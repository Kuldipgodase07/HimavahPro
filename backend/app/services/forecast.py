"""Simulated demand forecasting service.

HONESTY NOTE: this is a transparent statistical stand-in, NOT a Temporal Fusion Transformer.
Method: weekday-profile deseasonalisation -> exponentially weighted level -> damped linear
trend -> weather uplift -> normal-approximation P10/P50/P90 from in-sample residuals.
A trained model can replace `forecast_series` behind the same interface.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import iso, utcnow
from ..models import Consumption, Doc, Inventory, Node, Sensor

MODEL_VERSION = "HV-SimForecaster v0.3 (demo statistical model)"
Z90 = 1.2816
MIN_HISTORY = 14

CLASSES: dict[str, dict] = {
    "rations": {"label": "Rations", "unit": "kg", "per_person": 0.9},
    "fuel": {"label": "Fuel", "unit": "L", "per_person": 3.4},
    "medical": {"label": "Medical supplies", "unit": "kits", "per_person": 0.022},
    "spares": {"label": "Maintenance spares", "unit": "sets", "per_person": 0.03},
}

HEALTH_ORDER = {"healthy": 0, "attention": 1, "elevated": 2, "critical": 3}


def health_from(dos: float, usable: float, reorder: float) -> str:
    if dos < 3:
        return "critical"
    if dos < 5:
        return "elevated"
    if dos < 7 or usable < reorder:
        return "attention"
    return "healthy"


def weather_uplift(cls: str, weather: dict | None) -> float:
    if not weather:
        return 1.0
    t, snow = weather.get("temp_c", 0), weather.get("snow_cm", 0)
    if cls == "fuel":
        return 1 + 0.018 * max(0.0, -8 - t) + 0.004 * snow
    if cls == "rations":
        return 1 + 0.004 * max(0.0, -10 - t)
    if cls == "medical":
        return 1 + 0.006 * snow
    return 1 + 0.003 * snow


def _weekday_factors(vals: list[float]) -> list[float]:
    window = vals[-28:]
    offset = len(vals) - len(window)
    overall = mean(window) or 1.0
    buckets: dict[int, list[float]] = defaultdict(list)
    for i, v in enumerate(window):
        buckets[(offset + i) % 7].append(v)
    raw = [mean(buckets[p]) / overall if buckets.get(p) else 1.0 for p in range(7)]
    norm = mean(raw) or 1.0
    return [r / norm for r in raw]


def forecast_series(vals: list[float], horizon: int = 7, uplift: float = 1.0, use_trend: bool = True) -> dict:
    """Forecast `horizon` daily values from consecutive daily history (oldest -> newest)."""
    n = len(vals)
    if n < MIN_HISTORY:  # rule-based fallback: flat naive baseline, wide uncertainty
        base = mean(vals) if vals else 0.0
        sigma = max(base * 0.30, 0.01)
        days = [{"day": h, "p50": base * uplift, "p10": max(0.0, base * uplift - Z90 * sigma),
                 "p90": base * uplift + Z90 * sigma} for h in range(1, horizon + 1)]
        return {"daily": days, "level": base, "sigma": sigma, "cv": 0.30, "fallback": True, "trend_per_day": 0.0}

    f = _weekday_factors(vals)
    des = [v / (f[i % 7] or 1.0) for i, v in enumerate(vals)]
    alpha, level = 0.3, mean(des[: min(7, n)])
    resid: list[float] = []
    for i, d in enumerate(des):
        pred = level * f[i % 7]
        if i >= n - 28:
            resid.append(vals[i] - pred)
        level = alpha * d + (1 - alpha) * level
    w = des[-14:]
    xs = list(range(len(w)))
    xm, ym = mean(xs), mean(w)
    den = sum((x - xm) ** 2 for x in xs) or 1.0
    slope = sum((x - xm) * (y - ym) for x, y in zip(xs, w)) / den
    slope = max(-0.03 * level, min(0.03 * level, slope)) if use_trend else 0.0
    sigma = max(pstdev(resid) if len(resid) > 1 else 0.0, 0.03 * level)
    phi, days = 0.85, []
    for h in range(1, horizon + 1):
        trend = slope * sum(phi ** k for k in range(1, h + 1))
        p50 = max(0.0, (level + trend) * f[(n + h - 1) % 7] * uplift)
        sh = sigma * (1 + 0.08 * (h - 1))
        days.append({"day": h, "p50": p50, "p10": max(0.0, p50 - Z90 * sh), "p90": p50 + Z90 * sh})
    return {"daily": days, "level": level, "sigma": sigma, "cv": sigma / level if level else 1.0,
            "fallback": False, "trend_per_day": slope}


def baseline_series(vals: list[float], horizon: int = 7) -> list[float]:
    base = mean(vals[-7:]) if vals else 0.0
    return [base] * horizon


def backtest(vals: list[float], days: int = 14) -> dict:
    """One-day-ahead back-test on the synthetic history (no weather uplift available historically)."""
    m_err, b_err, k = 0.0, 0.0, 0
    for t in range(len(vals) - days, len(vals)):
        if t < MIN_HISTORY or vals[t] <= 0:
            continue
        pred = forecast_series(vals[:t], 1)["daily"][0]["p50"]
        base = mean(vals[max(0, t - 7):t])
        m_err += abs(pred - vals[t]) / vals[t]
        b_err += abs(base - vals[t]) / vals[t]
        k += 1
    if not k:
        return {"model_mape": None, "baseline_mape": None, "n": 0}
    return {"model_mape": round(100 * m_err / k, 1), "baseline_mape": round(100 * b_err / k, 1), "n": k}


def explain_change(vals: list[float], uplift_now: float, days_ago: int = 3) -> dict:
    """Genuinely recompute the forecast as it stood `days_ago` days earlier and attribute the difference."""
    if len(vals) < MIN_HISTORY + days_ago:
        return {"available": False, "reason": "Insufficient history for a before/after comparison."}
    mean7 = lambda r: mean(d["p50"] for d in r["daily"])
    then = mean7(forecast_series(vals[:-days_ago], 7, 1.0))
    level_only = mean7(forecast_series(vals, 7, 1.0, use_trend=False))
    with_trend = mean7(forecast_series(vals, 7, 1.0, use_trend=True))
    now_full = mean7(forecast_series(vals, 7, uplift_now, use_trend=True))
    comps = [("Recent consumption level", level_only - then), ("Consumption trend", with_trend - level_only),
             ("Weather uplift", now_full - with_trend)]
    return {"available": True, "days_ago": days_ago, "then_daily": then, "now_daily": now_full,
            "change_pct": 100 * (now_full - then) / then if then else 0.0,
            "components": [{"driver": k, "delta": v, "pct_of_prior": 100 * v / then if then else 0.0} for k, v in comps],
            "method": "Forecast recomputed with data available "
                      f"{days_ago} days ago vs now; differences attributed by successively enabling model components "
                      "(not SHAP)."}


def time_to_stockout_h(usable: float, daily: list[float], horizon_cap_days: int = 30) -> float:
    if usable <= 0:
        return 0.0
    remaining, hours = usable, 0.0
    for d in daily:
        if d <= 0:
            hours += 24
            continue
        if remaining <= d:
            return hours + 24 * remaining / d
        remaining -= d
        hours += 24
    last = daily[-1] if daily and daily[-1] > 0 else 1e-9
    return min(hours + 24 * remaining / last, horizon_cap_days * 24.0)


# --- data loading -----------------------------------------------------------------------------------------------

def load_history(db: Session) -> dict[tuple[str, str], list[float]]:
    out: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in db.execute(select(Consumption.post_id, Consumption.supply_class, Consumption.qty).order_by(Consumption.day)):
        out[(r[0], r[1])].append(r[2])
    return out


def load_weather(db: Session) -> dict[str, dict]:
    doc = db.get(Doc, "weather")
    return doc.value if doc else {}


def confidence_for(inv: Inventory, fc: dict, sensor_health: str | None, now: datetime) -> tuple[str, list[str]]:
    reasons: list[str] = []
    level = 2  # 2 High, 1 Medium, 0 Low
    if fc["fallback"]:
        return "Low", ["Fewer than 14 days of history: rule-based fallback (flat baseline) in use."]
    if fc["cv"] > 0.25:
        level = 0
        reasons.append(f"High demand variability (CV {fc['cv']:.0%}).")
    elif fc["cv"] > 0.12:
        level = min(level, 1)
        reasons.append(f"Moderate demand variability (CV {fc['cv']:.0%}).")
    if inv.validation != "valid":
        level = 0
        reasons.append(f"Stock reading flagged '{inv.validation}'.")
    if sensor_health in {"offline", "degraded"}:
        level = min(level, 0 if sensor_health == "offline" else 1)
        reasons.append(f"Smart-bin sensor {sensor_health}.")
    age_h = (now - inv.updated_at).total_seconds() / 3600
    if age_h > 24:
        level = max(0, level - 1)
        reasons.append(f"Stock reading is {age_h:.0f} h old.")
    label = ["Low", "Medium", "High"][level]
    if not reasons:
        reasons.append("Stable history, valid and recent stock reading.")
    return label, reasons


def enrich_inventory(db: Session, now: datetime | None = None) -> list[dict]:
    """One enriched row per inventory record: forecast-based Days of Supply, Time-to-Stockout, health, confidence."""
    now = now or utcnow()
    hist, weather = load_history(db), load_weather(db)
    nodes = {n.id: n for n in db.scalars(select(Node))}
    sensors = {s.id: s for s in db.scalars(select(Sensor))}
    rows = []
    for inv in db.scalars(select(Inventory).order_by(Inventory.post_id, Inventory.supply_class)):
        vals = hist.get((inv.post_id, inv.supply_class), [])
        up = weather_uplift(inv.supply_class, weather.get(inv.post_id))
        fc = forecast_series(vals, 7, up)
        p50 = [d["p50"] for d in fc["daily"]]
        usable = max(0.0, inv.quantity - inv.reserved)
        mean_p50 = mean(p50) or 1e-9
        dos = usable / mean_p50
        sensor = sensors.get(inv.sensor_id) if inv.sensor_id else None
        conf, reasons = confidence_for(inv, fc, sensor.health if sensor else None, now)
        chg = explain_change(vals, up)
        node = nodes.get(inv.post_id)
        rows.append({
            "id": inv.id, "post_id": inv.post_id, "post_name": node.name if node else inv.post_id, "tier": node.tier if node else None,
            "supply_class": inv.supply_class, "unit": inv.unit, "quantity": round(inv.quantity, 1), "reserved": round(inv.reserved, 1),
            "usable": round(usable, 1), "avg_daily": round(mean(vals[-7:]), 2) if vals else 0.0,
            "forecast_daily_p50": round(mean_p50, 2), "dos": round(dos, 1),
            "tts_p50_h": round(time_to_stockout_h(usable, p50), 1),
            "tts_earliest_h": round(time_to_stockout_h(usable, [d["p90"] for d in fc["daily"]]), 1),
            "reorder_threshold": round(inv.reorder_threshold, 1), "updated_at": iso(inv.updated_at),
            "age_h": round((now - inv.updated_at).total_seconds() / 3600, 1), "source": inv.source, "validation": inv.validation,
            "sensor_id": inv.sensor_id, "sensor_health": sensor.health if sensor else None, "version": inv.version,
            "health": health_from(dos, usable, inv.reorder_threshold), "confidence": conf, "confidence_reasons": reasons,
            "fallback": fc["fallback"], "change_pct": round(chg["change_pct"], 1) if chg.get("available") else None,
            "below_reorder": usable < inv.reorder_threshold,
        })
    return rows


def post_health(rows: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in rows:
        cur = out.get(r["post_id"], "healthy")
        out[r["post_id"]] = r["health"] if HEALTH_ORDER[r["health"]] > HEALTH_ORDER[cur] else cur
    return out


def forecast_detail(db: Session, post_id: str, cls: str, horizon_days: int) -> dict | None:
    inv = db.scalar(select(Inventory).where(Inventory.post_id == post_id, Inventory.supply_class == cls))
    if inv is None:
        return None
    now = utcnow()
    hist = load_history(db).get((post_id, cls), [])
    weather = load_weather(db).get(post_id)
    up = weather_uplift(cls, weather)
    fc = forecast_series(hist, 7, up)
    base = baseline_series(hist, 7)
    sensor = db.get(Sensor, inv.sensor_id) if inv.sensor_id else None
    conf, reasons = confidence_for(inv, fc, sensor.health if sensor else None, now)
    usable = max(0.0, inv.quantity - inv.reserved)
    p10, p50, p90 = ([d[k] for d in fc["daily"]] for k in ("p10", "p50", "p90"))
    dos = usable / (mean(p50) or 1e-9)
    hdays = fc["daily"][:horizon_days]
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    history_days = 28
    history = [{"date": iso(start - timedelta(days=len(hist) - i))[:10], "value": round(v, 2)}
               for i, v in enumerate(hist)][-history_days:]
    forecast = [{"date": iso(start + timedelta(days=d["day"] - 1))[:10], "p10": round(d["p10"], 2), "p50": round(d["p50"], 2),
                 "p90": round(d["p90"], 2), "baseline": round(base[d["day"] - 1], 2)} for d in fc["daily"]]
    chg = explain_change(hist, up)
    drivers = [{"driver": "Recent consumption level", "effect": round(fc["level"], 2), "unit": f"{inv.unit}/day",
                "note": "Exponentially weighted deseasonalised level of the last 28 days."},
               {"driver": "Damped trend", "effect": round(fc["trend_per_day"], 3), "unit": f"{inv.unit}/day²",
                "note": "Linear trend over 14 days, damped and capped at ±3 % of level per day."},
               {"driver": "Weather uplift", "effect": round((up - 1) * 100, 1), "unit": "%",
                "note": f"Simulated weather input: {weather}" if weather else "No weather input."},
               {"driver": "Weekday profile amplitude", "effect": round((max(_weekday_factors(hist)) - min(_weekday_factors(hist))) * 100, 1)
                if len(hist) >= 7 else 0.0, "unit": "% peak-to-trough", "note": "Day-of-week consumption pattern."}]
    return {
        "post_id": post_id, "supply_class": cls, "unit": inv.unit, "horizon_days": horizon_days, "model_version": MODEL_VERSION,
        "simulated": True, "history": history, "forecast": forecast,
        "horizon_totals": {"p10": round(sum(d["p10"] for d in hdays), 1), "p50": round(sum(d["p50"] for d in hdays), 1),
                           "p90": round(sum(d["p90"] for d in hdays), 1),
                           "baseline": round(sum(base[: horizon_days]), 1)},
        "usable": round(usable, 1), "dos": round(dos, 1), "confidence": conf, "confidence_reasons": reasons,
        "tts": {"earliest_h": round(time_to_stockout_h(usable, p90), 1), "expected_h": round(time_to_stockout_h(usable, p50), 1),
                "latest_h": round(time_to_stockout_h(usable, p10), 1)},
        "fallback": fc["fallback"], "health": health_from(dos, usable, inv.reorder_threshold),
        "data": {"updated_at": iso(inv.updated_at), "age_h": round((now - inv.updated_at).total_seconds() / 3600, 1),
                 "source": inv.source, "validation": inv.validation},
        "drivers": drivers, "change": chg, "backtest": backtest(hist),
        "review_required": conf == "Low",
        "review_message": ("Low-confidence forecast: mandatory human review before any action. " + " ".join(reasons)) if conf == "Low" else None,
        "confidence_definition": ("Confidence reflects demand variability, history length, stock-reading validity/freshness and sensor "
                                  "health. It is NOT a calibrated probability of being correct."),
    }
