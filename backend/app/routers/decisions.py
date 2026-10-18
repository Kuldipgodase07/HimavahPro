"""Recommendation inbox, human approval workflow and the what-if simulator."""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import Principal, require
from ..db import get_db, iso, utcnow
from ..models import Convoy, Decision, Doc, Inventory, Movement, Node, Recommendation, ScenarioRun
from ..services import audit
from ..services.explain import explain_recommendation
from ..services.forecast import CLASSES, MODEL_VERSION, enrich_inventory
from ..services.overview import expire_closures, rec_brief
from ..services.recommender import TARGET_DAYS, build_plan, generate_recommendations, next_rec_id
from ..services.routing import RouteNet
from ..services import simulator

router = APIRouter(prefix="/api", tags=["decisions"])

STATUS_FLOW = ["Draft", "Pending Review", "Approved", "Simulated Dispatch", "Completed"]


def rec_dict(r: Recommendation, db: Session | None = None) -> dict:
    d = rec_brief(r)
    d.update({"reason": r.reason, "plan": r.plan, "alternatives": r.alternatives, "evidence": r.evidence, "limitations": r.limitations,
              "model_version": r.model_version, "data_as_of": iso(r.data_as_of), "origin": r.origin, "updated_at": iso(r.updated_at),
              "decided_by": r.decided_by, "decision_reason": r.decision_reason, "original_qty": r.original_qty, "convoy_id": r.convoy_id})
    if db is not None:
        node = db.get(Node, r.post_id)
        d["post_name"] = node.name if node else r.post_id
    return d


def _get(db: Session, rec_id: str, p: Principal) -> Recommendation:
    r = db.get(Recommendation, rec_id)
    if r is None or (p.role == "post_incharge" and r.post_id != p.post_id):
        raise HTTPException(404, "Recommendation not found")
    return r


def _log(db: Session, p: Principal, rec: Recommendation, action: str, to: str, reason: str | None, audit_action: str, detail: dict | None = None) -> None:
    db.add(Decision(rec_id=rec.id, ts=utcnow(), actor=p.label, role=p.role, action=action, reason=reason, from_status=rec.status, to_status=to, detail=detail or {}))
    audit.append(db, p.label, p.role, audit_action, rec.id, "success", {"from": rec.status, "to": to, "reason": reason, **(detail or {})})
    rec.status = to
    rec.updated_at = utcnow()


@router.get("/recommendations")
def list_recommendations(status: str = "", urgency: str = "", cls: str = "", post: str = "", confidence: str = "", q: str = "", include_history: bool = False,
                         p: Principal = Depends(require("recs.view")), db: Session = Depends(get_db)):
    expire_closures(db)
    stmt = select(Recommendation).order_by(Recommendation.created_at.desc())
    items = [r for r in db.scalars(stmt) if (include_history or r.origin != "synthetic-history") and (p.role != "post_incharge" or r.post_id == p.post_id)]
    for key, val in (("status", status), ("urgency", urgency), ("supply_class", cls), ("post_id", post), ("confidence", confidence)):
        if val:
            items = [r for r in items if getattr(r, key) == val]
    if q:
        ql = q.lower()
        items = [r for r in items if ql in r.id.lower() or ql in r.post_id.lower() or ql in r.reason.lower()]
    order = {"critical": 0, "high": 1, "medium": 2}
    items.sort(key=lambda r: (r.status in ("Completed", "Rejected", "Withdrawn"), order[r.urgency], r.created_at))
    counts: dict[str, int] = {}
    for r in db.scalars(stmt):
        if r.origin != "synthetic-history":
            counts[r.status] = counts.get(r.status, 0) + 1
    return {"items": [rec_dict(r, db) for r in items], "counts": counts, "flow": STATUS_FLOW,
            "perms": {"decide": "recs.decide" in p.permissions, "submit": bool({"recs.submit", "recs.create", "recs.decide"} & p.permissions),
                      "dispatch": "recs.dispatch" in p.permissions, "create": "recs.create" in p.permissions}}


