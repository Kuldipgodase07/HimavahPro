# HimavahPro

**Predictive Logistics Intelligence Platform** — Predict | Prepare | Optimise | Assure
Smart India Hackathon 2026 · Team Sinhgad

> **This is a working prototype on synthetic data.** All posts (POST-K01…), depots, routes, stock levels
> and users are fictional. Forecasts, the Route Reliability Index and recommendations are **simulated,
> rule-based/statistical logic**, not trained models (no TFT, no SHAP). No real integration (SAP, GIS,
> SSO, SMS, satellite weather, IoT) is connected. No compliance or certification is claimed.
> **DPDP-aligned by design; subject to deployment-specific legal and security review.**

## Run locally

Backend (Python 3.11+):
```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000      # seeds the DB on first start
pytest                                # 12 tests
```
Frontend (Node 20+):
```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api to :8000
npm run typecheck && npm test && npm run build
```
Docker: `cp .env.example .env && docker compose up --build` then open http://localhost:8080.

## Demo access
Landing page → Sign in. Use "Demo role sign-in" buttons, or username + password `demo-password`, then MFA code `123456`.
Usernames: `commander`, `planner`, `post.incharge`, `field.operator`, `sysadmin`, `auditor`.
These are non-secret demo placeholders; override with `HIMAVAH_DEMO_PASSWORD` / `HIMAVAH_DEMO_MFA_CODE`, disable with `HIMAVAH_DEMO_AUTH=false`.

## Architecture
- **Backend**: FastAPI, Pydantic v2, SQLAlchemy 2 (SQLite default; PostgreSQL via `DATABASE_URL`).
  RBAC is enforced server-side per endpoint (`require(*perms)`); denied attempts are audit-logged.
  Audit log is a SHA-256 hash chain with a tamper-detection demo (on an in-memory copy).
  Identity sits behind an `IdentityProvider` boundary; demo tokens are HMAC-signed (secret from `HIMAVAH_SECRET`, else generated into `data/.secret`).
- **Services**: forecaster (weekday profile + EWMA + damped trend, P10/P50/P90, rule-based fallback under 14 days, back-test vs 7-day baseline), rule-based Route Reliability Index, Dijkstra (fastest vs reliable), recommender (human approval workflow), 14-day what-if simulator, calculation-backed explanations.
- **Frontend**: React 19, TypeScript, Vite, Tailwind 4, Recharts, MapLibre (offline synthetic map with SVG fallback), offline field queue (localStorage + service worker).

## Functional vs simulated
Functional: sign-in/RBAC, inventory edits with audit, forecasting, routing, recommendations with approve/edit/reject/request-info, dispatch simulation, convoys, field sync with conflict handling, simulator, audit chain, CSV reports, admin permission matrix.
Simulated: all data, weather, IoT sensors, MFA, dispatch, notifications, "AI" explanations.
Needs credentials/real work to integrate: ERP/inventory feeds, SSO/IdP, weather APIs, GIS tiles, SMS/radio, IoT gateway.

## Limitations
Not security-reviewed; in-memory login lockout; no real map tiles; model outputs are illustrative; PostgreSQL path untested here.
