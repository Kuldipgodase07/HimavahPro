"""Operational read/write endpoints: dashboard, map, inventory, forecasts, routes, convoys."""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, require
from ..db import get_db, iso, utcnow
from ..models import Convoy, FieldReport, Inventory, Movement, Node, Recommendation, Route, Sensor
from ..services import audit
from ..services.forecast import CLASSES, enrich_inventory, forecast_detail
from ..services.overview import dashboard, expire_closures, map_payload, node_dict, rec_brief, route_dict
from ..services.recommender import generate_recommendations, replan_convoys
from ..services.routing import RouteNet, assess

router = APIRouter(prefix="/api", tags=["operations"])


# --- dashboard & map ---------------------------------------------------------------------------------------------
@router.get("/dashboard")
def get_dashboard(p: Principal = Depends(require("dashboard.view")), db: Session = Depends(get_db)):
    expire_closures(db)
    return dashboard(db)


@router.get("/map")
def get_map(p: Principal = Depends(require("map.view")), db: Session = Depends(get_db)):
    expire_closures(db)
    return map_payload(db)


@router.get("/posts/{post_id}")
def get_post(post_id: str, p: Principal = Depends(require("map.view")), db: Session = Depends(get_db)):
    node = db.get(Node, post_id)
    if node is None or node.kind != "post":
        raise HTTPException(404, "Post not found")
    rows = [r for r in enrich_inventory(db) if r["post_id"] == post_id]
    net = RouteNet.from_db(db)
    routes = [route_dict(r, net) for r in db.scalars(select(Route).where((Route.a == post_id) | (Route.b == post_id)))]
    convoys = [c for c in db.scalars(select(Convoy).where(Convoy.dest_post == post_id, Convoy.status.in_(["Planned", "In Transit", "Delayed", "Incident"])))]
    recs = list(db.scalars(select(Recommendation).where(Recommendation.post_id == post_id, Recommendation.origin != "synthetic-history",
                                                       Recommendation.status.in_(["Draft", "Pending Review", "Info Requested", "Approved", "Simulated Dispatch"]))))
    sensors = list(db.scalars(select(Sensor).where(Sensor.post_id == post_id)))
    from ..services.forecast import load_weather
    return {"node": node_dict(node), "inventory": rows, "routes": routes, "weather": load_weather(db).get(post_id),
            "inbound": [convoy_dict(c, net) for c in convoys], "recommendations": [rec_brief(r) for r in recs],
            "sensors": [{"id": s.id, "kind": s.kind, "supply_class": s.supply_class, "battery_pct": s.battery_pct, "health": s.health, "last_seen": iso(s.last_seen)} for s in sensors]}


# --- inventory ---------------------------------------------------------------------------------------------------
SORTABLE = {"post_id", "supply_class", "usable", "avg_daily", "dos", "tts_p50_h", "reorder_threshold", "age_h", "health", "confidence"}
HEALTH_RANK = {"critical": 0, "elevated": 1, "attention": 2, "healthy": 3}


@router.get("/inventory")
def list_inventory(q: str = "", post: str = "", cls: str = "", health: str = "", source: str = "", validation: str = "",
                   sort: str = "dos", order: Literal["asc", "desc"] = "asc", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   p: Principal = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    rows = enrich_inventory(db)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["post_id"].lower() or ql in r["post_name"].lower() or ql in r["supply_class"]]
    for key, val in (("post_id", post), ("supply_class", cls), ("health", health), ("source", source), ("validation", validation)):
        if val:
            rows = [r for r in rows if r[key] == val]
    if sort not in SORTABLE:
        raise HTTPException(422, f"sort must be one of {sorted(SORTABLE)}")
    keyf = (lambda r: HEALTH_RANK[r["health"]]) if sort == "health" else (lambda r: r[sort])
    rows.sort(key=keyf, reverse=order == "desc")
    all_rows = enrich_inventory(db)
    summary = {h: sum(1 for r in all_rows if r["health"] == h) for h in HEALTH_RANK}
    total = len(rows)
    return {"total": total, "page": page, "page_size": page_size, "items": rows[(page - 1) * page_size: page * page_size], "summary": summary,
            "discrepancies": [r for r in all_rows if r["validation"] == "discrepancy"],
            "can_adjust": "inventory.adjust" in p.permissions, "scope_post": p.post_id if p.role == "post_incharge" else None}


