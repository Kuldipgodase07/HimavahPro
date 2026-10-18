"""Rule-based replenishment recommender ("planner engine").

It RECOMMENDS only. Nothing here dispatches anything: every recommendation must pass the human
approval workflow, and "simulated dispatch" creates a fictional convoy record inside this prototype.
Quantity uses a transparent coverage heuristic; an OR-Tools optimiser is a future boundary.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import iso, utcnow
from ..models import Convoy, Decision, Recommendation, Route
from . import audit
from .forecast import CLASSES, MODEL_VERSION, enrich_inventory
from .routing import RRI_VERSION, RouteNet

TARGET_DAYS = 10
TRIGGER_DOS = 7.0
PREP_H = 4
INBOUND_WINDOW_H = 120
AIR_CAPACITY = {"rations": 1500.0, "fuel": 800.0, "medical": 60.0, "spares": 80.0}  # placeholder per-sortie assumptions
ACTIVE_STATES = ("Draft", "Pending Review", "Info Requested", "Approved", "Simulated Dispatch")
EDITABLE_STATES = ("Draft", "Pending Review", "Info Requested")
ENGINE_ACTOR = "HimavahPro Planner Engine (simulated)"
REROUTE_PENALTY_H = 12.0  # assumed re-planning / clearance allowance when a convoy must leave its planned path


def _round_qty(cls: str, q: float) -> float:
    return float(math.ceil(q / 10) * 10) if cls in ("rations", "fuel") else float(math.ceil(q))


def _option(label: str, p: dict, tradeoff: str) -> dict:
    return {"label": label, "mode": p["mode"], "origin": p.get("origin"), "nodes": p["nodes"], "route_ids": p["route_ids"],
            "time_h": p["time_h"], "reliability": p["reliability"], "distance_km": p["distance_km"], "fuel_l": p["fuel_l"],
            "weakest_rri": p["weakest_rri"], "tradeoff": tradeoff}


def next_rec_id(db: Session) -> str:
    nums = [int(m.group(1)) for rid in db.scalars(select(Recommendation.id)) if (m := re.fullmatch(r"REC-(\d+)", rid))]
    return f"REC-{(max(nums) + 1) if nums else 1:03d}"


def build_plan(net: RouteNet, post: str, cls: str, qty: float) -> tuple[str, dict | None, list[dict], list[str], dict]:
    """Return (mode, primary option, alternatives, notes, raw plan)."""
    plan = net.plan_to(post)
    notes: list[str] = []
    fast, rel = plan["fastest"], plan["reliable"]
    options: list[dict] = []
    primary: dict | None = None
    mode = "unavailable"
    if fast:
        use_rel = rel and fast["reliability"] < 0.55 and rel["route_ids"] != fast["route_ids"]
        chosen = rel if use_rel else fast
        primary = _option("Primary: " + ("most reliable road route" if use_rel else "fastest road route"), chosen,
                          "Chosen because the fastest route is below 0.55 end-to-end reliability." if use_rel else "Lowest estimated travel time.")
        mode = "road"
        other = fast if use_rel else rel
        if other and other["route_ids"] != chosen["route_ids"]:
            options.append(_option("Fastest road route" if use_rel else "More reliable road route", other,
                                   f"{other['time_h'] - chosen['time_h']:+.1f} h travel, {other['reliability'] - chosen['reliability']:+.2f} reliability vs primary."))
        for a in plan["alternatives"]:
            options.append(_option(f"Alternative avoiding {a['avoids']}", a,
                                   f"{a['time_h'] - chosen['time_h']:+.1f} h travel, {a['reliability'] - chosen['reliability']:+.2f} reliability vs primary."))
    air = plan["air"]
    if air:
        cap = AIR_CAPACITY[cls]
        trade = ("Within assumed single-sortie capacity." if qty <= cap else
                 f"Quantity exceeds the assumed single-sortie capacity ({cap:g}); would need multiple sorties.") + " Subject to weather/visibility."
        opt = _option("Air resupply (helicopter)", air, trade)
        if primary is None:
            primary, mode = opt, "air"
            notes.append("No road route is currently available; air resupply is the only feasible option in the simulated network.")
        else:
            options.append(opt)
    if primary is None:
        notes.append("No feasible road or air route in the current simulated network state: escalate to the planner.")
    return mode, primary, options[:5], notes, plan


def _confidence(fc_conf: str, primary: dict | None) -> str:
    order = ["Low", "Medium", "High"]
    lvl = order.index(fc_conf)
    if primary is None:
        return "Low"
    if primary["reliability"] < 0.5:
        lvl = max(0, lvl - 1)
    return order[lvl]


def generate_recommendations(db: Session, actor: str = ENGINE_ACTOR, role: str = "system") -> list[dict]:
    rows = enrich_inventory(db)
    net = RouteNet.from_db(db)
    now = utcnow()
    convoys = list(db.scalars(select(Convoy).where(Convoy.status.in_(["Planned", "In Transit", "Delayed"]))))
    recs = {(r.post_id, r.supply_class): r for r in db.scalars(select(Recommendation).where(Recommendation.status.in_(ACTIVE_STATES)))
            if r.origin != "synthetic-history"}
    changes: list[dict] = []
    for row in rows:
        key = (row["post_id"], row["supply_class"])
        cls, post = key[1], key[0]
        existing = recs.get(key)
        needs = row["dos"] < TRIGGER_DOS or row["below_reorder"]
        inbound = sum(c.qty for c in convoys if c.dest_post == post and c.supply_class == cls and c.est_eta <= now + timedelta(hours=INBOUND_WINDOW_H))
        qty = max(0.0, row["forecast_daily_p50"] * TARGET_DAYS - row["usable"] - inbound)
        if not needs or qty < 1:
            if existing and existing.status in EDITABLE_STATES and existing.origin == "planner-engine":
                _transition(db, existing, "Withdrawn", actor, role, "Withdraw", "Stock risk no longer present (stock/convoy data changed).")
                changes.append({"id": existing.id, "change": "withdrawn"})
            continue
        qty = _round_qty(cls, qty)
        mode, primary, alts, notes, plan = build_plan(net, post, cls, qty)
        eta_h = round(primary["time_h"] + PREP_H, 1) if primary else None
        margin = None if eta_h is None else row["tts_p50_h"] - eta_h
        if row["dos"] < 3 or margin is None or margin < 0:
            urgency = "critical"
        elif margin < 48:
            urgency = "high"
        else:
            urgency = "medium"
        conf = _confidence(row["confidence"], primary)
        label = CLASSES[cls]["label"]
        closed = sorted(r["id"] for r in net.routes.values() if r["closed"])
        reason = (f"{label} at {post} ({row['post_name']}) is projected to run out in about {row['tts_p50_h']:.0f} h (median) and as early as "
                  f"{row['tts_earliest_h']:.0f} h under high demand (P90); Days of Supply {row['dos']:.1f}. ")
        if primary:
            reason += f"Estimated resupply time via {primary['mode']} is {eta_h:.0f} h including {PREP_H} h preparation. "
        reason += f"Proposed {qty:g} {row['unit']} restores about {TARGET_DAYS} days of cover" + (f" after counting {inbound:g} {row['unit']} already inbound." if inbound else ".")
        if closed:
            reason += f" Currently closed segments: {', '.join(closed)}."
        limits = ["Quantity follows a simple coverage heuristic (target %d days), not an optimiser." % TARGET_DAYS,
                  "Route reliability combines segment scores assuming independence and is not an operational safety assessment.",
                  f"Forecast: {MODEL_VERSION}. Reliability: {RRI_VERSION}. Both are simulated demo components."]
        if mode == "air":
            limits.append("Air capacity per sortie is a placeholder assumption.")
        limits += row["confidence_reasons"] if row["confidence"] != "High" else []
        evidence = {"dos": row["dos"], "tts_p50_h": row["tts_p50_h"], "tts_earliest_h": row["tts_earliest_h"], "usable": row["usable"],
                    "unit": row["unit"], "forecast_daily_p50": row["forecast_daily_p50"], "avg_daily": row["avg_daily"], "inbound_qty": inbound,
                    "target_days": TARGET_DAYS, "reorder_threshold": row["reorder_threshold"], "below_reorder": row["below_reorder"],
                    "health": row["health"], "forecast_confidence": row["confidence"], "forecast_change_pct": row["change_pct"],
                    "eta_h": eta_h, "margin_h": None if margin is None else round(margin, 1), "closed_routes": closed,
                    "data_updated_at": row["updated_at"], "stock_source": row["source"]}
        payload = dict(qty=qty, unit=row["unit"], urgency=urgency, reason=reason, transport_mode=mode, plan=primary or {}, alternatives=alts,
                       evidence=evidence, limitations=limits + notes, confidence=conf, mandatory_review=conf == "Low" or mode == "unavailable",
                       model_version=MODEL_VERSION, data_as_of=now, updated_at=now)
        if existing is None:
            rid = next_rec_id(db)
            rec = Recommendation(id=rid, post_id=post, supply_class=cls, status="Pending Review", origin="planner-engine", created_at=now, **payload)
            db.add(rec)
            db.add(Decision(rec_id=rid, ts=now, actor=actor, role=role, action="Generate", reason=None, from_status="-", to_status="Pending Review",
                            detail={"qty": qty, "urgency": urgency}))
            audit.append(db, actor, role, "recommendation.generated", rid, "success", {"post": post, "class": cls, "qty": qty, "urgency": urgency, "confidence": conf})
            changes.append({"id": rid, "change": "created"})
        elif existing.status in EDITABLE_STATES:
            rerouted = (existing.plan or {}).get('route_ids') != (primary or {}).get('route_ids')
            material = rerouted or abs(existing.qty - qty) > 0.1 * max(existing.qty, 1) or existing.transport_mode != mode or existing.urgency != urgency
            if existing.original_qty is None:  # human-edited quantity is preserved
                for k, v in payload.items():
                    setattr(existing, k, v)
            else:
                for k, v in payload.items():
                    if k != "qty":
                        setattr(existing, k, v)
            if material:
                audit.append(db, actor, role, "recommendation.updated", existing.id, "success",
                             {"qty": existing.qty, "urgency": urgency, "transport": mode, "rerouted": rerouted, "trigger": "network/stock state changed"})
                changes.append({"id": existing.id, "change": "updated"})
    db.flush()
    return changes


def _transition(db: Session, rec: Recommendation, to: str, actor: str, role: str, action: str, reason: str | None, detail: dict | None = None) -> None:
    db.add(Decision(rec_id=rec.id, ts=utcnow(), actor=actor, role=role, action=action, reason=reason, from_status=rec.status, to_status=to, detail=detail or {}))
    rec.status = to
    rec.updated_at = utcnow()


def replan_convoys(db: Session) -> list[dict]:
    """After a closure or reopening, re-evaluate active convoys (simulated)."""
    net = RouteNet.from_db(db)
    now = utcnow()
    changes = []
    routes = {r.id: r for r in db.scalars(select(Route))}
    for c in db.scalars(select(Convoy).where(Convoy.status.in_(["Planned", "In Transit", "Delayed"]))):
        if c.mode != "road":
            continue
        blocked_ids = [rid for rid in c.route_ids if net.routes[rid]["closed"]]
        auto = [i for i in c.incidents if i.get("auto") == "closure"]
        if blocked_ids:
            alt = net.shortest(c.origin, c.dest_post, "fastest")
            old_time = sum(net.a(r)["time_h"] for r in c.route_ids if r in net.routes)
            if alt:
                delay = max(2.0, alt["time_h"] - old_time) + REROUTE_PENALTY_H
                note = f"Rerouted around closed {', '.join(blocked_ids)} via {' → '.join(alt['nodes'])}; estimated delay {delay:.1f} h incl. {REROUTE_PENALTY_H:g} h re-planning allowance (simulated)."
                c.path, c.route_ids = alt["nodes"], alt["route_ids"]
            else:
                until = max((routes[r].closed_until or now) for r in blocked_ids)
                delay = max(2.0, (until - now).total_seconds() / 3600 + 6)
                note = f"No alternative road path; held until closure of {', '.join(blocked_ids)} clears. Estimated delay {delay:.0f} h (simulated)."
            c.est_eta = c.planned_eta + timedelta(hours=delay)
            c.status = "Delayed"
            c.incidents = [*[i for i in c.incidents if i.get("auto") != "closure"],
                           {"ts": iso(now), "type": "Route closure", "note": note, "actor": ENGINE_ACTOR, "auto": "closure"}]
            changes.append({"convoy": c.id, "change": "delayed", "delay_h": round(delay, 1)})
        elif auto and c.status == "Delayed":
            c.est_eta = c.planned_eta
            c.status = "In Transit" if c.dispatched_at else "Planned"
            c.incidents = [i for i in c.incidents if i.get("auto") != "closure"] + [
                {"ts": iso(now), "type": "Closure cleared", "note": "Closure cleared; estimated arrival restored to plan (simulated).", "actor": ENGINE_ACTOR}]
            changes.append({"convoy": c.id, "change": "restored"})
    db.flush()
    return changes
