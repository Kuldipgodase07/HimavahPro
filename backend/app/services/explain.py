"""Rule-based, calculation-backed explanations for recommendations.

No SHAP values are produced (no trained model exists). Every number shown here is recomputed from
the simulated forecaster and route formula, and labelled with its method.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Convoy, Inventory, Recommendation
from ..db import utcnow
from .forecast import CLASSES, enrich_inventory, forecast_detail
from .recommender import PREP_H, TARGET_DAYS, build_plan
from .routing import RouteNet


def explain_recommendation(db: Session, rec: Recommendation) -> dict:
    net = RouteNet.from_db(db)
    ev = rec.evidence or {}
    cls = rec.supply_class
    detail = forecast_detail(db, rec.post_id, cls, 3)
    plan = rec.plan or {}
    reasons = []
    if ev.get("dos") is not None:
        reasons.append(f"Days of Supply is {ev['dos']:.1f} (usable {ev.get('usable')} {rec.unit}); median stockout in {ev.get('tts_p50_h')} h, earliest {ev.get('tts_earliest_h')} h at P90 demand.")
    if ev.get("below_reorder"):
        reasons.append(f"Usable stock is below the reorder threshold ({ev.get('reorder_threshold')} {rec.unit}).")
    if ev.get("inbound_qty"):
        reasons.append(f"{ev['inbound_qty']:g} {rec.unit} already inbound was subtracted from the need.")
    if plan:
        reasons.append(f"Chosen route: {plan.get('label', plan.get('mode'))}, {plan.get('time_h')} h, end-to-end reliability {plan.get('reliability')}.")
    if ev.get("closed_routes"):
        reasons.append(f"Closed segments were excluded from routing: {', '.join(ev['closed_routes'])}.")
    if ev.get("scenario_run"):
        reasons.append(f"Created from what-if scenario {ev['scenario_run']}; baseline stockout day {ev.get('baseline_stockout_day')} vs scenario {ev.get('scenario_stockout_day')}.")

    route_drivers = []
    for rid in plan.get("route_ids", []):
        a = net.a(rid)
        route_drivers.append({"route_id": rid, "rri": a["rri"], "risk": a["risk"], "contributions": a["contributions"], "explanation": a["explanation"]})

    counterfactuals = []
    eta = ev.get("eta_h")
    tts = ev.get("tts_p50_h")
    if eta is not None and tts is not None:
        counterfactuals.append({"question": "What if dispatch is delayed by 24 hours?", "result": f"Margin between median stockout ({tts:.0f} h) and arrival ({eta + 24:.0f} h) would be {tts - eta - 24:+.0f} h.",
                                "method": "Arithmetic on the calculated stockout time and route time."})
    closed = [r for r in net.routes.values() if r["closed"]]
    if closed and plan and plan.get("mode") == "road":
        alt = net.copy()
        for r in alt.routes.values():
            r["closed"] = False
        alt.invalidate()
        p2 = alt.plan_to(rec.post_id)["fastest"]
        if p2:
            counterfactuals.append({"question": f"What if closed segment(s) {', '.join(r['id'] for r in closed)} were open?",
                                    "result": f"Fastest road time would be {p2['time_h']} h (vs {plan.get('time_h')} h now), via {', '.join(p2['route_ids'])}.",
                                    "method": "Dijkstra re-run with all closures lifted in an in-memory copy."})
    if detail:
        p90 = detail["forecast"]
        mean_p90 = sum(d["p90"] for d in p90) / len(p90)
        need90 = max(0.0, mean_p90 * TARGET_DAYS - ev.get("usable", 0) - ev.get("inbound_qty", 0))
        counterfactuals.append({"question": "What quantity would be needed if demand follows the P90 path?",
                                "result": f"About {need90:,.0f} {rec.unit} (vs proposed {rec.qty:g}).", "method": "Coverage heuristic re-run with P90 daily demand."})

    return {
        "recommendation_id": rec.id, "method": "Rule-based explanation with recomputed figures (not SHAP, not a trained explainer).",
        "reasons": reasons, "forecast_drivers": detail["drivers"] if detail else [], "forecast_change": detail["change"] if detail else None,
        "route_drivers": route_drivers, "counterfactuals": counterfactuals,
        "alternatives": rec.alternatives, "limitations": rec.limitations,
        "assumptions": [f"Target cover of {TARGET_DAYS} days; {PREP_H} h preparation time.", "Synthetic data and simulated models throughout.",
                        "Confidence is a rule-based label, not a calibrated probability."],
    }
