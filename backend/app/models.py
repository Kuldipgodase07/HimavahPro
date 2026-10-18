"""SQLAlchemy models. All data is synthetic."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32))
    unit: Mapped[str] = mapped_column(String(80))
    post_id: Mapped[str | None] = mapped_column(String(16), nullable=True)  # scope for Post In-Charge
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Node(Base):
    """Graph node: depot, junction, airfield or (fictional) logistics post."""
    __tablename__ = "nodes"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(12))  # depot | junction | airfield | post
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    alt_m: Mapped[int] = mapped_column(Integer)
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)  # criticality tier 1 (highest) .. 3
    helipad: Mapped[bool] = mapped_column(Boolean, default=False)
    personnel: Mapped[int] = mapped_column(Integer, default=0)  # aggregate headcount band only (no personal data)
    formation: Mapped[str] = mapped_column(String(40), default="")


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    a: Mapped[str] = mapped_column(String(16))
    b: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(8), default="road")  # road | air
    distance_km: Mapped[float] = mapped_column(Float)
    base_time_h: Mapped[float] = mapped_column(Float)
    slope_risk: Mapped[float] = mapped_column(Float)  # 0..1
    closure_count: Mapped[int] = mapped_column(Integer, default=0)  # synthetic history
    rain_mm: Mapped[float] = mapped_column(Float, default=0)
    snow_cm: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | closed
    closed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[str] = mapped_column(String(16), index=True)
    supply_class: Mapped[str] = mapped_column(String(16))
    unit: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[float] = mapped_column(Float)
    reserved: Mapped[float] = mapped_column(Float, default=0)
    reorder_threshold: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(10), default="simulated")  # manual | sensor | simulated
    validation: Mapped[str] = mapped_column(String(12), default="valid")  # valid | stale | discrepancy
    sensor_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency for offline sync


class Consumption(Base):
    __tablename__ = "consumption"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[str] = mapped_column(String(16), index=True)
    supply_class: Mapped[str] = mapped_column(String(16))
    day: Mapped[datetime] = mapped_column(DateTime)
    qty: Mapped[float] = mapped_column(Float)


class Movement(Base):
    __tablename__ = "movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[str] = mapped_column(String(16), index=True)
    supply_class: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(12))  # receipt | issue | adjustment | count
    qty: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(240), default="")
    ref: Mapped[str | None] = mapped_column(String(24), nullable=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(16), index=True)
    supply_class: Mapped[str] = mapped_column(String(16))
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(12))
    urgency: Mapped[str] = mapped_column(String(10))  # critical | high | medium
    reason: Mapped[str] = mapped_column(Text)
    transport_mode: Mapped[str] = mapped_column(String(16))  # road | air | unavailable
    plan: Mapped[dict] = mapped_column(JSON)  # chosen route plan (route ids, time, reliability, fuel)
    alternatives: Mapped[list] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)  # forecast and stock-risk evidence
    limitations: Mapped[list] = mapped_column(JSON)
    confidence: Mapped[str] = mapped_column(String(8))  # High | Medium | Low
    mandatory_review: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="Draft")
    model_version: Mapped[str] = mapped_column(String(40))
    data_as_of: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    origin: Mapped[str] = mapped_column(String(24), default="planner-engine")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    convoy_id: Mapped[str | None] = mapped_column(String(12), nullable=True)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rec_id: Mapped[str] = mapped_column(String(12), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Convoy(Base):
    __tablename__ = "convoys"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    dest_post: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16))
    supply_class: Mapped[str] = mapped_column(String(16))
    qty: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(8), default="road")
    path: Mapped[list] = mapped_column(JSON)  # node ids
    route_ids: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="Planned")  # Planned | In Transit | Delayed | Incident | Arrived
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_eta: Mapped[datetime] = mapped_column(DateTime)
    est_eta: Mapped[datetime] = mapped_column(DateTime)
    rec_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    incidents: Mapped[list] = mapped_column(JSON, default=list)


class FieldReport(Base):
    __tablename__ = "field_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str | None] = mapped_column(String(48), unique=True, nullable=True)  # idempotency key
    kind: Mapped[str] = mapped_column(String(20))  # road_condition | receipt | count | incident
    post_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80))


class Sensor(Base):
    __tablename__ = "sensors"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # smart-bin | rfid | ble
    supply_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    battery_pct: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[datetime] = mapped_column(DateTime)
    health: Mapped[str] = mapped_column(String(10), default="ok")  # ok | degraded | offline


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(48))
    resource: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(16))  # success | denied | failure
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(24))
    params: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)


class Doc(Base):
    """Small JSON document store for governance fixtures and editable configuration."""
    __tablename__ = "docs"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
