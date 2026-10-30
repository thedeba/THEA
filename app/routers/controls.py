from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..dependencies import get_services
from ..schemas import ControlsOut, ControlsUpdate
from ..services import Services

router = APIRouter(prefix="/api/controls", tags=["system"])


def _snapshot(services: Services) -> dict[str, Any]:
    controls = services.controls.snapshot()
    statuses = services.cameras.list_status()
    now = datetime.now(tz=timezone.utc)
    return {
        **controls,
        "consecutive_frames": services.settings.consecutive_frames,
        "cameras": len([item for item in statuses if item.get("configured")]),
        "cameras_online": len([item for item in statuses if item.get("online")]),
        "uptime_seconds": round(max(0.0, now.timestamp() - services.started_at), 1),
        "server_time": now.isoformat(),
    }


@router.get("", response_model=ControlsOut)
def get_controls(
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict[str, Any]:
    return _snapshot(services)


@router.patch("", response_model=ControlsOut)
def update_controls(
    payload: ControlsUpdate,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict[str, Any]:
    services.controls.update(
        monitoring_enabled=payload.monitoring_enabled,
        match_threshold=payload.match_threshold,
    )
    return _snapshot(services)
