"""What-if logistics simulator (simulation only; never touches live/production operations).

A day-by-day stock projection over 14 days per post/supply class: consumption comes from the
simulated forecaster's P50 path, inbound deliveries come from the simulated convoy records.
Scenarios change routes, demand, delivery timing or data availability in an in-memory copy; the
only persisted output is the scenario run record and (optionally) Draft recommendations.
"""
from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import iso, utcnow
from ..models import Convoy, Decision, Inventory, Recommendation, Route, ScenarioRun
from . import audit
from .forecast import CLASSES, MODEL_VERSION, enrich_inventory, forecast_series, load_history, load_weather, weather_uplift
from .recommender import ENGINE_ACTOR, REROUTE_PENALTY_H, TARGET_DAYS, _confidence, _round_qty, build_plan, next_rec_id
from .routing import RouteNet

HORIZON = 14
KINDS = {
    "route_closure": "A route becomes unavailable",
    "demand_surge": "Demand increases",
    "delivery_delay": "A stock delivery is delayed",
    "sensor_outage": "An inventory sensor becomes unavailable",
    "weather_disruption": "A weather disruption affects route segments",
}


class ScenarioError(ValueError):
    pass


def validate(kind: str, p: dict, net: RouteNet) -> dict:
    if kind not in KINDS:
        raise ScenarioError(f"Unknown scenario kind '{kind}'.")
    p = dict(p)
    if kind == "route_closure":
        if p.get("route_id") not in net.routes:
            raise ScenarioError("route_id must be an existing route.")
        p["days"] = float(p.get("days", 3))
        if not 0.5 <= p["days"] <= 30:
            raise ScenarioError("days must be between 0.5 and 30.")
    elif kind == "demand_surge":
        p["pct"] = float(p.get("pct", 20))
        if not 1 <= p["pct"] <= 200:
            raise ScenarioError("pct must be between 1 and 200.")
        p["supply_class"] = p.get("supply_class") or "all"
        if p["supply_class"] != "all" and p["supply_class"] not in CLASSES:
            raise ScenarioError("Unknown supply class.")
    elif kind == "delivery_delay":
        p["hours"] = float(p.get("hours", 24))
        if not 1 <= p["hours"] <= 240:
            raise ScenarioError("hours must be between 1 and 240.")
        p["convoy_id"] = p.get("convoy_id") or None
    elif kind == "sensor_outage":
        if not str(p.get("post_id", "")).startswith("POST-"):
            raise ScenarioError("post_id must be a post identifier (POST-Kxx).")
        p["hours"] = float(p.get("hours", 48))
    elif kind == "weather_disruption":
        ids = p.get("route_ids") or []
        if not ids or any(i not in net.routes for i in ids):
            raise ScenarioError("route_ids must list existing routes.")
        p["rain_mm"], p["snow_cm"] = float(p.get("rain_mm", 60)), float(p.get("snow_cm", 30))
        p["days"] = float(p.get("days", 2))
        if not (0 <= p["rain_mm"] <= 300 and 0 <= p["snow_cm"] <= 200):
            raise ScenarioError("Weather inputs out of range.")
    return p


def _daily_paths(db: Session) -> dict[tuple[str, str], list[float]]:
    hist, weather = load_history(db), load_weather(db)
    out = {}
    for post, cls in {(i.post_id, i.supply_class) for i in db.scalars(select(Inventory))}:
        fc = forecast_series(hist.get((post, cls), []), HORIZON, weather_uplift(cls, weather.get(post)))
        out[(post, cls)] = [d["p50"] for d in fc["daily"]]
    return out


def _project(usable: float, cons: list[float], arrivals: list[tuple[float, float]]) -> dict:
    stock, series, stockout = usable, [round(usable, 1)], None
    for d in range(HORIZON):
        before = stock
        stock -= cons[d]
        stock += sum(q for t, q in arrivals if 24 * d <= t < 24 * (d + 1) and t >= 0)
        if stockout is None and stock < 0:
            stockout = d + (before / cons[d] if cons[d] > 0 else 0)
        series.append(round(stock, 1))
    return {"stockout_day": None if stockout is None else round(stockout, 1), "min_stock": round(min(series), 1), "series": series}


