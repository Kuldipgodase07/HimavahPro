"""HimavahPro API (hackathon prototype, synthetic data)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import auth, decisions, governance, ops
from .seed import ensure_seeded


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_seeded()
    yield


app = FastAPI(title="HimavahPro API", version="0.1.0", lifespan=lifespan,
              description="Predictive Logistics Intelligence Platform: simulated prototype. All data is synthetic.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, ops.router, decisions.router, governance.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "HimavahPro", "simulated": True, "demo_auth": config.DEMO_AUTH}
