from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import get_websocket_user
from .routers import alerts, auth, cameras, controls, detections, engines, search, watchlist
from .schemas import HealthOut
from .services import build_services
from .settings import Settings, get_settings

logging.basicConfig(
    level=os.getenv("THEA_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = build_services(resolved_settings)
        app.state.settings = resolved_settings
        app.state.services = services
        services.websocket.set_loop(asyncio.get_running_loop())
        if resolved_settings.using_default_password:
            logger.warning(
                "Using the default admin password. Set THEA_ADMIN_PASSWORD in .env before exposing this server."
            )
        services.cameras.start()
        if services.face_engine.requested_mode == "mock":
            services.face_engine.warmup()
        else:
            threading.Thread(
                target=services.face_engine.warmup,
                name="face-engine-warmup",
                daemon=True,
            ).start()
        logger.info(
            "%s %s started | cameras=%s | watchlist=%s | engine=%s",
            resolved_settings.app_name,
            __version__,
            len(services.cameras.list_status()),
            services.watchlist_index.size,
            services.face_engine.active_id,
        )
        try:
            yield
        finally:
            services.cameras.stop()
            logger.info("THEA stopped")

    app = FastAPI(
        title=f"{resolved_settings.app_name} API",
        version=__version__,
        description="Local CCTV face recognition, watchlist matching and real-time alerts.",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(controls.router)
    app.include_router(engines.router)
    app.include_router(cameras.router)
    app.include_router(watchlist.router)
    app.include_router(alerts.router)
    app.include_router(detections.router)
    app.include_router(search.router)

    @app.get("/api/health", response_model=HealthOut, tags=["system"])
    def health() -> dict:
        services = getattr(app.state, "services", None)
        if services is None:
            return {
                "status": "starting",
                "face_engine": {"ready": False},
                "watchlist_index": "unknown",
                "watchlist_people": 0,
                "cameras": 0,
                "cameras_online": 0,
                "alerts": 0,
                "started_at": None,
            }
        statuses = services.cameras.list_status()
        control_state = services.controls.snapshot()
        return {
            "status": "ok",
            "face_engine": services.face_engine.status,
            "watchlist_index": services.watchlist_index.backend,
            "watchlist_people": services.watchlist_index.size,
            "cameras": len([item for item in statuses if item.get("configured")]),
            "cameras_online": len([item for item in statuses if item.get("online")]),
            "alerts": services.database.count_alerts(),
            "monitoring_enabled": control_state["monitoring_enabled"],
            "match_threshold": control_state["match_threshold"],
            "uptime_seconds": round(max(0.0, time.time() - services.started_at), 1),
            "started_at": datetime.fromtimestamp(
                services.started_at, tz=timezone.utc
            ).isoformat(),
        }

    @app.websocket("/ws/alerts")
    async def alerts_socket(websocket: WebSocket, token: str | None = Query(None)) -> None:
        username = get_websocket_user(websocket, token)
        if username is None:
            await websocket.close(code=4401)
            return
        services = websocket.app.state.services
        await services.websocket.connect(websocket)
        try:
            await websocket.send_json(
                {
                    "type": "connected",
                    "username": username,
                    "watchlist_people": services.watchlist_index.size,
                }
            )
            while True:
                message = await websocket.receive_text()
                if message == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug("WebSocket closed unexpectedly", exc_info=True)
        finally:
            await services.websocket.disconnect(websocket)

    _mount_frontend(app, resolved_settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    if not dist.is_dir():
        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {
                "name": "THEA",
                "status": "ok",
                "docs": "/docs",
                "message": "Frontend not built. Run `npm run dev` in frontend/ or `npm run build`.",
            }

        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found") from None
        if candidate.is_file():
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend index not found")


app = create_app()
