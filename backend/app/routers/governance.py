"""Field operations, Responsible AI, privacy/DPDP, audit, reports and administration."""
from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ALL_PERMISSIONS, PERMISSION_LABELS, PERMISSIONS, ROLES, Principal, require
from ..db import get_db, iso, utcnow
from ..models import AuditEvent, Decision, Doc, FieldReport, Inventory, Movement, Node, Recommendation, Route, Sensor, User
from ..services import audit
from ..services.forecast import CLASSES, backtest, enrich_inventory, load_history, post_health
from ..services.governance_data import DPDP_STATEMENT
from ..services.recommender import generate_recommendations
from ..services.routing import RouteNet
from .ops import apply_stock_change

router = APIRouter(prefix="/api", tags=["governance"])


# --- field operations (offline-ready sync queue) ------------------------------------------------------------------
@router.get("/field/overview")
def field_overview(p: Principal = Depends(require("field.use")), db: Session = Depends(get_db)):
    posts = [n for n in db.scalars(select(Node).where(Node.kind == "post").order_by(Node.id)) if p.role != "post_incharge" or n.id == p.post_id]
    sensors = [s for s in db.scalars(select(Sensor).order_by(Sensor.id)) if p.role != "post_incharge" or s.post_id == p.post_id]
    inv = {(i.post_id, i.supply_class): i for i in db.scalars(select(Inventory))}
    reports = list(db.scalars(select(FieldReport).order_by(FieldReport.ts.desc()).limit(12)))
    return {"posts": [{"id": n.id, "name": n.name} for n in posts], "routes": [{"id": r.id, "label": f"{r.id} {r.a} ↔ {r.b}"} for r in db.scalars(select(Route).where(Route.mode == "road"))],
            "sensors": [{"id": s.id, "post_id": s.post_id, "kind": s.kind, "supply_class": s.supply_class, "battery_pct": s.battery_pct, "health": s.health, "last_seen": iso(s.last_seen),
                         "reading": round(max(0, inv[(s.post_id, s.supply_class)].quantity), 1) if s.kind == "smart-bin" and (s.post_id, s.supply_class) in inv else None,
                         "unit": inv[(s.post_id, s.supply_class)].unit if s.kind == "smart-bin" and (s.post_id, s.supply_class) in inv else None} for s in sensors],
            "classes": [{"id": k, "label": v["label"], "unit": v["unit"]} for k, v in CLASSES.items()],
            "recent_reports": [{"id": r.id, "kind": r.kind, "post_id": r.post_id, "route_id": r.route_id, "payload": r.payload, "ts": iso(r.ts), "actor": r.actor} for r in reports],
            "scope_post": p.post_id if p.role == "post_incharge" else None, "server_time": iso(utcnow()),
            "offline_note": "Entries made offline are queued on this device and applied when you sync. Conflicts are shown for manual resolution."}


class SyncItem(BaseModel):
    client_id: str = Field(min_length=6, max_length=48)
    type: Literal["stock_receipt", "stock_issue", "stock_count", "road_condition", "receipt_confirmation"]
    post_id: str | None = None
    route_id: str | None = None
    supply_class: str | None = None
    qty: float | None = None
    note: str = Field("", max_length=240)
    condition: Literal["clear", "slippery", "debris", "blocked"] | None = None
    base_version: int | None = None
    resolution: Literal["keep_server", "apply_mine"] | None = None
    created_at: str | None = None


class SyncBody(BaseModel):
    items: list[SyncItem] = Field(max_length=50)