def run_scenario(db: Session, kind: str, params: dict) -> dict:
    base_net = RouteNet.from_db(db)
    p = validate(kind, params, base_net)
    now = utcnow()
    rows = {(r["post_id"], r["supply_class"]): r for r in enrich_inventory(db)}
    cons_base = _daily_paths(db)
    convoys = list(db.scalars(select(Convoy).where(Convoy.status.in_(["Planned", "In Transit", "Delayed"]))))
    arr_base: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for c in convoys:
        arr_base.setdefault((c.dest_post, c.supply_class), []).append(((c.est_eta - now).total_seconds() / 3600, c.qty))

    net = base_net.copy()
    cons_s = {k: list(v) for k, v in cons_base.items()}
    arr_s = {k: list(v) for k, v in arr_base.items()}
    stock_adj: dict[tuple[str, str], float] = {}
    low_conf_keys: set[tuple[str, str]] = set()
    notes: list[str] = []
    convoy_effects: list[dict] = []

    def delay_convoys(selector, extra_fn):
        arr_s.clear()
        for c in convoys:
            base_t = (c.est_eta - now).total_seconds() / 3600
            extra = extra_fn(c) if selector(c) else 0.0
            if extra:
                convoy_effects.append({"convoy": c.id, "post": c.dest_post, "delay_h": round(extra, 1)})
            arr_s.setdefault((c.dest_post, c.supply_class), []).append((base_t + extra, c.qty))

    if kind == "route_closure":
        rid = p["route_id"]
        net.routes[rid]["closed"] = True
        net.invalidate()

        def extra(c):
            old = sum(base_net.a(r)["time_h"] for r in c.route_ids)
            alt = net.shortest(c.origin, c.dest_post, "fastest") if c.mode == "road" else None
            return (max(2.0, alt["time_h"] - old) + REROUTE_PENALTY_H) if alt else p["days"] * 24 + 6

        delay_convoys(lambda c: c.mode == "road" and rid in c.route_ids, extra)
        notes.append(f"{rid} treated as unavailable for {p['days']:g} day(s); convoys using it are rerouted if an alternative exists (detour time + {REROUTE_PENALTY_H:g} h re-planning allowance), otherwise held until it reopens.")
    elif kind == "demand_surge":
        for (post, cls), v in cons_s.items():
            if p["supply_class"] in ("all", cls):
                cons_s[(post, cls)] = [x * (1 + p["pct"] / 100) for x in v]
        notes.append(f"Consumption multiplied by {1 + p['pct'] / 100:.2f} for {'all supply classes' if p['supply_class'] == 'all' else CLASSES[p['supply_class']]['label']}, applied uniformly across posts.")
    elif kind == "delivery_delay":
        delay_convoys(lambda c: p["convoy_id"] is None or c.id == p["convoy_id"], lambda c: p["hours"])
        notes.append(f"{'All active convoys' if p['convoy_id'] is None else p['convoy_id']} delayed by {p['hours']:g} h.")
    elif kind == "sensor_outage":
        for (post, cls), r in rows.items():
            if post == p["post_id"] and r["source"] == "sensor":
                stock_adj[(post, cls)] = -0.15 * r["usable"]
                low_conf_keys.add((post, cls))
        notes.append("Smart-bin readings at the post are unavailable: stock is assumed 15 % below the last reading (pessimistic bound) and confidence is Low. Posts with manual/simulated sources are unaffected.")
        if not low_conf_keys:
            notes.append("This post has no sensor-sourced stock records, so there is no modelled effect.")
    elif kind == "weather_disruption":
        closed_here = []
        for rid in p["route_ids"]:
            net.routes[rid]["rain_mm"], net.routes[rid]["snow_cm"] = p["rain_mm"], p["snow_cm"]
        net.invalidate()
        for rid in p["route_ids"]:
            if (net.a(rid)["rri"] or 0) < 0.3:
                net.routes[rid]["closed"] = True
                closed_here.append(rid)
        net.invalidate()

        def extra(c):
            old = sum(base_net.a(r)["time_h"] for r in c.route_ids)
            if any(r in closed_here for r in c.route_ids):
                alt = net.shortest(c.origin, c.dest_post, "fastest")
                return (max(2.0, alt["time_h"] - old) + REROUTE_PENALTY_H) if alt else p["days"] * 24 + 6
            new = sum(net.a(r)["time_h"] for r in c.route_ids)
            return max(0.0, new - old)

        delay_convoys(lambda c: c.mode == "road" and any(r in p["route_ids"] for r in c.route_ids), extra)
        notes.append(f"Weather inputs ({p['rain_mm']:g} mm rain, {p['snow_cm']:g} cm snow) applied to {', '.join(p['route_ids'])}; segments scoring RRI < 0.30 are treated as impassable ({', '.join(closed_here) or 'none'}).")

    posts: dict[str, dict] = {}
    day_counts_b, day_counts_s = [0] * (HORIZON + 1), [0] * (HORIZON + 1)
    for key, row in rows.items():
        post, cls = key
        usable_b = row["usable"]
        b = _project(usable_b, cons_base[key], arr_base.get(key, []))
        s = _project(max(0.0, usable_b + stock_adj.get(key, 0.0)), cons_s[key], arr_s.get(key, []))
        for d in range(HORIZON + 1):
            day_counts_b[d] += b["series"][d] < 0
            day_counts_s[d] += s["series"][d] < 0
        earlier = (s["stockout_day"] is not None and (b["stockout_day"] is None or s["stockout_day"] < b["stockout_day"] - 0.05))
        delayed_in = [e for e in convoy_effects if e["post"] == post and e.get("delay_h", 0) >= 1]
        changed = earlier or abs(s["min_stock"] - b["min_stock"]) > 0.5 or bool(delayed_in)
        entry = {"supply_class": cls, "unit": row["unit"], "baseline": b, "scenario": s, "affected": bool(changed),
                 "new_stockout": s["stockout_day"] is not None and b["stockout_day"] is None, "worse": earlier, "delivery_delay_h": max((e["delay_h"] for e in delayed_in), default=0),
                 "confidence": "Low" if key in low_conf_keys else row["confidence"]}
        if s["stockout_day"] is not None:
            shortfall = -s["min_stock"] + sum(cons_s[key][:3]) / 3 * 3
            entry["suggested_qty"] = _round_qty(cls, shortfall)
        posts.setdefault(post, {"post_id": post, "post_name": row["post_name"], "tier": row["tier"], "series": []})["series"].append(entry)

    out_posts = []
    for post, d in posts.items():
        worst = min(d["series"], key=lambda e: (e["scenario"]["stockout_day"] if e["scenario"]["stockout_day"] is not None else 99))
        d["affected"] = any(e["affected"] for e in d["series"])
        d["worst_class"] = worst["supply_class"]
        d["projected_dos_baseline"] = worst["baseline"]["stockout_day"] if worst["baseline"]["stockout_day"] is not None else None
        d["projected_dos_scenario"] = worst["scenario"]["stockout_day"] if worst["scenario"]["stockout_day"] is not None else None
        d["stockout_risk"] = any(e["scenario"]["stockout_day"] is not None for e in d["series"])
        if d["affected"]:
            d["alternatives"] = [{k: o[k] for k in ("label", "mode", "route_ids", "time_h", "reliability", "tradeoff")}
                                 for o in build_plan(net, post, worst["supply_class"], worst.get("suggested_qty", 0) or 1)[2][:3]]
        out_posts.append(d)
    out_posts.sort(key=lambda d: (not d["affected"], d["projected_dos_scenario"] if d["projected_dos_scenario"] is not None else 99))
    n_aff = sum(1 for d in out_posts if d["affected"])
    limitations = ["Simulation only: uses synthetic data, the simulated forecaster's P50 path and simulated convoy records.",
                   "Consumption is projected at P50; demand uncertainty (P10–P90) is not propagated through the 14-day projection.",
                   "Convoy delays are approximated from re-planned travel times; handling time and convoy capacity are not modelled.",
                   f"Forecast: {MODEL_VERSION}."]
    if low_conf_keys:
        limitations.append("Sensor outage: confidence is Low and results depend on a pessimistic 15 % stock assumption.")
    return {"kind": kind, "label": KINDS[kind], "params": p, "horizon_days": HORIZON, "simulated": True, "notes": notes,
            "convoy_effects": convoy_effects, "posts": out_posts, "affected_posts": n_aff,
            "summary": {"posts_affected": n_aff,
                        "baseline_stockout_series": sum(1 for d in out_posts for e in d["series"] if e["baseline"]["stockout_day"] is not None),
                        "scenario_stockout_series": sum(1 for d in out_posts for e in d["series"] if e["scenario"]["stockout_day"] is not None),
                        "new_stockout_series": sum(1 for d in out_posts for e in d["series"] if e["new_stockout"])},
            "chart": {"days": list(range(HORIZON + 1)), "baseline_in_stockout": day_counts_b, "scenario_in_stockout": day_counts_s},
            "limitations": limitations}


