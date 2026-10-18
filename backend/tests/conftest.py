import os, tempfile
_tmp = tempfile.mkdtemp()
os.environ["HIMAVAH_DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["HIMAVAH_SECRET"] = "test-secret"
os.environ["HIMAVAH_MONGODB_SYNC"] = "false"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fresh(client):
    from app.seed import wipe_and_reseed
    wipe_and_reseed()
    return client


def login(client, role):
    r = client.post("/api/auth/demo-login", json={"role": role})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}