@router.post("/field/sync")
def field_sync(body: SyncBody, p: Principal = Depends(require("field.use")), db: Session = Depends(get_db)):
    results = []
    for it in body.items:
        if db.scalar(select(FieldReport).where(FieldReport.client_id == it.client_id)):
            results.append({"client_id": it.client_id, "status": "duplicate", "message": "Already synchronised."})
            continue
        if p.role == "post_incharge" and it.post_id and it.post_id != p.post_id:
            results.append({"client_id": it.client_id, "status": "rejected", "message": "Outside your assigned post."})
            audit.append(db, p.label, p.role, "access.denied", it.post_id, "denied", {"reason": "field sync outside assigned post"})
            continue
        try:
            if it.type in ("stock_receipt", "stock_issue", "stock_count"):
                if "inventory.adjust" not in p.permissions and it.type != "stock_count":
                    results.append({"client_id": it.client_id, "status": "rejected", "message": "Your role cannot change stock."})
                    continue
                inv = db.scalar(select(Inventory).where(Inventory.post_id == it.post_id, Inventory.supply_class == it.supply_class))
                if inv is None or it.qty is None:
                    raise ValueError("Unknown post / supply class or missing quantity.")
                if it.base_version is not None and it.base_version != inv.version and it.resolution is None:
                    results.append({"client_id": it.client_id, "status": "conflict", "message": "Stock changed on the server since you went offline.",
                                    "server": {"quantity": inv.quantity, "version": inv.version, "updated_at": iso(inv.updated_at), "unit": inv.unit}})
                    continue
                if it.resolution == "keep_server":
                    db.add(FieldReport(client_id=it.client_id, kind="count", post_id=it.post_id, payload={"discarded": True, "note": "Conflict: server value kept"}, actor=p.label))
                    audit.append(db, p.label, p.role, "field.conflict_resolved", f"{it.post_id}/{it.supply_class}", "success", {"resolution": "keep_server"})
                    results.append({"client_id": it.client_id, "status": "applied", "message": "Server value kept."})
                    continue
                kind = {"stock_receipt": "receipt", "stock_issue": "issue", "stock_count": "count"}[it.type]
                recorded = inv.quantity
                if kind == "count":
                    db.add(FieldReport(kind="count", post_id=it.post_id, payload={"counted": it.qty, "recorded": recorded, "supply_class": it.supply_class}, actor=p.label))
                delta = apply_stock_change(db, inv, kind, it.qty, p.label, it.note or f"Field {kind} (synced)")
                db.add(FieldReport(client_id=it.client_id, kind=it.type, post_id=it.post_id, payload={"supply_class": it.supply_class, "qty": it.qty, "delta": delta}, actor=p.label))
                audit.append(db, p.label, p.role, "inventory.adjust", f"{it.post_id}/{it.supply_class}", "success", {"kind": kind, "delta": round(delta, 2), "via": "field-sync"})
            elif it.type == "road_condition":
                if it.route_id is None or db.get(Route, it.route_id) is None or it.condition is None:
                    raise ValueError("Route and condition are required.")
                db.add(FieldReport(client_id=it.client_id, kind="road_condition", route_id=it.route_id, payload={"condition": it.condition, "note": it.note}, actor=p.label))
                audit.append(db, p.label, p.role, "field.road_report", it.route_id, "success", {"condition": it.condition})
            else:
                db.add(FieldReport(client_id=it.client_id, kind="receipt", post_id=it.post_id, payload={"note": it.note}, actor=p.label))
                audit.append(db, p.label, p.role, "field.receipt_confirmed", it.post_id or "-", "success", {"note": it.note})
            results.append({"client_id": it.client_id, "status": "applied", "message": "Synchronised."})
        except ValueError as e:
            results.append({"client_id": it.client_id, "status": "rejected", "message": str(e)})
    db.flush()
    if any(r["status"] == "applied" for r in results):
        generate_recommendations(db)
    db.commit()
    return {"results": results, "server_time": iso(utcnow())}


