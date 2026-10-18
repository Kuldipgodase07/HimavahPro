from app.services.forecast import forecast_series, time_to_stockout_h, health_from, backtest
from app.services.routing import RouteNet, assess
from app.services import audit


def test_forecast_quantiles_ordered_and_fallback():
    vals = [100 + (i % 7) * 3 for i in range(40)]
    fc = forecast_series(vals, 7)
    assert all(d["p10"] <= d["p50"] <= d["p90"] for d in fc["daily"]) and not fc["fallback"]
    assert forecast_series([10, 11, 12], 3)["fallback"]


def test_time_to_stockout():
    assert time_to_stockout_h(100, [50, 50, 50]) == 48.0
    assert time_to_stockout_h(0, [10]) == 0.0


def test_health_bands():
    assert health_from(2, 100, 10) == "critical" and health_from(4, 100, 10) == "elevated"
    assert health_from(6, 100, 10) == "attention" and health_from(10, 100, 10) == "healthy"


def test_rri_decreases_with_rain():
    r = {"id": "x", "a": "A", "b": "B", "mode": "road", "distance_km": 10, "base_time_h": 1, "slope_risk": .4, "closure_count": 1, "rain_mm": 0, "snow_cm": 0, "closed": False}
    assert assess(r, rain=60)["rri"] < assess(r, rain=0)["rri"]


def test_dijkstra_prefers_cheaper_path_and_respects_closures():
    nodes = {k: {"id": k, "name": k, "kind": "junction", "lat": 0, "lon": 0, "helipad": False} for k in "ABC"}
    def rt(i, a, b, t):
        return {"id": i, "a": a, "b": b, "mode": "road", "distance_km": t * 20, "base_time_h": t, "slope_risk": 0, "closure_count": 0, "rain_mm": 0, "snow_cm": 0, "closed": False}
    net = RouteNet(nodes, {"R1": rt("R1", "A", "B", 1), "R2": rt("R2", "B", "C", 1), "R3": rt("R3", "A", "C", 5)})
    assert net.shortest("A", "C")["route_ids"] == ["R1", "R2"]
    net.routes["R1"]["closed"] = True
    net.invalidate()
    assert net.shortest("A", "C")["route_ids"] == ["R3"]
    net.routes["R3"]["closed"] = True
    net.invalidate()
    assert net.shortest("A", "C") is None


def test_hash_chain_detects_tamper(fresh):
    from app.db import SessionLocal
    from app.models import AuditEvent
    with SessionLocal() as db:
        assert audit.verify(db)["status"] == "intact"
        ev = db.get(AuditEvent, 3)
        ev.outcome = "failure" if ev.outcome == "success" else "success"
        db.commit()
        res = audit.verify(db)
        assert res["status"] == "tampering-detected" and res["broken_at"] == 3
