import os
import sys
from pathlib import Path

# Add backend directory to Python path for Vercel Serverless
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app as _app


async def app(scope, receive, send):
    """ASGI proxy wrapper that normalizes request path for Vercel rewrites."""
    if scope.get("type") in ("http", "websocket"):
        path = scope.get("path", "")
        if not path.startswith("/api") and not path.startswith("/docs") and not path.startswith("/openapi"):
            scope["path"] = f"/api{path}"
    await _app(scope, receive, send)