# --- Responsible AI ------------------------------------------------------------------------------------------------
@router.get("/ai/overview")
def ai_overview(p: Principal = Depends(require("ai.view")), db: Session = Depends(get_db)):
    rows = enrich_inventory(db)
    ph = post_health(rows)
    recs = [r for r in db.scalars(select(Recommendation)) if r.origin != "synthetic-history"]
    pending = [r for r in recs if r.status == "Pending Review"]
    decisions = list(db.scalars(select(Decision).order_by(Decision.ts.desc()).limit(60)))
    nodes = {n.id: n for n in db.scalars(select(Node)) if n.kind == "post"}
    models = db.get(Doc, "models").value["items"]
    admin = db.get(Doc, "admin").value
    hist = load_history(db)
    # honest evaluation: back-test on synthetic history
    bts = [backtest(v) for k, v in hist.items() if len(v) >= 28]
    mm = [b["model_mape"] for b in bts if b["model_mape"] is not None]
    bb = [b["baseline_mape"] for b in bts if b["baseline_mape"] is not None]
    evaluation = {"series": len(mm), "model_mape": round(sum(mm) / len(mm), 1) if mm else None, "baseline_mape": round(sum(bb) / len(bb), 1) if bb else None,
                  "method": "One-day-ahead back-test over the last 14 days of SYNTHETIC history, mean absolute percentage error. Not a measure of real-world accuracy."}
    # allocation fairness: proposed quantity share vs need share by criticality tier
    tiers: dict[int, dict] = {}
    for r in recs:
        if r.status in ("Withdrawn", "Rejected"):
            continue
        t = nodes[r.post_id].tier if r.post_id in nodes else None
        if t is None:
            continue
        d = tiers.setdefault(t, {"tier": t, "posts": set(), "recs": 0, "critical": 0})
        d["posts"].add(r.post_id)
        d["recs"] += 1
        d["critical"] += r.urgency == "critical"
    tier_rows = []
    for t in (1, 2, 3):
        in_t = [n for n in nodes.values() if n.tier == t]
        at_risk = {r["post_id"] for r in rows if r["health"] in ("critical", "elevated") and nodes[r["post_id"]].tier == t}
        covered = {r.post_id for r in recs if r.status not in ("Withdrawn", "Rejected", "Completed") and nodes[r.post_id].tier == t}
        tier_rows.append({"tier": t, "posts": len(in_t), "posts_at_risk": len(at_risk), "at_risk_with_open_recommendation": len(at_risk & covered),
                          "at_risk_without_recommendation": sorted(at_risk - covered)})
    under = [{"post_id": r["post_id"], "post_name": r["post_name"], "supply_class": r["supply_class"], "dos": r["dos"], "tier": r["tier"]}
             for r in rows if r["health"] in ("critical", "elevated") and not any(
                 x.post_id == r["post_id"] and x.supply_class == r["supply_class"] and x.status in ("Pending Review", "Approved", "Simulated Dispatch", "Draft", "Info Requested") for x in recs)]
    low_q = [{"id": r.id, "post_id": r.post_id, "supply_class": r.supply_class, "confidence": r.confidence, "status": r.status} for r in recs if r.mandatory_review and r.status in ("Pending Review", "Draft", "Info Requested")]
    overrides = [{"ts": iso(d.ts), "rec_id": d.rec_id, "actor": d.actor, "action": d.action, "reason": d.reason, "detail": d.detail}
                 for d in decisions if d.action in ("Edit and approve", "Reject") ][:10]
    return {"disclaimer": "All models in this prototype are simulated or rule-based. No SHAP values, trained-model metrics or counterfactuals from a trained model are shown.",
            "confidence_meaning": "High / Medium / Low labels combine demand variability, history length, stock-reading validity and freshness, and sensor health. They are not calibrated probabilities.",
            "oversight": {"pending_reviews": len(pending), "pending": [{"id": r.id, "post_id": r.post_id, "urgency": r.urgency, "confidence": r.confidence, "mandatory_review": r.mandatory_review} for r in pending],
                          "history": [{"ts": iso(d.ts), "rec_id": d.rec_id, "actor": d.actor, "action": d.action, "reason": d.reason, "to": d.to_status} for d in decisions if d.action != "Generate"][:12],
                          "overrides": overrides},
            "low_confidence_queue": low_q, "data_quality": [{"post_id": r["post_id"], "supply_class": r["supply_class"], "confidence": r["confidence"], "reasons": r["confidence_reasons"]}
                                                          for r in rows if r["confidence"] != "High"][:12],
            "fallback": {"rule_based_fallback_enabled": admin["config"]["rule_based_fallback"], "series_on_fallback": sum(1 for r in rows if r["fallback"]),
                         "note": "Series with fewer than 14 days of history use a flat rule-based baseline with wide uncertainty."},
            "service_health": [{"service": "Forecast service (simulated statistical model)", "status": "ok"}, {"service": "Route reliability formula", "status": "ok"},
                               {"service": "Explanation service (rule-based)", "status": "ok"}, {"service": "Natural-language query service (optional)", "status": "disabled"}],
            "allocation": {"policy": ("Recommendations are generated per post and supply class to restore a 10-day cover once Days of Supply falls below 7, regardless of post rank. "
                                      "Criticality tier (1 = highest altitude/most remote) is used only to monitor coverage here; it does not reduce another post's allocation. "
                                      "Any change to this policy should be a documented human decision."),
                           "tiers": tier_rows, "under_supply_alerts": under},
            "models": models, "evaluation": evaluation}


