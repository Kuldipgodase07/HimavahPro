"""Hash-chained audit log demonstration.

Each event hash covers the previous hash plus the canonical event content, so editing any
past row breaks every later hash. LIMITATION: a hash chain alone is not tamper-proof; whoever
can rewrite the whole table can recompute the chain. Production needs protected/append-only
storage, access controls, key management (e.g. signed anchors), monitoring and independent
verification.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import iso, utcnow
from ..models import AuditEvent

GENESIS = "0" * 64


def _canonical(ts: datetime, actor: str, role: str, action: str, resource: str, outcome: str, detail: dict) -> str:
    return json.dumps(
        {"ts": iso(ts), "actor": actor, "role": role, "action": action, "resource": resource, "outcome": outcome, "detail": detail},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _hash(prev: str, canonical: str) -> str:
    return hashlib.sha256((prev + canonical).encode()).hexdigest()


def append(db: Session, actor: str, role: str, action: str, resource: str, outcome: str = "success",
           detail: dict | None = None, ts: datetime | None = None) -> AuditEvent:
    ts = (ts or utcnow()).replace(microsecond=0)
    detail = detail or {}
    last = db.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
    prev = last.hash if last else GENESIS
    ev = AuditEvent(ts=ts, actor=actor, role=role, action=action, resource=resource, outcome=outcome, detail=detail,
                    prev_hash=prev, hash=_hash(prev, _canonical(ts, actor, role, action, resource, outcome, detail)))
    db.add(ev)
    db.flush()
    return ev


def to_dict(e: AuditEvent) -> dict:
    return {"id": e.id, "ts": iso(e.ts), "actor": e.actor, "role": e.role, "action": e.action, "resource": e.resource,
            "outcome": e.outcome, "detail": e.detail, "prev_hash": e.prev_hash, "hash": e.hash}


def verify(db: Session, simulate_tamper_id: int | None = None) -> dict:
    """Recompute the chain. With simulate_tamper_id, an in-memory COPY of that row is altered to
    demonstrate detection; the stored data is never modified."""
    events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id)))
    prev = GENESIS
    broken_at: int | None = None
    reason = None
    for e in events:
        outcome, detail = e.outcome, copy.deepcopy(e.detail)
        if simulate_tamper_id is not None and e.id == simulate_tamper_id:
            outcome = "success" if outcome != "success" else "failure"  # simulated edit
        if e.prev_hash != prev:
            broken_at, reason = e.id, "prev_hash does not match the preceding event"
            break
        if _hash(prev, _canonical(e.ts, e.actor, e.role, e.action, e.resource, outcome, detail)) != e.hash:
            broken_at, reason = e.id, "event content does not match its recorded hash"
            break
        prev = e.hash
    return {
        "status": "intact" if broken_at is None else "tampering-detected",
        "events_checked": len(events), "broken_at": broken_at, "reason": reason,
        "head_hash": events[-1].hash if events else GENESIS, "simulated": simulate_tamper_id is not None,
        "limitations": ("A hash chain detects accidental or naive edits only. It is not a complete tamper-proof system: "
                        "production deployments need protected append-only storage, access controls, key management, "
                        "monitoring and independent verification."),
    }
