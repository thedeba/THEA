from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from ..auth import get_current_user, get_media_user
from ..dates import parse_timestamp
from ..dependencies import get_services
from ..schemas import AlertListOut, AlertOut, PathOut
from ..serializers import alert_to_out, path_to_out
from ..services import Services

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/paths", response_model=list[PathOut])
def list_paths(
    since_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    rows = services.database.list_paths(
        since_ts=time.time() - since_hours * 3600, limit=limit
    )
    return [path_to_out(row) for row in rows]


@router.get("/paths/{path_id}", response_model=list[AlertOut])
def get_path(
    path_id: str,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    alerts = services.database.get_path_alerts(path_id)
    if not alerts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")
    return [alert_to_out(alert) for alert in alerts]


@router.get("", response_model=AlertListOut)
def list_alerts(
    person_id: int | None = Query(None),
    person: str | None = Query(None),
    camera_id: str | None = Query(None),
    path_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    try:
        date_from_ts = parse_timestamp(date_from)
        date_to_ts = parse_timestamp(date_to, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    total, rows = services.database.list_alerts(
        person_id=person_id,
        person_name=person,
        camera_id=camera_id,
        path_id=path_id,
        date_from_ts=date_from_ts,
        date_to_ts=date_to_ts,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "items": [alert_to_out(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    alert = services.database.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert_to_out(alert)


@router.get("/{alert_id}/snapshot")
def alert_snapshot(
    alert_id: int,
    services: Services = Depends(get_services),
    _user: str = Depends(get_media_user),
) -> FileResponse:
    alert = services.database.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    relative = alert.get("snapshot_path")
    if not relative:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not available")
    path = _safe_media_path(services, relative)
    if path is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return FileResponse(path, media_type="image/jpeg")


def _safe_media_path(services: Services, relative: str) -> Path | None:
    path = (services.settings.data_dir / relative).resolve()
    try:
        path.relative_to(services.settings.data_dir.resolve())
    except ValueError:
        return None
    return path