@router.get("/ai/model/{model_id}")
def model_card(model_id: str, p: Principal = Depends(require("ai.view")), db: Session = Depends(get_db)):
    m = next((x for x in db.get(Doc, "models").value["items"] if x["id"] == model_id), None)
    if m is None:
        raise HTTPException(404, "Model not found")
    return m


# --- governance (privacy / DPDP) -----------------------------------------------------------------------------------
@router.get("/governance/privacy")
def privacy(p: Principal = Depends(require("governance.view")), db: Session = Depends(get_db)):
    d = db.get(Doc, "privacy").value
    admin = db.get(Doc, "admin").value
    users = [{"username": u.username, "name": u.name, "role": ROLES[u.role], "unit": u.unit, "last_login": iso(u.last_login), "active": u.active} for u in db.scalars(select(User).order_by(User.id))]
    access = [{"ts": iso(e.ts), "actor": e.actor, "action": e.action, "resource": e.resource, "outcome": e.outcome}
              for e in db.scalars(select(AuditEvent).where(AuditEvent.action.in_(["auth.sign_in", "auth.sign_out", "access.denied", "audit.verify", "governance.update"])).order_by(AuditEvent.id.desc()).limit(15))]
    return {**d, "statement": DPDP_STATEMENT, "access_history": access, "accounts": users, "can_manage": "governance.manage" in p.permissions,
            "personal_note": "Personal data here is limited to synthetic account, audit-actor and reporter identifiers. Inventory, terrain, weather and route data are non-personal operational data."}


class GovUpdate(BaseModel):
    section: Literal["requests", "deletions", "incidents", "processing"]
    item_id: str
    status: str | None = None
    stage: int | None = Field(None, ge=0, le=5)
    lawful_basis: str | None = Field(None, max_length=300)
    purpose: str | None = Field(None, max_length=300)
    note: str = Field("", max_length=300)


@router.post("/governance/update")
def gov_update(body: GovUpdate, p: Principal = Depends(require("governance.manage")), db: Session = Depends(get_db)):
    doc = db.get(Doc, "privacy")
    val = {**doc.value}
    items = [dict(i) for i in val[body.section]]
    it = next((i for i in items if i["id"] == body.item_id), None)
    if it is None:
        raise HTTPException(404, "Record not found")
    allowed = {"requests": {"Open", "In review", "Closed"}, "deletions": {"Pending approval", "Approved", "Completed (simulated)", "Rejected"},
               "incidents": set(), "processing": {"Draft", "Under review", "Approved for prototype"}}[body.section]
    if body.status is not None:
        if body.status not in allowed:
            raise HTTPException(422, f"Status must be one of {sorted(allowed)}")
        it["status"] = body.status
    if body.stage is not None and body.section == "incidents":
        it["stage"] = body.stage
    if body.section == "processing":
        if body.lawful_basis is not None:
            it["lawful_basis"] = body.lawful_basis
        if body.purpose is not None:
            it["purpose"] = body.purpose
    val[body.section] = items
    doc.value = val
    audit.append(db, p.label, p.role, "governance.update", f"{body.section}/{body.item_id}", "success", {"status": body.status, "stage": body.stage, "note": body.note})
    db.commit()
    return it


# --- audit -------------------------------------------------------------------------------------------------------
@router.get("/audit")
def list_audit(q: str = "", action: str = "", outcome: str = "", actor: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
               p: Principal = Depends(require("audit.view")), db: Session = Depends(get_db)):
    events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())))
    if q:
        ql = q.lower()
        events = [e for e in events if ql in e.resource.lower() or ql in e.action.lower() or ql in e.actor.lower() or ql in str(e.detail).lower()]
    if action:
        events = [e for e in events if e.action.startswith(action)]
    if outcome:
        events = [e for e in events if e.outcome == outcome]
    if actor:
        events = [e for e in events if actor.lower() in e.actor.lower()]
    actions = sorted({e.action for e in db.scalars(select(AuditEvent))})
    total = len(events)
    return {"total": total, "page": page, "page_size": page_size, "items": [audit.to_dict(e) for e in events[(page - 1) * page_size: page * page_size]], "actions": actions,
            "can_verify": "audit.verify" in p.permissions}


