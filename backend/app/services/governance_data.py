"""Governance, privacy and administration fixtures (all synthetic and illustrative).

DPDP-aligned by design; subject to deployment-specific legal and security review.
Nothing here is a legal determination, certification or audit result.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..db import iso, utcnow
from ..models import Doc

DPDP_STATEMENT = "DPDP-aligned by design; subject to deployment-specific legal and security review."

MODELS = [
    {"id": "HV-SimForecaster", "version": "0.3", "status": "active", "kind": "Statistical demand forecaster (simulated)",
     "trained": False,
     "description": "Weekday-profile deseasonalisation, exponentially weighted level, damped trend, weather uplift, normal-approximation P10/P50/P90.",
     "intended_use": "Demonstrating uncertainty-aware demand forecasts on synthetic consumption data.",
     "not_for": "Operational planning, safety-critical decisions, or any real logistics data without validation.",
     "limitations": ["Not a Temporal Fusion Transformer and not trained on real data.", "Normal-approximation intervals are not calibrated against real outcomes.",
                     "Weather uplift coefficients are hand-set assumptions.", "Rule-based fallback (flat baseline) is used below 14 days of history."],
     "inputs": ["Daily consumption history (synthetic)", "Simulated weather inputs per post"], "evaluation_source": "backtest",
     "lineage": ["Synthetic generator (seed 2026) -> consumption table", "Simulated weather -> docs.weather"],
     "drift": {"status": "placeholder", "note": "No drift monitor is implemented. A production deployment would track input and error distributions."}},
    {"id": "HV-RRI-Formula", "version": "0.2", "status": "active", "kind": "Rule-based logistic scoring formula",
     "trained": False,
     "description": "Hand-set logistic score over rainfall, snowfall, slope risk and closure history, giving a Route Reliability Index in [0, 1].",
     "intended_use": "Illustrating how route reliability could be explained and compared.",
     "not_for": "Declaring a route safe or passable. A high score is not an operational clearance.",
     "limitations": ["Coefficients are not fitted to data.", "Segment reliabilities are combined assuming independence.", "Weather inputs are synthetic."],
     "inputs": ["Rainfall (mm)", "Snowfall (cm)", "Slope risk (0-1)", "Synthetic closure history"], "evaluation_source": None,
     "lineage": ["Synthetic route attributes -> routes table"],
     "drift": {"status": "placeholder", "note": "Not applicable until the formula is replaced by a trained model."}},
    {"id": "HV-Planner", "version": "0.1", "status": "active", "kind": "Rule-based planner (Dijkstra + coverage heuristic)",
     "trained": False,
     "description": "Dijkstra pathfinding for fastest and most reliable routes; replenishment quantity from a 10-day coverage heuristic.",
     "intended_use": "Generating reviewable recommendations that always require human approval.",
     "not_for": "Autonomous dispatch or optimisation claims.",
     "limitations": ["No capacity, vehicle or handling-time model.", "OR-Tools optimisation is a future integration boundary."],
     "inputs": ["Forecasts", "Inventory", "Route graph and RRI"], "evaluation_source": None,
     "lineage": ["Forecaster output + route graph -> recommendations"],
     "drift": {"status": "placeholder", "note": "Not applicable to a deterministic rule-based planner."}},
    {"id": "TFT-Forecaster", "version": "planned", "status": "planned", "kind": "Temporal Fusion Transformer (PyTorch Forecasting)",
     "trained": False, "description": "Planned replacement for the statistical forecaster. NOT implemented or running in this prototype.",
     "intended_use": "Future multi-horizon probabilistic forecasting.", "not_for": "Not available.",
     "limitations": ["Not implemented."], "inputs": [], "evaluation_source": None, "lineage": [],
     "drift": {"status": "placeholder", "note": "Not implemented."}},
    {"id": "XGB-RouteRisk", "version": "planned", "status": "planned", "kind": "XGBoost route-risk classifier",
     "trained": False, "description": "Planned tabular model for route disruption risk. NOT implemented in this prototype.",
     "intended_use": "Future route-risk prediction.", "not_for": "Not available.", "limitations": ["Not implemented."],
     "inputs": [], "evaluation_source": None, "lineage": [], "drift": {"status": "placeholder", "note": "Not implemented."}},
    {"id": "SHAP-Explainer", "version": "planned", "status": "planned", "kind": "SHAP feature attributions",
     "trained": False, "description": "Planned. SHAP values require a compatible trained model; none are computed or displayed in this prototype.",
     "intended_use": "Future model explanations.", "not_for": "Not available.", "limitations": ["Not implemented."],
     "inputs": [], "evaluation_source": None, "lineage": [], "drift": {"status": "placeholder", "note": "Not implemented."}},
]

STAGES = ["Detect", "Contain", "Assess", "Notify (if required)", "Recover", "Review"]


def seed_docs(db: Session) -> None:
    now = utcnow()
    d = lambda days: iso(now - timedelta(days=days))  # noqa: E731
    db.add(Doc(key="models", value={"items": MODELS}))
    db.add(Doc(key="privacy", value={
        "statement": DPDP_STATEMENT,
        "inventory": [
            {"id": "DS-01", "name": "Inventory & stock readings", "classification": "Non-personal operational", "personal": False,
             "examples": "Quantities, thresholds, sensor readings", "retention_key": "operational", "owner": "Logistics"},
            {"id": "DS-02", "name": "Consumption history", "classification": "Non-personal operational (aggregate)", "personal": False,
             "examples": "Daily consumption per post and class", "retention_key": "operational", "owner": "Logistics"},
            {"id": "DS-03", "name": "Terrain, weather & route risk", "classification": "Non-personal environmental", "personal": False,
             "examples": "Rainfall, snow, slope, closure counts", "retention_key": "operational", "owner": "Planning"},
            {"id": "DS-04", "name": "Per-post headcount band", "classification": "Aggregate (not personal)", "personal": False,
             "examples": "Integer headcount used only as a demand-scaling input", "retention_key": "operational", "owner": "Planning"},
            {"id": "DS-05", "name": "User accounts", "classification": "Personal data (synthetic)", "personal": True,
             "examples": "Name, username, unit, role, last login", "retention_key": "accounts", "owner": "Administration"},
            {"id": "DS-06", "name": "Audit log", "classification": "Contains personal identifiers (actor names)", "personal": True,
             "examples": "Actor, action, timestamp", "retention_key": "audit", "owner": "Assurance"},
            {"id": "DS-07", "name": "Approval & decision records", "classification": "Contains personal identifiers (approver names)", "personal": True,
             "examples": "Approver, reason text", "retention_key": "decisions", "owner": "Command"},
            {"id": "DS-08", "name": "Field reports", "classification": "Contains personal identifiers (reporter names)", "personal": True,
             "examples": "Reporter, road condition note", "retention_key": "field", "owner": "Field operations"},
            {"id": "DS-09", "name": "Device registry", "classification": "Pseudonymous device identifiers", "personal": False,
             "examples": "Sensor IDs, battery, last seen", "retention_key": "operational", "owner": "Administration"},
        ],
        "processing": [
            {"id": "PR-01", "activity": "Authentication and session management", "data": "Username, role, login time", "personal": True,
             "purpose": "Authenticate authorised users and enforce least-privilege access", "lawful_basis": "To be confirmed by deployment-specific legal review",
             "retention_key": "accounts", "recipients": "System administrators", "status": "Draft"},
            {"id": "PR-02", "activity": "Audit logging of consequential actions", "data": "Actor, action, resource, timestamp", "personal": True,
             "purpose": "Accountability and integrity review of decisions", "lawful_basis": "To be confirmed by deployment-specific legal review",
             "retention_key": "audit", "recipients": "Auditors, administrators", "status": "Draft"},
            {"id": "PR-03", "activity": "Recording approval decisions and reasons", "data": "Approver identity, reason text", "personal": True,
             "purpose": "Human-in-command oversight and review", "lawful_basis": "To be confirmed by deployment-specific legal review",
             "retention_key": "decisions", "recipients": "Command, auditors", "status": "Draft"},
            {"id": "PR-04", "activity": "Field condition reporting", "data": "Reporter identity, free-text note", "personal": True,
             "purpose": "Route condition awareness", "lawful_basis": "To be confirmed by deployment-specific legal review",
             "retention_key": "field", "recipients": "Planners", "status": "Draft"},
            {"id": "PR-05", "activity": "Demand forecasting and route risk scoring", "data": "Non-personal operational data only", "personal": False,
             "purpose": "Logistics planning", "lawful_basis": "Not applicable to non-personal data (to be confirmed)",
             "retention_key": "operational", "recipients": "Planners, command", "status": "Draft"},
        ],
        "consents": [
            {"id": "CN-001", "subject": "Synthetic user U-001", "notice_version": "v0.1", "purpose": "Account and audit processing notice", "status": "Notice acknowledged", "date": d(12)},
            {"id": "CN-002", "subject": "Synthetic user U-002", "notice_version": "v0.1", "purpose": "Account and audit processing notice", "status": "Notice acknowledged", "date": d(11)},
            {"id": "CN-003", "subject": "Synthetic user U-003", "notice_version": "v0.1", "purpose": "Field reporting notice", "status": "Pending acknowledgement", "date": d(2)},
        ],
        "minimisation": [
            {"id": "MC-01", "control": "Inventory, forecast and route records contain no personal identifiers", "status": "implemented"},
            {"id": "MC-02", "control": "Per-post headcount stored as an aggregate integer only", "status": "implemented"},
            {"id": "MC-03", "control": "Role-scoped views (Post In-Charge limited to own post for stock adjustments)", "status": "implemented"},
            {"id": "MC-04", "control": "Free-text fields warn against entering personal data", "status": "planned"},
            {"id": "MC-05", "control": "Automated purge of expired personal records", "status": "planned"},
        ],
        "retention": [
            {"key": "operational", "label": "Operational data (inventory, forecasts, routes)", "days": 730, "personal": False},
            {"key": "accounts", "label": "User accounts and sessions", "days": 365, "personal": True},
            {"key": "audit", "label": "Audit log", "days": 1095, "personal": True},
            {"key": "decisions", "label": "Approval and decision records", "days": 1095, "personal": True},
            {"key": "field", "label": "Field reports", "days": 180, "personal": True},
        ],
        "deletions": [
            {"id": "DEL-001", "dataset": "Field reports", "scope": "Records older than 180 days (synthetic)", "status": "Pending approval", "requested": d(1)},
            {"id": "DEL-002", "dataset": "User accounts", "scope": "Deactivated synthetic accounts", "status": "Completed (simulated)", "requested": d(20)},
        ],
        "requests": [
            {"id": "GR-001", "type": "Access request", "subject": "Synthetic data principal 1", "received": d(6), "due": iso(now + timedelta(days=24)),
             "status": "In review", "summary": "Request for a copy of account and audit records (synthetic)."},
            {"id": "GR-002", "type": "Correction request", "subject": "Synthetic data principal 2", "received": d(3), "due": iso(now + timedelta(days=27)),
             "status": "Open", "summary": "Unit name recorded incorrectly (synthetic)."},
            {"id": "GR-003", "type": "Grievance", "subject": "Synthetic data principal 3", "received": d(15), "due": iso(now + timedelta(days=15)),
             "status": "Closed", "summary": "Query about retention of field reports (synthetic)."},
        ],
        "incidents": [
            {"id": "INC-S01", "title": "Simulated: report exported to an unintended recipient", "severity": "Medium", "stage": 1, "opened": d(1),
             "note": "Training scenario only. No real incident."},
        ],
        "stages": STAGES,
        "encryption": [
            {"item": "Transport encryption (TLS)", "status": "not-implemented", "note": "Terminate TLS at a reverse proxy in deployment; not configured in the prototype."},
            {"item": "Encryption at rest", "status": "not-implemented", "note": "Development SQLite file is unencrypted. Use encrypted volumes / managed encryption in deployment."},
            {"item": "Key management", "status": "planned", "note": "KMS/HSM integration boundary only; no keys are managed by the prototype."},
            {"item": "Session token signing", "status": "demo", "note": "HMAC-SHA256 signed demo tokens; replace with the approved identity provider."},
            {"item": "Audit log integrity", "status": "demo", "note": "SHA-256 hash chain. Not a complete tamper-proof system."},
        ],
        "disclaimer": "Illustrative governance workspace. It does not claim DPDP compliance, CERT-In certification, a security audit or official approval.",
    }))
    db.add(Doc(key="admin", value={
        "config": {"low_confidence_threshold": "Low", "mandatory_review_on_low": True, "rule_based_fallback": True,
                   "session_ttl_hours": 8, "audit_chain_enabled": True, "default_forecast_horizon_days": 3, "demo_auth_enabled": True},
        "integrations": [
            {"id": "mqtt", "name": "MQTT broker (IoT events)", "status": "not-connected", "note": "Integration boundary only; sensor readings are simulated."},
            {"id": "postgis", "name": "PostgreSQL + PostGIS / TimescaleDB", "status": "optional", "note": "Set DATABASE_URL to use PostgreSQL; PostGIS/Timescale features are not yet used."},
            {"id": "navic", "name": "NavIC positioning / timing", "status": "not-connected", "note": "Would provide position/time only, not internet connectivity."},
            {"id": "weather", "name": "Public weather data adapter", "status": "not-connected", "note": "Weather inputs are simulated."},
            {"id": "idp", "name": "Identity provider (OIDC / SAML)", "status": "not-connected", "note": "Demo authentication in use."},
            {"id": "llm", "name": "Local natural-language query service (e.g. Ollama)", "status": "disabled", "note": "Optional and isolated; not required to load any screen."},
        ],
    }))
