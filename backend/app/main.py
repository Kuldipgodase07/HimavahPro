"""HimavahPro API (hackathon prototype, synthetic data)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import auth, decisions, governance, ops
from .seed import ensure_seeded

logger = logging.getLogger("himavahpro")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_seeded()
    # Synchronize all records to MongoDB Atlas if enabled and needed
    if config.MONGODB_SYNC_ENABLED:
        try:
            from .mongodb import get_mongo_db, sync_all_to_mongo
            db = get_mongo_db()
            if db is not None and db.users.count_documents({}) == 0:
                from .db import SessionLocal
                with SessionLocal() as session:
                    sync_all_to_mongo(session)
        except Exception as e:
            logger.warning(f"MongoDB startup sync error: {e}")
    yield


app = FastAPI(title="HimavahPro API", version="0.1.0", lifespan=lifespan,
              description="Predictive Logistics Intelligence Platform: simulated prototype. All data is synthetic.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, ops.router, decisions.router, governance.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "HimavahPro", "simulated": True, "demo_auth": config.DEMO_AUTH}


@app.get("/api/mongodb/status")
def mongodb_status():
    """Returns the real-time connection status and document counts for MongoDB Atlas."""
    from .mongodb import get_mongo_status
    return get_mongo_status()