@router.post("/audit/verify")
def verify_audit(tamper_demo: bool = False, p: Principal = Depends(require("audit.verify")), db: Session = Depends(get_db)):
    target = None
    if tamper_demo:
        target = db.scalar(select(AuditEvent.id).order_by(AuditEvent.id.desc()).offset(2).limit(1)) or db.scalar(select(AuditEvent.id).limit(1))
    res = audit.verify(db, simulate_tamper_id=target)
    audit.append(db, p.label, p.role, "audit.verify", "audit-chain", "success", {"status": res["status"], "events_checked": res["events_checked"], "tamper_demo": tamper_demo})
    db.commit()
    return res


# --- reports -----------------------------------------------------------------------------------------------------
REPORTS = {
    "inventory-health": "Inventory health report", "forecast-performance": "Forecast performance report", "stockout-risk": "Stockout-risk report",
    "route-reliability": "Route reliability report", "recommendations": "Recommendation and approval report", "data-quality": "Data quality report",
    "responsible-ai": "Responsible-AI governance report",
}


def build_report(db: Session, key: str, date_from: str | None, date_to: str | None, q: str) -> dict:
    rows = enrich_inventory(db)
    now = utcnow()

    def in_range(ts):
        s = iso(ts)[:10]
        return (not date_from or s >= date_from) and (not date_to or s <= date_to)

    if key == "inventory-health":
        cols = ["post_id", "post_name", "supply_class", "unit", "usable", "dos", "tts_p50_h", "health", "source", "age_h"]
        data = [{c: r[c] for c in cols} for r in rows]
        summary = [{"label": h.title(), "value": sum(1 for r in rows if r["health"] == h)} for h in ("healthy", "attention", "elevated", "critical")]
        chart = {"type": "bar", "x": "label", "y": "value", "data": summary}
    elif key == "stockout-risk":
        cols = ["post_id", "supply_class", "dos", "tts_p50_h", "tts_earliest_h", "confidence", "health"]
        data = [{c: r[c] for c in cols} for r in sorted(rows, key=lambda r: r["tts_p50_h"])[:30]]
        summary = [{"label": "Within 72 h (P50)", "value": sum(1 for r in rows if r["tts_p50_h"] <= 72)}, {"label": "Within 7 days (P50)", "value": sum(1 for r in rows if r["tts_p50_h"] <= 168)},
                   {"label": "Within 72 h (P90 demand)", "value": sum(1 for r in rows if r["tts_earliest_h"] <= 72)}]
        chart = {"type": "bar", "x": "post_id", "y": "tts_p50_h", "data": data[:12]}
    elif key == "forecast-performance":
        hist = load_history(db)
        data = []
        for (post, cls), v in sorted(hist.items()):
            b = backtest(v)
            if b["n"]:
                data.append({"post_id": post, "supply_class": cls, "model_mape_pct": b["model_mape"], "baseline_mape_pct": b["baseline_mape"], "days_tested": b["n"]})
        mm = [d["model_mape_pct"] for d in data]
        bb = [d["baseline_mape_pct"] for d in data]
        summary = [{"label": "Mean model MAPE %", "value": round(sum(mm) / len(mm), 1) if mm else None}, {"label": "Mean baseline MAPE %", "value": round(sum(bb) / len(bb), 1) if bb else None},
                   {"label": "Series evaluated", "value": len(data)}]
        chart = {"type": "bar", "x": "post_id", "y": "model_mape_pct", "data": data[:12]}
    elif key == "route-reliability":
        net = RouteNet.from_db(db)
        data = [{"route_id": r.id, "from": r.a, "to": r.b, "mode": r.mode, "rri": net.a(r.id)["rri"], "risk": net.a(r.id)["risk"], "time_h": net.a(r.id)["time_h"], "closures_history": r.closure_count, "status": r.status}
                for r in db.scalars(select(Route).order_by(Route.id))]
        summary = [{"label": k.title(), "value": sum(1 for d in data if d["risk"] == k)} for k in ("low", "moderate", "elevated", "high", "closed")]
        chart = {"type": "bar", "x": "route_id", "y": "rri", "data": [d for d in data if d["mode"] == "road"][:14]}
    elif key == "recommendations":
        recs = [r for r in db.scalars(select(Recommendation).order_by(Recommendation.created_at.desc())) if in_range(r.created_at)]
        data = [{"id": r.id, "post_id": r.post_id, "supply_class": r.supply_class, "qty": r.qty, "unit": r.unit, "urgency": r.urgency, "confidence": r.confidence, "status": r.status,
                 "decided_by": r.decided_by or "", "created": iso(r.created_at)} for r in recs]
        summary = [{"label": s, "value": sum(1 for d in data if d["status"] == s)} for s in ("Pending Review", "Approved", "Simulated Dispatch", "Completed", "Rejected")]
        chart = {"type": "bar", "x": "label", "y": "value", "data": summary}
    elif key == "data-quality":
        data = [{"post_id": r["post_id"], "supply_class": r["supply_class"], "source": r["source"], "validation": r["validation"], "age_h": r["age_h"], "sensor_health": r["sensor_health"] or "n/a",
                 "confidence": r["confidence"], "issues": "; ".join(r["confidence_reasons"])} for r in rows if r["confidence"] != "High" or r["validation"] != "valid" or r["age_h"] > 24]
        summary = [{"label": "Records with issues", "value": len(data)}, {"label": "Stale or discrepancy", "value": sum(1 for d in data if d["validation"] != "valid")},
                   {"label": "Low confidence", "value": sum(1 for d in data if d["confidence"] == "Low")}]
        chart = {"type": "bar", "x": "confidence", "y": "value", "data": [{"confidence": c, "value": sum(1 for d in data if d["confidence"] == c)} for c in ("Low", "Medium", "High")]}
    else:  # responsible-ai
        decisions = [d for d in db.scalars(select(Decision).order_by(Decision.ts.desc())) if in_range(d.ts)]
        data = [{"ts": iso(d.ts), "rec_id": d.rec_id, "actor": d.actor, "action": d.action, "from": d.from_status, "to": d.to_status, "reason": d.reason or ""} for d in decisions]
        human = [d for d in decisions if d.role != "system"]
        summary = [{"label": "Human decisions", "value": sum(1 for d in human if d.action in ("Approve", "Edit and approve", "Reject", "Request more information"))},
                   {"label": "Overrides (edit)", "value": sum(1 for d in human if d.action == "Edit and approve")}, {"label": "Rejections", "value": sum(1 for d in human if d.action == "Reject")}]
        chart = {"type": "bar", "x": "label", "y": "value", "data": summary}
    if q:
        ql = q.lower()
        data = [d for d in data if ql in " ".join(str(v) for v in d.values()).lower()]
    return {"key": key, "title": REPORTS[key], "generated_at": iso(now), "synthetic": True, "summary": summary, "columns": list(data[0].keys()) if data else [],
            "rows": data, "chart": chart, "note": "Synthetic data and calculated demo metrics. Any improvement figures are targets until validated against a defined baseline."}