@router.get("/recommendations/{rec_id}")
def get_recommendation(rec_id: str, p: Principal = Depends(require("recs.view")), db: Session = Depends(get_db)):
    r = _get(db, rec_id, p)
    hist = [{"ts": iso(d.ts), "actor": d.actor, "role": d.role, "action": d.action, "reason": d.reason, "from": d.from_status, "to": d.to_status, "detail": d.detail}
            for d in db.scalars(select(Decision).where(Decision.rec_id == rec_id).order_by(Decision.ts, Decision.id))]
    convoy = db.get(Convoy, r.convoy_id) if r.convoy_id else None
    return {"item": rec_dict(r, db), "history": hist, "flow": STATUS_FLOW,
            "convoy": {"id": convoy.id, "status": convoy.status, "est_eta": iso(convoy.est_eta)} if convoy else None}


@router.get("/recommendations/{rec_id}/explanation")
def recommendation_explanation(rec_id: str, p: Principal = Depends(require("recs.view")), db: Session = Depends(get_db)):
    return explain_recommendation(db, _get(db, rec_id, p))


class CreateRecBody(BaseModel):
    post_id: str
    supply_class: Literal["rations", "fuel", "medical", "spares"]
    qty: float = Field(gt=0, le=100000)
    note: str = Field("", max_length=240)


@router.post("/recommendations")
def create_draft(body: CreateRecBody, p: Principal = Depends(require("recs.create")), db: Session = Depends(get_db)):
    row = next((r for r in enrich_inventory(db) if r["post_id"] == body.post_id and r["supply_class"] == body.supply_class), None)
    if row is None:
        raise HTTPException(404, "Unknown post / supply class")
    if db.scalar(select(Recommendation).where(Recommendation.post_id == body.post_id, Recommendation.supply_class == body.supply_class,
                                              Recommendation.status.in_(["Draft", "Pending Review", "Info Requested", "Approved", "Simulated Dispatch"]))):
        raise HTTPException(409, "An open recommendation already exists for this post and supply class.")
    net = RouteNet.from_db(db)
    mode, primary, alts, notes, _ = build_plan(net, body.post_id, body.supply_class, body.qty)
    now = utcnow()
    rid = next_rec_id(db)
    rec = Recommendation(id=rid, post_id=body.post_id, supply_class=body.supply_class, qty=body.qty, unit=row["unit"], urgency="medium",
                         reason=body.note or "Manually drafted by a planner.", transport_mode=mode, plan=primary or {}, alternatives=alts,
                         evidence={"dos": row["dos"], "tts_p50_h": row["tts_p50_h"], "tts_earliest_h": row["tts_earliest_h"], "usable": row["usable"], "unit": row["unit"],
                                   "eta_h": round(primary["time_h"] + 4, 1) if primary else None, "forecast_confidence": row["confidence"]},
                         limitations=["Manually drafted; quantity not derived by the planner engine.", *notes], confidence=row["confidence"],
                         mandatory_review=row["confidence"] == "Low", status="Draft", model_version=MODEL_VERSION, data_as_of=now, origin="manual-draft", created_at=now, updated_at=now)
    db.add(rec)
    db.add(Decision(rec_id=rid, ts=now, actor=p.label, role=p.role, action="Create draft", reason=body.note or None, from_status="-", to_status="Draft"))
    audit.append(db, p.label, p.role, "recommendation.draft_created", rid, "success", {"post": body.post_id, "class": body.supply_class, "qty": body.qty})
    db.commit()
    return rec_dict(rec, db)


@router.post("/recommendations/{rec_id}/submit")
def submit(rec_id: str, p: Principal = Depends(require()), db: Session = Depends(get_db)):
    if not ({"recs.submit", "recs.create", "recs.decide"} & p.permissions):
        audit.append(db, p.label, p.role, "access.denied", rec_id, "denied", {"required": "recs.submit"})
        db.commit()
        raise HTTPException(403, "Permission denied: requires recs.submit")
    r = _get(db, rec_id, p)
    if r.status != "Draft":
        raise HTTPException(409, f"Only Draft recommendations can be submitted (current: {r.status}).")
    _log(db, p, r, "Submit for review", "Pending Review", None, "recommendation.submit")
    db.commit()
    return rec_dict(r, db)


class RespondBody(BaseModel):
    message: str = Field(min_length=5, max_length=500)


@router.post("/recommendations/{rec_id}/respond")
def respond_info(rec_id: str, body: RespondBody, p: Principal = Depends(require("recs.submit")), db: Session = Depends(get_db)):
    r = _get(db, rec_id, p)
    if r.status != "Info Requested":
        raise HTTPException(409, "No information request is open on this recommendation.")
    _log(db, p, r, "Provide information", "Pending Review", body.message, "recommendation.info_provided")
    db.commit()
    return rec_dict(r, db)


