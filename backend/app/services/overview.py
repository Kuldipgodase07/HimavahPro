"""Aggregations for the Command Centre, map and housekeeping."""
from __future__ import annotations

from datetime import timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import iso, utcnow
from ..models import Decision, Doc, Node, Recommendation, Route, Sensor
from . import audit
from .forecast import CLASSES, HEALTH_ORDER, enrich_inventory, forecast_series, health_from, load_history, load_weather, post_health, weather_uplift
from .recommender import ENGINE_ACTOR, generate_recommendations, replan_convoys
from .routing import RouteNet

URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2}


def expire_closures(db: Session) -> list[str]:
    """Reopen routes whose simulated closure period has elapsed and refresh dependent plans."""
    now = utcnow()
    reopened = []
    for r in db.scalars(select(Route).where(Route.status == "closed")):
        if r.closed_until and r.closed_until <= now:
            r.status, r.closed_until, r.closure_reason = "open", None, None
            reopened.append(r.id)
            audit.append(db, ENGINE_ACTOR, "system", "route.reopen", r.id, "success", {"reason": "Simulated closure period elapsed"})
    if reopened:
        db.flush()
        replan_convoys(db)
        generate_recommendations(db)
        db.commit()
    return reopened


def node_dict(n: Node) -> dict:
    return {"id": n.id, "name": n.name, "kind": n.kind, "lat": n.lat, "lon": n.lon, "alt_m": n.alt_m, "tier": n.tier, "helipad": n.helipad,
            "formation": n.formation, "personnel": n.personnel}


def route_dict(r: Route, net: RouteNet) -> dict:
    a = net.a(r.id)
    return {"id": r.id, "a": r.a, "b": r.b, "mode": r.mode, "distance_km": r.distance_km, "status": r.status, "closed": r.status == "closed",
            "closed_until": iso(r.closed_until), "closure_reason": r.closure_reason, "slope_risk": r.slope_risk, "closure_count": r.closure_count,
            "rain_mm": r.rain_mm, "snow_cm": r.snow_cm, "time_h": a["time_h"], "rri": a["rri"], "risk": a["risk"], "explanation": a["explanation"]}


def _health_trend(rows: list[dict], hist: dict, days: int = 14) -> list[dict]:
    """Stock-health counts per day, reconstructed from consumption history (receipts are not modelled)."""
    out = []
    now = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    for k in range(days - 1, -1, -1):
        counts = {"healthy": 0, "attention": 0, "elevated": 0, "critical": 0}
        for r in rows:
            vals = hist.get((r["post_id"], r["supply_class"]), [])
            back = sum(vals[len(vals) - k:]) if k else 0.0
            usable = r["usable"] + back
            dos = usable / (r["forecast_daily_p50"] or 1e-9)
            counts[health_from(dos, usable, r["reorder_threshold"])] += 1
        out.append({"date": iso(now - timedelta(days=k))[:10], **counts})
    return out


def _demand_chart(db: Session, hist: dict, weather: dict) -> list[dict]:
    series = {}
    for cls in CLASSES:
        totals_hist = [0.0] * 14
        totals_fc = [0.0] * 7
        for (post, c), vals in hist.items():
            if c != cls or len(vals) < 14:
                continue
            for i in range(14):
                totals_hist[i] += vals[len(vals) - 14 + i]
            fc = forecast_series(vals, 7, weather_uplift(cls, weather.get(post)))
            for i, d in enumerate(fc["daily"]):
                totals_fc[i] += d["p50"]
        base = mean(totals_hist) or 1.0
        series[cls] = ([100 * v / base for v in totals_hist], [100 * v / base for v in totals_fc])
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for i in range(21):
        date = iso(start + timedelta(days=i - 14))[:10]
        row = {"date": date, "forecast": i >= 14}
        for cls, (h, f) in series.items():
            row[cls] = round(h[i] if i < 14 else f[i - 14], 1)
        out.append(row)
    return out