@router.get("/reports")
def reports_index(p: Principal = Depends(require("reports.view"))):
    return {"items": [{"key": k, "title": v} for k, v in REPORTS.items()]}


@router.get("/reports/{key}")
def get_report(key: str, date_from: str | None = None, date_to: str | None = None, q: str = "", p: Principal = Depends(require("reports.view")), db: Session = Depends(get_db)):
    if key not in REPORTS:
        raise HTTPException(404, "Unknown report")
    return build_report(db, key, date_from, date_to, q)


@router.get("/reports/{key}/csv")
def report_csv(key: str, date_from: str | None = None, date_to: str | None = None, q: str = "", p: Principal = Depends(require("reports.view")), db: Session = Depends(get_db)):
    if key not in REPORTS:
        raise HTTPException(404, "Unknown report")
    rep = build_report(db, key, date_from, date_to, q)
    buf = io.StringIO()
    buf.write(f"# {rep['title']} - SYNTHETIC DEMONSTRATION DATA - generated {rep['generated_at']}\n")
    w = csv.DictWriter(buf, fieldnames=rep["columns"] or ["no_data"])
    w.writeheader()
    for row in rep["rows"]:
        w.writerow({k: ("'" + str(v) if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in row.items()})  # neutralise CSV formula injection
    audit.append(db, p.label, p.role, "report.export", key, "success", {"rows": len(rep["rows"])})
    db.commit()
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="himavahpro-{key}.csv"'})


# --- administration ------------------------------------------------------------------------------------------------
@router.get("/admin/overview")
def admin_overview(p: Principal = Depends(require("admin.view")), db: Session = Depends(get_db)):
    admin = db.get(Doc, "admin").value
    priv = db.get(Doc, "privacy").value
    users = [{"id": u.id, "username": u.username, "name": u.name, "role": u.role, "role_label": ROLES[u.role], "unit": u.unit, "post_id": u.post_id, "active": u.active,
              "mfa": u.mfa_enabled, "last_login": iso(u.last_login)} for u in db.scalars(select(User).order_by(User.id))]
    sensors = [{"id": s.id, "post_id": s.post_id, "kind": s.kind, "battery_pct": s.battery_pct, "health": s.health, "last_seen": iso(s.last_seen)} for s in db.scalars(select(Sensor).order_by(Sensor.id))]
    nodes = [n for n in db.scalars(select(Node)) if n.kind in ("depot", "airfield", "post")]
    hierarchy = {}
    for n in nodes:
        hierarchy.setdefault(n.formation or "Rear", []).append({"id": n.id, "name": n.name, "kind": n.kind})
    return {"users": users, "roles": [{"role": r, "label": l} for r, l in ROLES.items()], "devices": sensors, "config": admin["config"], "integrations": admin["integrations"],
            "retention": priv["retention"], "hierarchy": [{"formation": k, "units": v} for k, v in sorted(hierarchy.items())],
            "health": [{"component": "API", "status": "ok"}, {"component": "Database", "status": "ok", "note": "Development SQLite unless DATABASE_URL is set."},
                       {"component": "Sensors healthy", "status": "ok" if all(s["health"] == "ok" for s in sensors) else "attention",
                        "note": f"{sum(1 for s in sensors if s['health'] != 'ok')} of {len(sensors)} need attention"},
                       {"component": "Audit chain", "status": "ok"}],
            "can_edit_users": "admin.users" in p.permissions, "can_edit_config": "admin.config" in p.permissions,
            "permission_matrix": {"roles": [{"role": r, "label": l} for r, l in ROLES.items()], "permissions": [{"key": k, "label": PERMISSION_LABELS.get(k, k)} for k in ALL_PERMISSIONS],
                                  "grants": {r: sorted(PERMISSIONS[r]) for r in ROLES}}}


class UserUpdate(BaseModel):
    role: str | None = None
    active: bool | None = None


@router.patch("/admin/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, p: Principal = Depends(require("admin.users")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    if body.role is not None and body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    if u.username == p.username and (body.active is False or (body.role and body.role != "sysadmin")):
        raise HTTPException(409, "You cannot remove your own administrator access.")
    before = {"role": u.role, "active": u.active}
    if body.role is not None:
        u.role = body.role
    if body.active is not None:
        u.active = body.active
    audit.append(db, p.label, p.role, "admin.user_update", u.username, "success", {"from": before, "to": {"role": u.role, "active": u.active}})
    db.commit()
    return {"id": u.id, "role": u.role, "active": u.active}


class ConfigUpdate(BaseModel):
    key: Literal["low_confidence_threshold", "mandatory_review_on_low", "rule_based_fallback", "session_ttl_hours", "audit_chain_enabled", "default_forecast_horizon_days"]
    value: str | int | bool


@router.patch("/admin/config")
def update_config(body: ConfigUpdate, p: Principal = Depends(require("admin.config")), db: Session = Depends(get_db)):
    doc = db.get(Doc, "admin")
    cfg = dict(doc.value["config"])
    v = body.value
    if body.key == "low_confidence_threshold" and v not in ("Low", "Medium"):
        raise HTTPException(422, "Must be Low or Medium")
    if body.key in ("mandatory_review_on_low", "rule_based_fallback", "audit_chain_enabled") and not isinstance(v, bool):
        raise HTTPException(422, "Must be true or false")
    if body.key == "audit_chain_enabled" and v is False:
        raise HTTPException(422, "The audit chain cannot be disabled in this prototype.")
    if body.key == "session_ttl_hours" and not (isinstance(v, int) and 1 <= v <= 24):
        raise HTTPException(422, "Must be 1-24")
    if body.key == "default_forecast_horizon_days" and v not in (1, 3, 7):
        raise HTTPException(422, "Must be 1, 3 or 7")
    old = cfg.get(body.key)
    cfg[body.key] = v
    doc.value = {**doc.value, "config": cfg}
    audit.append(db, p.label, p.role, "config.change", f"config.{body.key}", "success", {"from": old, "to": v, "note": "Recorded setting; not all settings alter prototype behaviour."})
    db.commit()
    return cfg