class DecisionBody(BaseModel):
    action: Literal["approve", "edit_approve", "reject", "request_info"]
    reason: str | None = Field(None, max_length=500)
    qty: float | None = Field(None, gt=0)
    transport_mode: Literal["road", "air"] | None = None
    acknowledged_low_confidence: bool = False


@router.post("/recommendations/{rec_id}/decision")
def decide(rec_id: str, body: DecisionBody, p: Principal = Depends(require("recs.decide")), db: Session = Depends(get_db)):
    r = _get(db, rec_id, p)
    if r.status not in ("Pending Review", "Info Requested"):
        raise HTTPException(409, f"Decisions can only be taken on Pending Review items (current: {r.status}).")
    reason = (body.reason or "").strip()
    if body.action in ("reject", "edit_approve", "request_info") and len(reason) < 10:
        raise HTTPException(422, {"reject": "A reason of at least 10 characters is required to reject.",
                                  "edit_approve": "A reason of at least 10 characters is required to override the recommendation.",
                                  "request_info": "State what information is needed (at least 10 characters)."}[body.action])
    if body.action in ("approve", "edit_approve") and r.mandatory_review and not body.acknowledged_low_confidence:
        raise HTTPException(422, "This recommendation is flagged for mandatory review (low confidence or no feasible route). Acknowledge the limitations to proceed.")
    if body.action == "request_info":
        _log(db, p, r, "Request more information", "Info Requested", reason, "recommendation.request_info")
    elif body.action == "reject":
        r.decided_by, r.decision_reason = p.label, reason
        _log(db, p, r, "Reject", "Rejected", reason, "recommendation.reject")
    else:
        detail: dict = {}
        if body.action == "edit_approve":
            changed = []
            if body.qty is not None and abs(body.qty - r.qty) > 1e-9:
                if body.qty > r.qty * 3:
                    raise HTTPException(422, "Edited quantity may not exceed 3x the proposed quantity.")
                r.original_qty, detail["qty_from"], detail["qty_to"] = r.qty, r.qty, body.qty
                r.qty = body.qty
                changed.append("quantity")
            if body.transport_mode and body.transport_mode != r.transport_mode:
                alt = next((a for a in r.alternatives if a["mode"] == body.transport_mode), None)
                if alt is None:
                    raise HTTPException(422, f"No feasible {body.transport_mode} option is available for this recommendation.")
                detail["mode_from"], detail["mode_to"] = r.transport_mode, body.transport_mode
                r.alternatives = [{**r.plan, "label": "Original plan"}, *[a for a in r.alternatives if a is not alt]]
                r.plan, r.transport_mode = alt, body.transport_mode
                changed.append("transport")
            if not changed:
                raise HTTPException(422, "Edit and Approve requires a changed quantity or transport mode.")
        r.decided_by, r.decision_reason = p.label, reason or None
        _log(db, p, r, "Edit and approve" if body.action == "edit_approve" else "Approve", "Approved", reason or None,
             "recommendation.override" if body.action == "edit_approve" else "recommendation.approve",
             {**detail, "acknowledged_low_confidence": body.acknowledged_low_confidence})
    db.commit()
    return rec_dict(r, db)


def _complete_delivery(db: Session, rec: Recommendation, convoy: Convoy, p: Principal) -> float:
    inv = db.scalar(select(Inventory).where(Inventory.post_id == rec.post_id, Inventory.supply_class == rec.supply_class))
    inv.quantity = round(inv.quantity + rec.qty, 2)
    inv.updated_at, inv.source, inv.validation, inv.version = utcnow(), "manual", "valid", inv.version + 1
    db.add(Movement(post_id=rec.post_id, supply_class=rec.supply_class, kind="receipt", qty=rec.qty, actor=p.label, note=f"Simulated delivery {convoy.id}", ref=rec.id))
    convoy.status, convoy.est_eta = "Arrived", utcnow()
    return rec.qty


