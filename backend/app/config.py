"""Environment-based configuration. No secrets are committed to source control."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# On Vercel and serverless environments, the filesystem is read-only except /tmp
_is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
_default_data_dir = Path("/tmp/himavah_data") if _is_serverless else BASE_DIR / "data"
DATA_DIR = Path(os.getenv("HIMAVAH_DATA_DIR", _default_data_dir))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# Development data layer: SQLite. Point DATABASE_URL at PostgreSQL (e.g.
# postgresql+psycopg://user:pass@db:5432/himavahpro) for production-oriented deployments.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'himavahpro.db'}")

# MongoDB Atlas configuration
MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://HimavahPro:Himavah%4026@cluster0.se6sibu.mongodb.net/himavahpro?retryWrites=true&w=majority"
)
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "himavahpro")
MONGODB_SYNC_ENABLED = _flag("HIMAVAH_MONGODB_SYNC", True)

# Demonstration authentication. Replace with an approved identity provider later
# (see app/auth.py: the IdentityProvider boundary).
DEMO_AUTH = _flag("HIMAVAH_DEMO_AUTH", True)
DEMO_PASSWORD = os.getenv("HIMAVAH_DEMO_PASSWORD", "demo-password")  # non-secret demo placeholder
DEMO_MFA_CODE = os.getenv("HIMAVAH_DEMO_MFA_CODE", "123456")  # non-secret demo placeholder
TOKEN_TTL_SECONDS = int(os.getenv("HIMAVAH_TOKEN_TTL", "28800"))

CORS_ORIGINS = [o.strip() for o in os.getenv("HIMAVAH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

# Re-anchor synthetic timestamps to "now" when the demo database is older than this many hours.
REBASE_AFTER_HOURS = float(os.getenv("HIMAVAH_REBASE_AFTER_HOURS", "6"))


def _load_secret() -> str:
    env = os.getenv("HIMAVAH_SECRET")
    if env:
        return env
    path = DATA_DIR / ".secret"
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_hex(32)
    path.write_text(value)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


SECRET = _load_secret()
