from .conftest import login


def test_requires_auth(fresh):
    assert fresh.get("/api/dashboard").status_code == 401


def test_password_and_mfa_flow(fresh):
    assert fresh.post("/api/auth/login", json={"username": "planner", "password": "wrong"}).status_code == 401
    r = fresh.post("/api/auth/login", json={"username": "planner", "password": "demo-password"}).json()
    assert r["mfa_required"]
    assert fresh.post("/api/auth/mfa", json={"challenge": r["challenge"], "code": "000000"}).status_code == 401
    ok = fresh.post("/api/auth/mfa", json={"challenge": r["challenge"], "code": "123456"})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "planner"


def test_rbac_enforced_server_side(fresh):
    fo = login(fresh, "field_operator")
    assert fresh.get("/api/admin/overview", headers=fo).status_code == 403
    assert fresh.get("/api/audit", headers=fo).status_code == 403
    assert fresh.post("/api/routes/RT-01/closure", json={"days": 3, "reason": "x y z"}, headers=fo).status_code == 403
    aud = login(fresh, "auditor")
    assert fresh.get("/api/audit", headers=aud).status_code == 200
    assert fresh.post("/api/recommendations/REC-001/decision", json={"action": "approve"}, headers=aud).status_code == 403
    assert fresh.patch("/api/admin/config", json={"key": "session_ttl_hours", "value": 4}, headers=aud).status_code == 403


def test_post_incharge_scoped(fresh):
    pi = login(fresh, "post_incharge")
    inv = fresh.get("/api/inventory?post=POST-K09", headers=pi).json()["items"][0]
    r = fresh.post(f"/api/inventory/{inv['id']}/adjust", json={"kind": "receipt", "qty": 5, "reason": "not my post"}, headers=pi)
    assert r.status_code == 403


def test_landslide_end_to_end(fresh):
    pl, cm, au = login(fresh, "planner"), login(fresh, "commander"), login(fresh, "auditor")
    recs = fresh.get("/api/recommendations", headers=cm).json()
    k04 = next(r for r in recs["items"] if r["post_id"] == "POST-K04" and r["supply_class"] == "fuel")
    before_time = k04["plan"]["time_h"]
    # forecast has uncertainty and DoS
    f = fresh.get("/api/forecast?post=POST-K04&cls=fuel&horizon=3", headers=cm).json()
    assert f["dos"] > 0 and f["tts"]["earliest_h"] <= f["tts"]["expected_h"] <= f["tts"]["latest_h"]
    # close the landslide route
    demo = fresh.get("/api/simulations/kinds", headers=pl).json()["demo"]
    c = fresh.post(f"/api/routes/{demo['landslide_route_id']}/closure", json={"days": 3, "reason": "Simulated landslide"}, headers=pl)
    assert c.status_code == 200 and c.json()["route"]["closed"]
    k04b = next(r for r in fresh.get("/api/recommendations", headers=cm).json()["items"] if r["id"] == k04["id"])
    assert demo["landslide_route_id"] not in k04b["plan"]["route_ids"]
    # simulator
    res = fresh.post("/api/simulations/run", json={"kind": "demand_surge", "params": {"pct": 40}}, headers=pl).json()
    assert res["simulated"] and res["posts"]
    # approvals: reject needs a reason, mandatory review needs acknowledgement
    assert fresh.post(f"/api/recommendations/{k04['id']}/decision", json={"action": "reject"}, headers=cm).status_code == 422
    ap = fresh.post(f"/api/recommendations/{k04['id']}/decision", json={"action": "approve"}, headers=cm)
    assert ap.status_code == 200 and ap.json()["status"] == "Approved"
    # planners cannot approve
    assert fresh.post(f"/api/recommendations/{k04['id']}/decision", json={"action": "approve"}, headers=pl).status_code == 403
    d = fresh.post(f"/api/recommendations/{k04['id']}/dispatch", headers=pl)
    assert d.status_code == 200 and d.json()["status"] == "Simulated Dispatch"
    done = fresh.post(f"/api/recommendations/{k04['id']}/complete", headers=pl)
    assert done.status_code == 200
    # inventory updated consistently
    inv = fresh.get("/api/inventory?post=POST-K04&cls=fuel", headers=cm).json()["items"][0]
    assert inv["dos"] > 6
    # audit trail contains the decision and chain is intact
    events = fresh.get("/api/audit?q=" + k04["id"], headers=au).json()["items"]
    assert any(e["action"] == "recommendation.approve" for e in events)
    assert fresh.post("/api/audit/verify", headers=au).json()["status"] == "intact"
    assert fresh.post("/api/audit/verify?tamper_demo=true", headers=au).json()["status"] == "tampering-detected"


def test_stock_adjust_validation_and_audit(fresh):
    pi = login(fresh, "post_incharge")
    inv = fresh.get("/api/inventory?post=POST-K04&cls=rations", headers=pi).json()["items"][0]
    assert fresh.post(f"/api/inventory/{inv['id']}/adjust", json={"kind": "issue", "qty": 1e9, "reason": "too much"}, headers=pi).status_code == 422
    assert fresh.post(f"/api/inventory/{inv['id']}/adjust", json={"kind": "issue", "qty": 10, "reason": "x"}, headers=pi).status_code == 422
    ok = fresh.post(f"/api/inventory/{inv['id']}/adjust", json={"kind": "issue", "qty": 10, "reason": "Routine issue to troops"}, headers=pi)
    assert ok.status_code == 200 and ok.json()["delta"] == -10
