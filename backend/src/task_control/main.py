from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from task_control.api.correlation import CorrelationIdMiddleware
from task_control.api.errors import install_error_handlers
from task_control.api.security_headers import SecurityHeadersMiddleware
from task_control.api.v1 import (
    audit,
    auth,
    definitions,
    health,
    runs,
    schedules,
    scripts,
    stats,
    targets,
    users,
)
from task_control.config import get_settings
from task_control.infrastructure.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Task Control Center API",
        version="1.0.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(definitions.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(schedules.router, prefix="/api/v1")
    app.include_router(targets.router, prefix="/api/v1")
    app.include_router(stats.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(scripts.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="not found")
            return FileResponse(dist / "index.html")

    return app


app = create_app()