@router.get("/inventory/{inv_id}")
def inventory_detail(inv_id: int, p: Principal = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    row = next((r for r in enrich_inventory(db) if r["id"] == inv_id), None)
    if row is None:
        raise HTTPException(404, "Inventory record not found")
    moves = list(db.scalars(select(Movement).where(Movement.post_id == row["post_id"], Movement.supply_class == row["supply_class"]).order_by(Movement.ts.desc()).limit(25)))
    reports = list(db.scalars(select(FieldReport).where(FieldReport.post_id == row["post_id"], FieldReport.kind == "count").order_by(FieldReport.ts.desc()).limit(5)))
    flags = []
    if row["validation"] == "discrepancy":
        flags.append("Stock reading flagged as discrepancy: recorded stock disagrees with an independent source.")
    if row["validation"] == "stale" or row["age_h"] > 24:
        flags.append(f"Reading is {row['age_h']:.0f} h old.")
    if row["sensor_health"] in ("offline", "degraded"):
        flags.append(f"Smart-bin sensor {row['sensor_health']}.")
    for r in reports:
        diff = r.payload.get("counted", 0) - r.payload.get("recorded", 0)
        if r.payload.get("recorded") and abs(diff) / max(r.payload["recorded"], 1) > 0.05:
            flags.append(f"Field count by {r.actor} differed from recorded stock by {diff:+g} {row['unit']}.")
    return {"item": row, "movements": [{"id": m.id, "kind": m.kind, "qty": m.qty, "ts": iso(m.ts), "actor": m.actor, "note": m.note, "ref": m.ref} for m in moves],
            "flags": flags, "can_adjust": "inventory.adjust" in p.permissions and (p.role != "post_incharge" or p.post_id == row["post_id"])}


class AdjustBody(BaseModel):
    kind: Literal["receipt", "issue", "adjustment", "count"]
    qty: float
    reason: str = Field(min_length=5, max_length=240)
    expected_version: int | None = None


def apply_stock_change(db: Session, inv: Inventory, kind: str, qty: float, actor: str, note: str, ref: str | None = None) -> float:
    """Apply a stock change, returning the signed delta. Raises ValueError on invalid input."""
    if kind in ("receipt", "issue"):
        if qty <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if kind == "issue" and qty > inv.quantity - inv.reserved:
            raise ValueError(f"Issue exceeds usable stock ({inv.quantity - inv.reserved:g} {inv.unit}).")
        delta = qty if kind == "receipt" else -qty
    elif kind == "count":
        if qty < 0:
            raise ValueError("Counted quantity cannot be negative.")
        delta = qty - inv.quantity
    else:
        if qty == 0 or abs(qty) > max(inv.quantity * 0.5, 1):
            raise ValueError("Adjustment must be non-zero and within ±50 % of current stock.")
        delta = qty
    if inv.quantity + delta < inv.reserved:
        raise ValueError("Change would take stock below the reserved quantity.")
    inv.quantity = round(inv.quantity + delta, 2)
    inv.updated_at = utcnow()
    inv.source, inv.validation, inv.version = "manual", "valid", inv.version + 1
    db.add(Movement(post_id=inv.post_id, supply_class=inv.supply_class, kind=kind, qty=round(delta, 2), actor=actor, note=note, ref=ref))
    return delta


@router.post("/inventory/{inv_id}/adjust")
def adjust_inventory(inv_id: int, body: AdjustBody, p: Principal = Depends(require("inventory.adjust")), db: Session = Depends(get_db)):
    inv = db.get(Inventory, inv_id)
    if inv is None:
        raise HTTPException(404, "Inventory record not found")
    if p.role == "post_incharge" and p.post_id != inv.post_id:
        audit.append(db, p.label, p.role, "access.denied", f"{inv.post_id}/{inv.supply_class}", "denied", {"reason": "outside assigned post"})
        db.commit()
        raise HTTPException(403, "Post In-Charge may only adjust stock at the assigned post.")
    if body.expected_version is not None and body.expected_version != inv.version:
        raise HTTPException(409, "Stock record changed since you opened it. Reload and retry.")
    try:
        delta = apply_stock_change(db, inv, body.kind, body.qty, p.label, body.reason)
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit.append(db, p.label, p.role, "inventory.adjust", f"{inv.post_id}/{inv.supply_class}", "success",
                 {"kind": body.kind, "delta": round(delta, 2), "reason": body.reason, "new_quantity": inv.quantity})
    db.flush()
    changes = generate_recommendations(db)
    db.commit()
    return {"ok": True, "delta": round(delta, 2), "item": next(r for r in enrich_inventory(db) if r["id"] == inv_id), "recommendation_changes": changes}


# --- forecasts ---------------------------------------------------------------------------------------------------
@router.get("/forecast/options")
def forecast_options(p: Principal = Depends(require("forecast.view")), db: Session = Depends(get_db)):
    return {"posts": [{"id": n.id, "name": n.name} for n in db.scalars(select(Node).where(Node.kind == "post").order_by(Node.id))],
            "classes": [{"id": k, "label": v["label"], "unit": v["unit"]} for k, v in CLASSES.items()], "horizons": [1, 3, 7]}


@router.get("/forecast")
def get_forecast(post: str, cls: str, horizon: int = Query(3), p: Principal = Depends(require("forecast.view")), db: Session = Depends(get_db)):
    if horizon not in (1, 3, 7):
        raise HTTPException(422, "horizon must be 1, 3 or 7 days (24 h, 72 h, 7 d)")
    if cls not in CLASSES:
        raise HTTPException(422, "Unknown supply class")
    out = forecast_detail(db, post, cls, horizon)
    if out is None:
        raise HTTPException(404, "No inventory record for that post and class")
    return out


# --- routes ------------------------------------------------------------------------------------------------------
@router.get("/routes")
def list_routes(q: str = "", risk: str = "", mode: str = "", p: Principal = Depends(require("routes.view")), db: Session = Depends(get_db)):
    expire_closures(db)
    net = RouteNet.from_db(db)
    items = [route_dict(r, net) for r in db.scalars(select(Route).order_by(Route.id))]
    if q:
        ql = q.lower()
        items = [r for r in items if ql in r["id"].lower() or ql in r["a"].lower() or ql in r["b"].lower()]
    if risk:
        items = [r for r in items if r["risk"] == risk]
    if mode:
        items = [r for r in items if r["mode"] == mode]
    nodes = {n.id: n.name for n in db.scalars(select(Node))}
    for r in items:
        r["a_name"], r["b_name"] = nodes.get(r["a"], r["a"]), nodes.get(r["b"], r["b"])
    return {"items": items, "can_close": "routes.closure" in p.permissions}


@router.get("/routes/plan")
def plan_route(dst: str, p: Principal = Depends(require("routes.view")), db: Session = Depends(get_db)):
    net = RouteNet.from_db(db)
    if dst not in net.nodes:
        raise HTTPException(404, "Unknown destination")
    return net.plan_to(dst)


@router.get("/routes/{route_id}")
def route_detail(route_id: str, rain: float | None = Query(None, ge=0, le=300), snow: float | None = Query(None, ge=0, le=200),
                 p: Principal = Depends(require("routes.view")), db: Session = Depends(get_db)):
    net = RouteNet.from_db(db)
    if route_id not in net.routes:
        raise HTTPException(404, "Route not found")
    r = net.routes[route_id]
    base = net.a(route_id)
    scenario = assess(r, rain, snow) if (rain is not None or snow is not None) else None
    alt = None
    if r["mode"] == "road":
        alt = {"fastest": net.shortest(r["a"], r["b"], "fastest"), "reliable": net.shortest(r["a"], r["b"], "reliable"),
               "avoiding_this_segment": net.shortest(r["a"], r["b"], "reliable", blocked={route_id}) if not r["closed"] else net.shortest(r["a"], r["b"], "reliable")}
    reports = [{"ts": iso(f.ts), "actor": f.actor, "condition": f.payload.get("condition"), "note": f.payload.get("note")}
               for f in db.scalars(select(FieldReport).where(FieldReport.route_id == route_id).order_by(FieldReport.ts.desc()).limit(5))]
    row = db.get(Route, route_id)
    nodes = {n.id: n.name for n in db.scalars(select(Node))}
    return {"route": route_dict(row, net), "a_name": nodes.get(r["a"]), "b_name": nodes.get(r["b"]), "assessment": base, "scenario": scenario,
            "comparison": alt, "field_reports": reports, "can_close": "routes.closure" in p.permissions,
            "caveat": "A high Route Reliability Index is a model output, not an operational safety clearance."}


class ClosureBody(BaseModel):
    days: float = Field(3, ge=0.5, le=30)
    reason: str = Field("Simulated landslide", min_length=3, max_length=200)


@router.post("/routes/{route_id}/closure")
def close_route(route_id: str, body: ClosureBody, p: Principal = Depends(require("routes.closure")), db: Session = Depends(get_db)):
    r = db.get(Route, route_id)
    if r is None:
        raise HTTPException(404, "Route not found")
    if r.status == "closed":
        raise HTTPException(409, "Route is already closed")
    r.status, r.closed_until, r.closure_reason = "closed", utcnow() + timedelta(days=body.days), body.reason
    audit.append(db, p.label, p.role, "route.closure", route_id, "success", {"days": body.days, "reason": body.reason, "simulated": True})
    db.flush()
    convoy_changes = replan_convoys(db)
    rec_changes = generate_recommendations(db)
    db.commit()
    return {"ok": True, "route": route_dict(r, RouteNet.from_db(db)), "convoy_changes": convoy_changes, "recommendation_changes": rec_changes}


@router.post("/routes/{route_id}/reopen")
def reopen_route(route_id: str, p: Principal = Depends(require("routes.closure")), db: Session = Depends(get_db)):
    r = db.get(Route, route_id)
    if r is None:
        raise HTTPException(404, "Route not found")
    if r.status != "closed":
        raise HTTPException(409, "Route is not closed")
    r.status, r.closed_until, r.closure_reason = "open", None, None
    audit.append(db, p.label, p.role, "route.reopen", route_id, "success", {"simulated": True})
    db.flush()
    convoy_changes = replan_convoys(db)
    rec_changes = generate_recommendations(db)
    db.commit()
    return {"ok": True, "route": route_dict(r, RouteNet.from_db(db)), "convoy_changes": convoy_changes, "recommendation_changes": rec_changes}


# --- convoys -----------------------------------------------------------------------------------------------------
def convoy_dict(c: Convoy, net: RouteNet) -> dict:
    delay_h = (c.est_eta - c.planned_eta).total_seconds() / 3600
    segs = [{"route_id": rid, "risk": net.a(rid)["risk"] if rid in net.routes else "unknown", "closed": net.routes.get(rid, {}).get("closed", False)} for rid in c.route_ids]
    worst = "closed" if any(s["closed"] for s in segs) else next((k for k in ("high", "elevated", "moderate", "low") if any(s["risk"] == k for s in segs)), "low")
    return {"id": c.id, "dest_post": c.dest_post, "origin": c.origin, "supply_class": c.supply_class, "qty": c.qty, "unit": CLASSES[c.supply_class]["unit"],
            "mode": c.mode, "path": c.path, "route_ids": c.route_ids, "status": c.status, "dispatched_at": iso(c.dispatched_at), "planned_eta": iso(c.planned_eta),
            "est_eta": iso(c.est_eta), "delay_h": round(delay_h, 1), "rec_id": c.rec_id, "incidents": c.incidents, "route_status": worst, "segments": segs,
            "simulated": True}


@router.get("/convoys")
def list_convoys(status: str = "", p: Principal = Depends(require("convoy.view")), db: Session = Depends(get_db)):
    expire_closures(db)
    net = RouteNet.from_db(db)
    items = [convoy_dict(c, net) for c in db.scalars(select(Convoy).order_by(Convoy.id))]
    if status:
        items = [c for c in items if c["status"] == status]
    return {"items": items, "simulation_label": "Simulated movements: fictional identifiers; no real GPS/NavIC tracking.", "can_report": "convoy.report" in p.permissions}


class IncidentBody(BaseModel):
    type: Literal["Vehicle breakdown", "Rockfall delay", "Weather hold", "Road blocked", "Other"]
    note: str = Field(min_length=5, max_length=240)


@router.post("/convoys/{convoy_id}/incident")
def report_incident(convoy_id: str, body: IncidentBody, p: Principal = Depends(require("convoy.report")), db: Session = Depends(get_db)):
    c = db.get(Convoy, convoy_id)
    if c is None:
        raise HTTPException(404, "Convoy not found")
    if c.status == "Arrived":
        raise HTTPException(409, "Convoy has already arrived")
    c.incidents = [*c.incidents, {"ts": iso(utcnow()), "type": body.type, "note": body.note, "actor": p.label}]
    if body.type in ("Road blocked", "Vehicle breakdown"):
        c.status = "Incident"
    else:
        c.status = "Delayed"
    c.est_eta = c.est_eta + timedelta(hours=3)
    audit.append(db, p.label, p.role, "convoy.incident", convoy_id, "success", {"type": body.type, "note": body.note, "simulated": True})
    db.commit()
    return convoy_dict(c, RouteNet.from_db(db))
