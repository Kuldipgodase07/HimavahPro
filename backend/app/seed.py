"""Deterministic synthetic demonstration data.

Everything here is fictional: post names, identifiers, coordinates (a synthetic planar grid near
0°,0°, NOT geo-referenced to any real location), consumption history, weather and personnel
headcounts. No real operational, personal or classified information is used.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .db import Base, engine, iso, utcnow
from .models import (AuditEvent, Consumption, Convoy, Decision, Doc, FieldReport, Inventory, Movement, Node,
                     Recommendation, Route, ScenarioRun, Sensor, User)
from .services import audit
from .services.forecast import CLASSES, forecast_series, weather_uplift
from .services.routing import RouteNet

SEED = 2026
HISTORY_DAYS = 60

# id, name, kind, lon, lat, alt_m, helipad, sector
NODES = [
    ("DEP-A", "Base Depot Alpha", "depot", -0.85, -0.40, 600, False, "Rear"),
    ("DEP-B", "Forward Depot Bravo", "depot", -0.85, 0.30, 900, False, "Rear"),
    ("AIR-1", "Airfield One", "airfield", -0.65, 0.05, 1100, False, "Rear"),
    ("JN-1", "Junction North", "junction", -0.55, 0.40, 1500, False, "Transit"),
    ("JN-2", "Junction South", "junction", -0.55, -0.30, 1400, False, "Transit"),
    ("JN-3", "Junction Centre", "junction", -0.40, 0.00, 1800, False, "Transit"),
    ("POST-K01", "Tara Ridge", "post", -0.30, 0.45, 2600, False, "Sector Alpha"),
    ("POST-K02", "Meru Col", "post", -0.05, 0.50, 3000, False, "Sector Alpha"),
    ("POST-K03", "Sindhu Overlook", "post", 0.20, 0.45, 3400, False, "Sector Alpha"),
    ("POST-K04", "Ananta Pass", "post", 0.45, 0.50, 3800, False, "Sector Alpha"),
    ("POST-K05", "Veda Glacier Post", "post", 0.70, 0.40, 4200, True, "Sector Alpha"),
    ("POST-K06", "Ishan Bluff", "post", -0.25, -0.40, 2500, False, "Sector Bravo"),
    ("POST-K07", "Kirti Saddle", "post", 0.00, -0.45, 2900, False, "Sector Bravo"),
    ("POST-K08", "Rudra Terrace", "post", 0.25, -0.40, 3300, False, "Sector Bravo"),
    ("POST-K09", "Shwet Camp", "post", 0.50, -0.45, 3700, False, "Sector Bravo"),
    ("POST-K10", "Parvat Point", "post", 0.75, -0.35, 4100, True, "Sector Bravo"),
    ("POST-K11", "Nanda Spur", "post", -0.15, 0.05, 2800, False, "Sector Charlie"),
    ("POST-K12", "Uttung Outpost", "post", 0.10, 0.00, 3200, False, "Sector Charlie"),
    ("POST-K13", "Girija Plateau", "post", 0.35, 0.05, 3600, False, "Sector Charlie"),
    ("POST-K14", "Anand Col", "post", 0.60, 0.00, 4000, True, "Sector Charlie"),
    ("POST-K15", "Dhruv Bluff", "post", 0.20, 0.25, 3500, False, "Sector Delta"),
    ("POST-K16", "Sagar Spur", "post", 0.45, 0.25, 3900, True, "Sector Delta"),
    ("POST-K17", "Chandra Ledge", "post", 0.30, -0.20, 3450, False, "Sector Delta"),
    ("POST-K18", "Hima Terrace", "post", 0.55, -0.20, 3850, True, "Sector Delta"),
]

ROAD_EDGES = [
    ("DEP-A", "DEP-B"), ("DEP-B", "JN-1"), ("DEP-A", "JN-2"), ("JN-1", "JN-3"), ("JN-2", "JN-3"),
    ("JN-1", "POST-K01"), ("POST-K01", "POST-K02"), ("POST-K02", "POST-K03"), ("POST-K03", "POST-K04"), ("POST-K04", "POST-K05"),
    ("JN-2", "POST-K06"), ("POST-K06", "POST-K07"), ("POST-K07", "POST-K08"), ("POST-K08", "POST-K09"), ("POST-K09", "POST-K10"),
    ("JN-3", "POST-K11"), ("POST-K11", "POST-K12"), ("POST-K12", "POST-K13"), ("POST-K13", "POST-K14"),
    ("POST-K02", "POST-K11"), ("POST-K03", "POST-K15"), ("POST-K15", "POST-K12"), ("POST-K15", "POST-K16"),
    ("POST-K16", "POST-K04"), ("POST-K16", "POST-K13"), ("POST-K17", "POST-K12"), ("POST-K17", "POST-K08"),
    ("POST-K17", "POST-K18"), ("POST-K18", "POST-K13"), ("POST-K18", "POST-K09"), ("POST-K07", "POST-K11"),
]
AIR_TARGETS = ["POST-K05", "POST-K10", "POST-K14", "POST-K16", "POST-K18"]

LANDSLIDE_EDGE = ("POST-K02", "POST-K03")
DEMO_POST, DEMO_CLASS = "POST-K04", "fuel"

# (post, class) -> target Days of Supply (forecast-based). Others are drawn from 8..21.
DOS_OVERRIDES = {
    ("POST-K04", "fuel"): 3.5, ("POST-K09", "medical"): 2.3, ("POST-K14", "rations"): 2.7, ("POST-K05", "fuel"): 4.2,
    ("POST-K10", "spares"): 5.6, ("POST-K16", "fuel"): 6.1, ("POST-K13", "rations"): 4.6, ("POST-K18", "spares"): 9.0,
    ("POST-K07", "medical"): 11.0, ("POST-K12", "fuel"): 9.0, ("POST-K11", "rations"): 10.0, ("POST-K02", "fuel"): 7.5,
    ("POST-K03", "fuel"): 8.0,
}
HIGH_VARIABILITY = {("POST-K09", "medical"): 0.32}
SHORT_HISTORY = {("POST-K18", "spares"): 9}
VALIDATION = {("POST-K07", "medical"): "discrepancy", ("POST-K12", "fuel"): "stale"}
STALE_AGE_H = {("POST-K12", "fuel"): 41.0}
COLD_SNAP_POSTS = {"POST-K01", "POST-K02", "POST-K03", "POST-K04", "POST-K05", "POST-K15", "POST-K16"}

USERS = [
    ("commander", "Demo Commander", "commander", "Simulated Formation HQ", None),
    ("planner", "Demo Logistics Planner", "planner", "Simulated Formation HQ", None),
    ("post.incharge", "Demo Post In-Charge", "post_incharge", "POST-K04 (Ananta Pass)", "POST-K04"),
    ("field.operator", "Demo Field Operator", "field_operator", "Simulated Convoy Unit 1", None),
    ("sysadmin", "Demo System Administrator", "sysadmin", "Platform Team", None),
    ("auditor", "Demo Auditor / Privacy Reviewer", "auditor", "Assurance Cell", None),
    ("planner.two", "Demo Planner Two", "planner", "Simulated Sector Bravo Cell", None),
    ("post.incharge.two", "Demo Post In-Charge Two", "post_incharge", "POST-K09 (Shwet Camp)", "POST-K09"),
    ("field.operator.two", "Demo Field Operator Two", "field_operator", "Simulated Convoy Unit 2", None),
]


def create_schema() -> None:
    Base.metadata.create_all(engine)


def reset_schema() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def is_seeded(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(Node)) or 0) > 0


def _km(a: tuple, b: tuple) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1]) * 111.0


def seed_all(db: Session) -> None:
    rnd = random.Random(SEED)
    now = utcnow().replace(microsecond=0)
    node_by = {n[0]: n for n in NODES}

    # --- users and graph ---------------------------------------------------------------------------------------
    for u in USERS:
        db.add(User(username=u[0], name=u[1], role=u[2], unit=u[3], post_id=u[4], last_login=now - timedelta(hours=rnd.randint(2, 70))))
    for nid, name, kind, lon, lat, alt, heli, sector in NODES:
        tier = None
        personnel = 0
        if kind == "post":
            tier = 1 if alt >= 4000 else 2 if alt >= 3500 else 3
            personnel = rnd.randint(32, 110)
        db.add(Node(id=nid, name=name, kind=kind, lon=lon, lat=lat, alt_m=alt, tier=tier, helipad=heli, personnel=personnel, formation=sector))
    db.flush()
    personnel = {n.id: n.personnel for n in db.scalars(select(Node)) if n.kind == "post"}

    for i, (a, b) in enumerate(ROAD_EDGES, start=1):
        na, nb = node_by[a], node_by[b]
        dist = _km((na[3], na[4]), (nb[3], nb[4])) * rnd.uniform(1.25, 1.55)
        dalt = abs(na[5] - nb[5])
        slope = min(0.9, max(0.08, 0.12 + dalt / 2600 * 0.55 + rnd.uniform(-0.05, 0.1)))
        avg_alt = (na[5] + nb[5]) / 2
        rain = max(0.0, rnd.uniform(0, 14) + (10 if "Alpha" in na[7] + nb[7] else 0) - avg_alt / 900)
        snow = max(0.0, rnd.uniform(-4, 6) + avg_alt / 700 + (6 if "Alpha" in na[7] + nb[7] else 0))
        closures = max(0, int(rnd.gauss(slope * 4, 1)))
        speed = 32 - 14 * slope
        rid = f"RT-{i:02d}"
        db.add(Route(id=rid, a=a, b=b, mode="road", distance_km=round(dist, 1), base_time_h=round(dist / speed, 2),
                     slope_risk=round(slope, 2), closure_count=closures, rain_mm=round(rain, 1), snow_cm=round(snow, 1)))
    for j, t in enumerate(AIR_TARGETS, start=1):
        nt, na = node_by[t], node_by["AIR-1"]
        dist = _km((na[3], na[4]), (nt[3], nt[4]))
        db.add(Route(id=f"AR-{j:02d}", a="AIR-1", b=t, mode="air", distance_km=round(dist, 1), base_time_h=round(dist / 140 + 0.6, 2),
                     slope_risk=0.0, closure_count=rnd.randint(0, 2), rain_mm=round(rnd.uniform(0, 10), 1), snow_cm=round(rnd.uniform(0, 5), 1)))
    db.flush()

    # The demo landslide hits a segment on the primary road path to the demo post (with alternatives available).
    net0 = RouteNet.from_db(db)
    from .services.recommender import build_plan
    prim = build_plan(net0, DEMO_POST, DEMO_CLASS, 1)[1]  # the plan the planner engine will actually propose
    landslide_id = prim["route_ids"][-3] if len(prim["route_ids"]) >= 3 else prim["route_ids"][0]

    # --- weather (simulated) ---------------------------------------------------------------------------------------
    weather = {}
    for nid, _, kind, _, _, alt, _, _ in NODES:
        if kind != "post":
            continue
        temp = -2 - (alt - 2500) / 450 + rnd.uniform(-1.5, 1.5)
        snow = max(0.0, rnd.uniform(0, 6) + (alt - 2500) / 500)
        if nid in COLD_SNAP_POSTS:
            temp -= 4.5
            snow += 8
        weather[nid] = {"temp_c": round(temp, 1), "snow_cm": round(snow, 1), "wind_kph": rnd.randint(8, 45)}
    db.add(Doc(key="weather", value=weather))
    db.add(Doc(key="demo", value={"landslide_route_id": landslide_id, "demo_post": DEMO_POST, "demo_class": DEMO_CLASS,
                                  "scenario_name": "Simulated Landslide Disruption", "closure_days": 3}))

    # --- consumption history + inventory -----------------------------------------------------------------------
    start = now.replace(hour=0, minute=0, second=0) - timedelta(days=HISTORY_DAYS)
    for post, pers in personnel.items():
        node = node_by[post]
        for cls, meta in CLASSES.items():
            key = (post, cls)
            alt_f = 1 + (node[5] - 2500) / 6000 if cls == "fuel" else 1.0
            base = max(pers * meta["per_person"] * alt_f, 0.5)
            cv = HIGH_VARIABILITY.get(key, rnd.uniform(0.05, 0.13))
            n_days = SHORT_HISTORY.get(key, HISTORY_DAYS)
            phase = rnd.uniform(0, 7)
            vals = []
            for t in range(n_days):
                season = 1 + 0.12 * math.sin(2 * math.pi * (t + phase) / 7)
                drift = 1 + 0.0015 * (t - n_days / 2)
                noise = max(0.3, rnd.gauss(1, cv))
                v = base * season * drift * noise
                if cls == "fuel" and post in COLD_SNAP_POSTS and t >= n_days - 6:
                    v *= 1.12 + 0.02 * (t - (n_days - 6))
                if cls == "medical":
                    v = max(0.2, v)
                vals.append(round(v, 2))
            for t, v in enumerate(vals):
                day = start + timedelta(days=HISTORY_DAYS - n_days + t)
                db.add(Consumption(post_id=post, supply_class=cls, day=day, qty=v))
            fc = forecast_series(vals, 7, weather_uplift(cls, weather[post]))
            mean_p50 = sum(d["p50"] for d in fc["daily"]) / 7
            dos = DOS_OVERRIDES.get(key, round(rnd.uniform(8, 21), 1))
            usable = dos * mean_p50
            reserved = round(usable * rnd.uniform(0.03, 0.09), 1)
            sensor_roll = rnd.random()
            source = "sensor" if sensor_roll < 0.6 else "manual" if sensor_roll < 0.88 else "simulated"
            sensor_id = f"SB-{post[-3:]}-{cls[:3].upper()}" if source == "sensor" else None
            age = STALE_AGE_H.get(key, rnd.uniform(0.4, 9))
            if source == "manual":
                age = max(age, rnd.uniform(2, 20))
            updated = now - timedelta(hours=age)
            validation = VALIDATION.get(key, "valid")
            health = "ok"
            battery = rnd.randint(41, 98)
            if key == ("POST-K11", "rations"):
                source, sensor_id, health, battery = "sensor", "SB-K11-RAT", "offline", 0
                updated = now - timedelta(hours=30)
            if key == ("POST-K08", "fuel"):
                source, sensor_id, health, battery = "sensor", "SB-K08-FUE", "degraded", 12
            if sensor_id:
                db.add(Sensor(id=sensor_id, post_id=post, kind="smart-bin", supply_class=cls, battery_pct=battery,
                              last_seen=updated if health == "offline" else now - timedelta(minutes=rnd.randint(1, 55)), health=health))
            db.add(Inventory(post_id=post, supply_class=cls, unit=meta["unit"], quantity=round(usable + reserved, 1), reserved=reserved,
                             reorder_threshold=round(mean_p50 * (7 if node[5] >= 3500 else 5), 1), updated_at=updated, source=source,
                             validation=validation, sensor_id=sensor_id))
            # synthetic movement history
            for k in range(rnd.randint(2, 4)):
                kind = rnd.choice(["receipt", "issue", "issue", "adjustment"])
                amt = round(base * rnd.uniform(1, 4) * (1 if kind == "receipt" else -1 if kind == "issue" else rnd.choice([-0.3, 0.2])), 1)
                db.add(Movement(post_id=post, supply_class=cls, kind=kind, qty=amt, ts=now - timedelta(days=rnd.uniform(0.5, 14)),
                                actor="Synthetic history", note="Synthetic demonstration record"))
        db.add(Sensor(id=f"RF-{post[-3:]}", post_id=post, kind="rfid", battery_pct=100, last_seen=now - timedelta(minutes=rnd.randint(1, 120)), health="ok"))
        db.add(Sensor(id=f"BL-{post[-3:]}", post_id=post, kind="ble", battery_pct=rnd.randint(55, 100),
                      last_seen=now - timedelta(minutes=rnd.randint(1, 200)), health="ok"))
    db.flush()

    # --- convoys (simulated movements) ---------------------------------------------------------------------------
    net = RouteNet.from_db(db)

    def add_convoy(cid, post, cls, qty, status, dispatched_h, eta_h, mode="road", origin=None, rec_id=None, incidents=None):
        if mode == "air":
            p = net.plan_to(post)["air"]
        else:
            from .services.recommender import build_plan
            p = build_plan(net, post, cls, qty)[1]  # same primary path the planner proposes
        if p is None:
            return
        disp = now - timedelta(hours=dispatched_h) if dispatched_h is not None else None
        eta = now + timedelta(hours=eta_h)
        db.add(Convoy(id=cid, dest_post=post, origin=p["origin"], supply_class=cls, qty=qty, mode=mode, path=p["nodes"], route_ids=p["route_ids"],
                      status=status, dispatched_at=disp, planned_eta=eta, est_eta=eta, rec_id=rec_id, incidents=incidents or []))

    add_convoy("CNV-101", DEMO_POST, DEMO_CLASS, 900, "In Transit", 6, 30)
    add_convoy("CNV-102", "POST-K14", "rations", 1100, "Planned", None, 52)
    add_convoy("CNV-103", "POST-K09", "medical", 14, "In Transit", 10, 20)
    add_convoy("CNV-104", "POST-K10", "spares", 22, "In Transit", 1, 3, mode="air")
    add_convoy("CNV-105", "POST-K02", "rations", 700, "Arrived", 40, -14)
    add_convoy("CNV-106", "POST-K13", "rations", 900, "Delayed", 14, 26,
               incidents=[{"ts": iso(now - timedelta(hours=5)), "type": "Rockfall delay", "note": "Synthetic incident: minor rockfall, clearing in progress.", "actor": "Synthetic history"}])
    db.flush()

    _seed_history(db, rnd, now)
    from .services.governance_data import seed_docs
    seed_docs(db)
    db.add(Doc(key="meta", value={"anchor": iso(now), "seeded_at": iso(now)}))
    db.flush()

    from .services.recommender import generate_recommendations
    generate_recommendations(db, actor="HimavahPro Planner Engine (simulated)", role="system")
    db.commit()


def _seed_history(db: Session, rnd: random.Random, now: datetime) -> None:
    """Historic audit/decision records so the audit trail and approval history are populated."""
    events = [
        (timedelta(days=2, hours=5), "Demo Commander (Formation Commander)", "commander", "auth.sign_in", "session", "success", {"method": "demo"}),
        (timedelta(days=2, hours=4), "Demo System Administrator (System Administrator)", "sysadmin", "config.change", "model.low_confidence_threshold", "success", {"from": "Medium", "to": "Low", "note": "Synthetic history"}),
        (timedelta(days=1, hours=22), "Demo Planner (Logistics Planner)", "planner", "scenario.run", "SCN-H001", "success", {"kind": "demand_surge", "pct": 15}),
        (timedelta(days=1, hours=20), "Demo Post In-Charge (Post In-Charge)", "post_incharge", "inventory.adjust", "POST-K04/rations", "success", {"qty": -20, "reason": "Spoilage write-off (synthetic)"}),
        (timedelta(days=1, hours=9), "Demo Commander (Formation Commander)", "commander", "recommendation.approve", "REC-H001", "success", {"note": "Synthetic history"}),
        (timedelta(days=1, hours=8), "Demo Commander (Formation Commander)", "commander", "recommendation.reject", "REC-H002", "success", {"reason": "Superseded by air resupply (synthetic)"}),
        (timedelta(hours=20), "Demo Auditor / Privacy Reviewer (Auditor / Privacy Reviewer)", "auditor", "audit.verify", "audit-chain", "success", {"status": "intact"}),
    ]
    for delta, actor, role, action, resource, outcome, detail in events:
        audit.append(db, actor, role, action, resource, outcome, detail, ts=now - delta)
    # Historic recommendations with decisions (not active; they populate approval history)
    for rid, post, cls, qty, status, act, reason, hrs in [
        ("REC-H001", "POST-K02", "rations", 700.0, "Completed", "Approve", None, 33),
        ("REC-H002", "POST-K10", "medical", 12.0, "Rejected", "Reject", "Superseded by air resupply CNV-104 (synthetic)", 32),
    ]:
        unit = CLASSES[cls]["unit"]
        db.add(Recommendation(id=rid, post_id=post, supply_class=cls, qty=qty, unit=unit, urgency="medium", reason="Synthetic historic record.",
                              transport_mode="road", plan={}, alternatives=[], evidence={}, limitations=["Synthetic history"], confidence="Medium",
                              status=status, model_version="HV-SimForecaster v0.3 (demo statistical model)", origin="synthetic-history",
                              created_at=now - timedelta(hours=hrs + 2), updated_at=now - timedelta(hours=hrs), decided_by="Demo Commander",
                              decision_reason=reason))
        db.add(Decision(rec_id=rid, ts=now - timedelta(hours=hrs), actor="Demo Commander", role="commander", action=act, reason=reason,
                        from_status="Pending Review", to_status="Approved" if act == "Approve" else "Rejected", detail={"synthetic": True}))


def rebase_time(db: Session, delta: timedelta) -> None:
    """Shift synthetic timestamps forward so the demonstration looks current. Audit rows are never altered."""
    for model, cols in [(Inventory, ["updated_at"]), (Sensor, ["last_seen"]), (Movement, ["ts"]), (Recommendation, ["created_at", "updated_at", "data_as_of"]),
                        (Decision, ["ts"]), (Convoy, ["dispatched_at", "planned_eta", "est_eta"]), (FieldReport, ["ts"]),
                        (ScenarioRun, ["ts"]), (Route, ["closed_until"]), (User, ["last_login"])]:
        for row in db.scalars(select(model)):
            for c in cols:
                v = getattr(row, c)
                if v is not None:
                    setattr(row, c, v + delta)
    for conv in db.scalars(select(Convoy)):
        conv.incidents = [{**i, "ts": iso(datetime.fromisoformat(i["ts"].rstrip("Z")) + delta)} for i in conv.incidents]


def ensure_seeded() -> None:
    from . import config
    from .db import SessionLocal

    create_schema()
    with SessionLocal() as db:
        if not is_seeded(db):
            seed_all(db)
            return
        meta = db.get(Doc, "meta")
        if meta:
            anchor = datetime.fromisoformat(meta.value["anchor"].rstrip("Z"))
            now = utcnow()
            if (now - anchor).total_seconds() > config.REBASE_AFTER_HOURS * 3600:
                rebase_time(db, now - anchor)
                meta.value = {**meta.value, "anchor": iso(now)}
                db.commit()


def wipe_and_reseed() -> None:
    from .db import SessionLocal

    reset_schema()
    with SessionLocal() as db:
        seed_all(db)