def save_run(db: Session, actor_label: str, role: str, result: dict) -> str:
    n = (db.scalar(select(func.count()).select_from(ScenarioRun)) or 0) + 1
    rid = f"SCN-{n:04d}"
    db.add(ScenarioRun(id=rid, actor=actor_label, kind=result["kind"], params=result["params"], summary={"summary": result["summary"], "affected": result["affected_posts"]}))
    audit.append(db, actor_label, role, "scenario.run", rid, "success", {"kind": result["kind"], "params": result["params"], "affected_posts": result["affected_posts"]})
    return rid


def create_drafts(db: Session, run_id: str, result: dict, actor_label: str, role: str, max_drafts: int = 6) -> list[dict]:
    """Create Draft recommendations from a scenario result (humans must still submit and approve them)."""
    base_net = RouteNet.from_db(db)
    net = base_net.copy()
    p = result["params"]
    if result["kind"] == "route_closure":
        net.routes[p["route_id"]]["closed"] = True
    elif result["kind"] == "weather_disruption":
        for rid in p["route_ids"]:
            net.routes[rid]["rain_mm"], net.routes[rid]["snow_cm"] = p["rain_mm"], p["snow_cm"]
    net.invalidate()
    rows = {(r["post_id"], r["supply_class"]): r for r in enrich_inventory(db)}
    existing = {(r.post_id, r.supply_class): r for r in db.scalars(select(Recommendation).where(Recommendation.status.in_(["Draft", "Pending Review", "Info Requested", "Approved", "Simulated Dispatch"])))}
    now = utcnow()
    made = []
    cands = [(d, e) for d in result["posts"] for e in d["series"] if e.get("suggested_qty") and e["affected"]]
    cands.sort(key=lambda t: t[1]["scenario"]["stockout_day"] or 99)
    for d, e in cands[:max_drafts]:
        key = (d["post_id"], e["supply_class"])
        if key in existing:
            made.append({"post_id": key[0], "supply_class": key[1], "skipped": f"{existing[key].id} already open ({existing[key].status})"})
            continue
        row = rows[key]
        mode, primary, alts, notes, _ = build_plan(net, key[0], key[1], e["suggested_qty"])
        conf = "Low" if e["confidence"] == "Low" else _confidence(row["confidence"], primary)
        eta = round(primary["time_h"] + 4, 1) if primary else None
        rid = next_rec_id(db)
        db.add(Recommendation(
            id=rid, post_id=key[0], supply_class=key[1], qty=e["suggested_qty"], unit=row["unit"], urgency="high" if e["scenario"]["stockout_day"] < 5 else "medium",
            reason=(f"Scenario {run_id} ({result['label']}) projects stockout of {CLASSES[key[1]]['label']} at {key[0]} in "
                    f"{e['scenario']['stockout_day']:.1f} days. Proposed {e['suggested_qty']:g} {row['unit']} covers the projected shortfall plus a 3-day buffer."),
            transport_mode=mode, plan=primary or {}, alternatives=alts,
            evidence={"scenario_run": run_id, "scenario_stockout_day": e["scenario"]["stockout_day"], "baseline_stockout_day": e["baseline"]["stockout_day"],
                      "dos": row["dos"], "tts_p50_h": row["tts_p50_h"], "tts_earliest_h": row["tts_earliest_h"], "usable": row["usable"], "unit": row["unit"],
                      "eta_h": eta, "forecast_confidence": row["confidence"], "closed_routes": [r["id"] for r in net.routes.values() if r["closed"]]},
            limitations=["Created from a what-if scenario: it reflects a hypothetical state until validated.", *result["limitations"], *notes],
            confidence=conf, mandatory_review=conf == "Low", status="Draft", model_version=MODEL_VERSION, data_as_of=now, origin=f"scenario:{run_id}",
            created_at=now, updated_at=now))
        db.add(Decision(rec_id=rid, ts=now, actor=actor_label, role=role, action="Create draft", reason=f"From scenario {run_id}", from_status="-", to_status="Draft"))
        audit.append(db, actor_label, role, "recommendation.draft_created", rid, "success", {"scenario": run_id, "post": key[0], "class": key[1]})
        made.append({"id": rid, "post_id": key[0], "supply_class": key[1], "qty": e["suggested_qty"]})
    db.flush()
    return made
