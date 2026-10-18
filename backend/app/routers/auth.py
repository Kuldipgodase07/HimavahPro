from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..auth import (ALL_PERMISSIONS, PERMISSION_LABELS, PERMISSIONS, ROLES, Principal, current_principal, identity_provider, issue_token,
                    principal_for, verify_token)
from ..db import get_db, iso, utcnow
from ..models import User
from ..services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

_failures: dict[str, list[float]] = {}  # in-memory demo lockout (per process)
LOCK_AFTER, LOCK_WINDOW = 5, 300


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class MfaBody(BaseModel):
    challenge: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class DemoBody(BaseModel):
    role: str


DEMO_USERNAMES = {"commander": "commander", "planner": "planner", "post_incharge": "post.incharge", "field_operator": "field.operator",
                  "sysadmin": "sysadmin", "auditor": "auditor"}
ROLE_BLURBS = {
    "commander": "Reviews and approves recommendations; full operational visibility.",
    "planner": "Runs scenarios, triggers simulated closures, submits plans for review.",
    "post_incharge": "Manages stock for POST-K04; scoped least-privilege access.",
    "field_operator": "Field entry, road-condition and incident reports only.",
    "sysadmin": "Users, configuration and governance records; no operational decisions.",
    "auditor": "Read-only audit, governance and AI oversight records.",
}


def _session(db: Session, user: User, method: str) -> dict:
    user.last_login = utcnow()
    p = principal_for(user)
    audit.append(db, p.label, p.role, "auth.sign_in", "session", "success", {"method": method})
    db.commit()
    return {"token": issue_token(user), "user": _me(p)}


def _me(p: Principal) -> dict:
    return {"username": p.username, "name": p.name, "role": p.role, "role_label": ROLES[p.role], "post_id": p.post_id,
            "permissions": sorted(p.permissions)}


@router.get("/demo-roles")
def demo_roles():
    if not config.DEMO_AUTH:
        return {"enabled": False, "roles": []}
    return {"enabled": True, "notice": "Demonstration authentication only. No real credentials or identity infrastructure.",
            "roles": [{"role": r, "label": ROLES[r], "description": ROLE_BLURBS[r]} for r in DEMO_USERNAMES]}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    key = body.username.strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < LOCK_WINDOW]
    if len(recent) >= LOCK_AFTER:
        audit.append(db, key, "unknown", "auth.locked", "session", "denied", {})
        db.commit()
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = identity_provider.authenticate(body.username, body.password, db)
    if user is None:
        _failures[key] = [*recent, now]
        audit.append(db, key, "unknown", "auth.sign_in", "session", "failure", {"reason": "invalid credentials"})
        db.commit()
        raise HTTPException(401, "Invalid username or password.")
    _failures.pop(key, None)
    if user.mfa_enabled:
        return {"mfa_required": True, "challenge": issue_token(user, "mfa", 300), "hint": "Demonstration MFA: enter the demo code shown in the README."}
    return {"mfa_required": False, **_session(db, user, "password")}


@router.post("/mfa")
def mfa(body: MfaBody, db: Session = Depends(get_db)):
    username = verify_token(body.challenge, "mfa")
    if not username:
        raise HTTPException(401, "Verification session expired. Sign in again.")
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(401, "Account unavailable.")
    if body.code != config.DEMO_MFA_CODE:
        audit.append(db, username, user.role, "auth.mfa", "session", "failure", {})
        db.commit()
        raise HTTPException(401, "Verification code incorrect.")
    return _session(db, user, "password+mfa(demo)")


@router.post("/demo-login")
def demo_login(body: DemoBody, db: Session = Depends(get_db)):
    if not config.DEMO_AUTH:
        raise HTTPException(404, "Demo sign-in is disabled.")
    uname = DEMO_USERNAMES.get(body.role)
    user = db.scalar(select(User).where(User.username == uname)) if uname else None
    if user is None or not user.active:
        raise HTTPException(404, "Unknown demo role.")
    return _session(db, user, "demo-role")


@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    return _me(p)


@router.post("/logout")
def logout(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    audit.append(db, p.label, p.role, "auth.sign_out", "session", "success", {})
    db.commit()
    return {"ok": True}


@router.get("/permission-matrix")
def permission_matrix(_: Principal = Depends(current_principal)):
    return {"roles": [{"role": r, "label": l} for r, l in ROLES.items()],
            "permissions": [{"key": k, "label": PERMISSION_LABELS.get(k, k)} for k in ALL_PERMISSIONS],
            "grants": {r: sorted(PERMISSIONS[r]) for r in ROLES}}