def dashboard(db: Session) -> dict:
    now = utcnow()
    rows = enrich_inventory(db)
    ph = post_health(rows)
    net = RouteNet.from_db(db)
    routes = list(db.scalars(select(Route)))
    posts = [n for n in db.scalars(select(Node)) if n.kind == "post"]
    recs = list(db.scalars(select(Recommendation).where(Recommendation.origin != "synthetic-history")))
    sensors = list(db.scalars(select(Sensor)))
    hist, weather = load_history(db), load_weather(db)

    pending = [r for r in recs if r.status == "Pending Review"]
    road = [r for r in routes if r.mode == "road"]
    elevated = [r for r in road if net.a(r.id)["risk"] in ("elevated", "high", "closed")]
    stale = [r for r in rows if r["validation"] != "valid" or r["age_h"] > 24]
    offline = [s for s in sensors if s.health != "ok"]
    kpis = {
        "active_posts": len(posts),
        "posts_attention": sum(1 for v in ph.values() if v != "healthy"),
        "critical_alerts": sum(1 for r in rows if r["health"] == "critical"),
        "routes_elevated": len(elevated), "routes_total": len(road),
        "pending_approvals": len(pending),
        "sync": {"sources_ok": len(rows) - len(stale), "sources_total": len(rows), "sensors_unhealthy": len(offline), "sensors_total": len(sensors),
                 "label": "Synchronised" if not stale and not offline else "Attention needed"},
    }
    alerts = []
    for r in sorted((r for r in rows if r["health"] in ("critical", "elevated")), key=lambda r: r["tts_p50_h"])[:8]:
        alerts.append({"severity": r["health"], "post_id": r["post_id"], "post_name": r["post_name"], "supply_class": r["supply_class"],
                       "message": f"{CLASSES[r['supply_class']]['label']}: {r['dos']} days of supply, stockout in ~{r['tts_p50_h']:.0f} h (P50).",
                       "dos": r["dos"], "tts_p50_h": r["tts_p50_h"]})
    pend = sorted(pending, key=lambda r: (URGENCY_ORDER[r.urgency], r.created_at))[:5]
    changes = sorted((r for r in rows if r["change_pct"] is not None), key=lambda r: -abs(r["change_pct"]))[:5]
    disruptions = [route_dict(r, net) for r in sorted(road, key=lambda r: (0 if r.status == "closed" else 1, net.a(r.id)["rri"] or 0))
                   if r.status == "closed" or net.a(r.id)["risk"] in ("elevated", "high")][:6]
    dq = []
    for r in rows:
        issues = []
        if r["confidence"] == "Low":
            issues.append("Low-confidence forecast: mandatory human review")
        if r["validation"] != "valid":
            issues.append(f"Stock reading {r['validation']}")
        if r["sensor_health"] in ("offline", "degraded"):
            issues.append(f"Sensor {r['sensor_health']}")
        if r["fallback"]:
            issues.append("Rule-based fallback in use")
        if issues:
            dq.append({"post_id": r["post_id"], "post_name": r["post_name"], "supply_class": r["supply_class"], "issues": issues, "confidence": r["confidence"]})
    risk_dist = {"low": 0, "moderate": 0, "elevated": 0, "high": 0, "closed": 0}
    for r in road:
        risk_dist[net.a(r.id)["risk"]] += 1
    decisions = [{"ts": iso(d.ts), "rec_id": d.rec_id, "actor": d.actor, "action": d.action, "from": d.from_status, "to": d.to_status, "reason": d.reason}
                 for d in db.scalars(select(Decision).order_by(Decision.ts.desc()).limit(8))]
    return {
        "as_of": iso(now), "simulated": True, "kpis": kpis, "alerts": alerts,
        "pending_recommendations": [rec_brief(r) for r in pend], "forecast_changes": [
            {"post_id": r["post_id"], "post_name": r["post_name"], "supply_class": r["supply_class"], "change_pct": r["change_pct"], "dos": r["dos"]} for r in changes],
        "route_disruptions": disruptions, "data_quality": dq[:8], "data_quality_total": len(dq),
        "charts": {"stock_health_trend": _health_trend(rows, hist), "demand_forecast": _demand_chart(db, hist, weather), "route_risk": risk_dist,
                   "trend_note": "Reconstructed from synthetic consumption history; receipts are not modelled."},
        "recent_decisions": decisions, "post_health": ph,
        "scenario": db.get(Doc, "demo").value,
    }


def rec_brief(r: Recommendation) -> dict:
    return {"id": r.id, "post_id": r.post_id, "supply_class": r.supply_class, "qty": r.qty, "unit": r.unit, "urgency": r.urgency, "status": r.status,
            "confidence": r.confidence, "transport_mode": r.transport_mode, "mandatory_review": r.mandatory_review, "created_at": iso(r.created_at),
            "eta_h": (r.evidence or {}).get("eta_h")}


def map_payload(db: Session) -> dict:
    rows = enrich_inventory(db)
    ph = post_health(rows)
    net = RouteNet.from_db(db)
    weather = load_weather(db)
    by_post: dict[str, list[dict]] = {}
    for r in rows:
        by_post.setdefault(r["post_id"], []).append(r)
    nodes = []
    for n in db.scalars(select(Node)):
        d = node_dict(n)
        if n.kind == "post":
            d["health"] = ph.get(n.id, "healthy")
            d["inventory"] = [{k: r[k] for k in ("supply_class", "unit", "usable", "dos", "tts_p50_h", "health", "confidence")} for r in by_post.get(n.id, [])]
            d["weather"] = weather.get(n.id)
        nodes.append(d)
    return {"as_of": iso(utcnow()), "simulated": True,
            "frame_note": "Synthetic planar coordinate frame; not geo-referenced to any real location. No live military intelligence is represented.",
            "nodes": nodes, "routes": [route_dict(r, net) for r in db.scalars(select(Route))]}
