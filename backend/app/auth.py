"""Demonstration authentication and server-side role-based access control.

The IdentityProvider boundary is deliberately small so an approved identity provider
(OIDC/SAML or a government SSO) can replace DemoIdentityProvider without touching routers.
Permissions are enforced here, in the backend; the UI only mirrors them for convenience.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User

ROLES = {
    "commander": "Formation Commander",
    "planner": "Logistics Planner",
    "post_incharge": "Post In-Charge",
    "field_operator": "Convoy / Field Operator",
    "sysadmin": "System Administrator",
    "auditor": "Auditor / Privacy Reviewer",
}

_OPS_VIEW = {"dashboard.view", "map.view", "forecast.view", "inventory.view", "routes.view", "recs.view", "convoy.view", "sim.view"}

PERMISSIONS: dict[str, set[str]] = {
    "commander": _OPS_VIEW | {"recs.decide", "recs.dispatch", "recs.create", "routes.closure", "sim.run", "reports.view",
                              "ai.view", "audit.view", "governance.view", "convoy.report"},
    "planner": _OPS_VIEW | {"recs.create", "recs.submit", "recs.dispatch", "routes.closure", "sim.run", "reports.view", "ai.view",
                            "convoy.report"},
    "post_incharge": {"dashboard.view", "map.view", "forecast.view", "inventory.view", "inventory.adjust", "routes.view",
                      "recs.view", "convoy.view", "convoy.report", "field.use", "sim.view"},
    "field_operator": {"dashboard.view", "map.view", "inventory.view", "convoy.view", "convoy.report", "field.use", "routes.view"},
    "sysadmin": {"dashboard.view", "map.view", "admin.view", "admin.users", "admin.config", "governance.view", "governance.manage",
                 "audit.view", "ai.view", "reports.view"},
    "auditor": {"dashboard.view", "inventory.view", "forecast.view", "routes.view", "recs.view", "convoy.view", "ai.view",
                "audit.view", "audit.verify", "governance.view", "reports.view", "admin.view"},
}

# Every permission that exists, used to render the permission matrix.
ALL_PERMISSIONS = sorted({p for perms in PERMISSIONS.values() for p in perms})

PERMISSION_LABELS = {
    "dashboard.view": "View Command Centre", "map.view": "View Logistics Map", "forecast.view": "View demand forecasts",
    "inventory.view": "View inventory", "inventory.adjust": "Adjust stock (scoped to own post for Post In-Charge)",
    "routes.view": "View route intelligence", "routes.closure": "Trigger / clear simulated route closure",
    "recs.view": "View recommendations", "recs.create": "Create draft recommendations", "recs.submit": "Submit recommendations for review",
    "recs.decide": "Approve / edit / reject recommendations", "recs.dispatch": "Run simulated dispatch / completion",
    "sim.view": "View What-if Simulator", "sim.run": "Run what-if scenarios", "convoy.view": "View convoy status",
    "convoy.report": "Report simulated incidents", "field.use": "Use field operations tools", "reports.view": "View and export reports",
    "ai.view": "View Responsible AI Centre", "audit.view": "View audit trail", "audit.verify": "Verify audit chain integrity",
    "governance.view": "View privacy & security governance", "governance.manage": "Manage governance records",
    "admin.view": "View administration", "admin.users": "Manage users and roles", "admin.config": "Change system configuration",
}


@dataclass
class Principal:
    username: str
    name: str
    role: str
    post_id: str | None
    permissions: set[str]

    @property
    def label(self) -> str:
        return f"{self.name} ({ROLES[self.role]})"


class IdentityProvider(Protocol):
    def authenticate(self, username: str, password: str, db: Session) -> User | None: ...


class DemoIdentityProvider:
    """Demonstration only: a single shared non-secret placeholder password from the environment."""

    def authenticate(self, username: str, password: str, db: Session) -> User | None:
        user = db.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None or not user.active:
            return None
        if not hmac.compare_digest(password.encode(), config.DEMO_PASSWORD.encode()):
            return None
        return user


identity_provider: IdentityProvider = DemoIdentityProvider()


def _sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(config.SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _verify(token: str) -> dict | None:
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(config.SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:  # malformed token
        return None


def issue_token(user: User, kind: str = "access", ttl: int | None = None) -> str:
    return _sign({"sub": user.username, "kind": kind, "exp": int(time.time()) + (ttl or config.TOKEN_TTL_SECONDS)})


def verify_token(token: str, kind: str = "access") -> str | None:
    payload = _verify(token)
    if not payload or payload.get("kind") != kind:
        return None
    return payload["sub"]


def principal_for(user: User) -> Principal:
    return Principal(user.username, user.name, user.role, user.post_id, set(PERMISSIONS.get(user.role, set())))


def current_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    username = verify_token(authorization.split(" ", 1)[1])
    if not username:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Account unavailable")
    return principal_for(user)


def require(*perms: str):
    """Dependency factory: the caller must hold every listed permission (enforced server-side)."""

    def dep(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> Principal:
        missing = [x for x in perms if x not in p.permissions]
        if missing:
            from .services.audit import append  # local import avoids a cycle

            append(db, p.label, p.role, "access.denied", ",".join(missing), "denied", {"required": list(perms)})
            db.commit()
            raise HTTPException(status_code=403, detail=f"Permission denied: requires {', '.join(missing)}")
        return p

    return dep