@router.post("/recommendations/{rec_id}/dispatch")
def simulated_dispatch(rec_id: str, p: Principal = Depends(require("recs.dispatch")), db: Session = Depends(get_db)):
    r = _get(db, rec_id, p)
    if r.status != "Approved":
        raise HTTPException(409, "Only Approved recommendations can enter simulated dispatch.")
    if not r.plan:
        raise HTTPException(422, "No feasible route plan: cannot create a simulated dispatch.")
    n = (db.scalar(select(func.count()).select_from(Convoy)) or 0) + 101
    cid = f"CNV-{n}"
    while db.get(Convoy, cid):
        n += 1
        cid = f"CNV-{n}"
    now = utcnow()
    eta = now + timedelta(hours=(r.evidence or {}).get("eta_h") or r.plan["time_h"] + 4)
    db.add(Convoy(id=cid, dest_post=r.post_id, origin=r.plan.get("origin") or r.plan["nodes"][0], supply_class=r.supply_class, qty=r.qty, mode=r.plan["mode"],
                  path=r.plan["nodes"], route_ids=r.plan["route_ids"], status="In Transit", dispatched_at=now, planned_eta=eta, est_eta=eta, rec_id=r.id))
    r.convoy_id = cid
    _log(db, p, r, "Start simulated dispatch", "Simulated Dispatch", None, "dispatch.simulated", {"convoy": cid, "note": "Fictional convoy record; no real dispatch system is connected."})
    db.flush()
    generate_recommendations(db)
    db.commit()
    return rec_dict(r, db)


@router.post("/recommendations/{rec_id}/complete")
def complete(rec_id: str, p: Principal = Depends(require("recs.dispatch")), db: Session = Depends(get_db)):
    r = _get(db, rec_id, p)
    if r.status != "Simulated Dispatch":
        raise HTTPException(409, "Only recommendations in Simulated Dispatch can be completed.")
    convoy = db.get(Convoy, r.convoy_id)
    qty = _complete_delivery(db, r, convoy, p)
    _log(db, p, r, "Mark completed", "Completed", None, "dispatch.completed", {"convoy": convoy.id, "received_qty": qty})
    db.flush()
    changes = generate_recommendations(db)
    db.commit()
    return {"item": rec_dict(r, db), "recommendation_changes": changes}


# --- simulator ---------------------------------------------------------------------------------------------------
@router.get("/simulations/kinds")
def sim_kinds(p: Principal = Depends(require("sim.view")), db: Session = Depends(get_db)):
    demo = db.get(Doc, "demo").value
    net = RouteNet.from_db(db)
    return {"kinds": [{"id": k, "label": v} for k, v in simulator.KINDS.items()], "demo": demo,
            "routes": [{"id": r["id"], "label": f"{r['id']} {r['a']} ↔ {r['b']}", "mode": r["mode"]} for r in net.routes.values()],
            "posts": [{"id": n.id, "name": n.name} for n in db.scalars(select(Node).where(Node.kind == "post").order_by(Node.id))],
            "convoys": [c.id for c in db.scalars(select(Convoy).where(Convoy.status.in_(["Planned", "In Transit", "Delayed"])))],
            "classes": [{"id": k, "label": v["label"]} for k, v in CLASSES.items()],
            "banner": "SIMULATION ENVIRONMENT: scenarios run on an in-memory copy and never change live stock, routes or convoys.",
            "can_run": "sim.run" in p.permissions}


class RunBody(BaseModel):
    kind: str
    params: dict = Field(default_factory=dict)


@router.post("/simulations/run")
def run_sim(body: RunBody, p: Principal = Depends(require("sim.run")), db: Session = Depends(get_db)):
    try:
        result = simulator.run_scenario(db, body.kind, body.params)
    except simulator.ScenarioError as e:
        raise HTTPException(422, str(e))
    result["run_id"] = simulator.save_run(db, p.label, p.role, result)
    db.commit()
    return result


@router.get("/simulations/runs")
def sim_runs(p: Principal = Depends(require("sim.view")), db: Session = Depends(get_db)):
    return {"items": [{"id": r.id, "ts": iso(r.ts), "actor": r.actor, "kind": r.kind, "params": r.params, "summary": r.summary}
                      for r in db.scalars(select(ScenarioRun).order_by(ScenarioRun.ts.desc()).limit(15))]}


@router.post("/simulations/{run_id}/drafts")
def sim_drafts(run_id: str, p: Principal = Depends(require("sim.run", "recs.create")), db: Session = Depends(get_db)):
    run = db.get(ScenarioRun, run_id)
    if run is None:
        raise HTTPException(404, "Scenario run not found")
    result = simulator.run_scenario(db, run.kind, run.params)
    made = simulator.create_drafts(db, run_id, result, p.label, p.role)
    db.commit()
    return {"created": made}
