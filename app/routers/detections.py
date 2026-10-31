from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..auth import get_current_user, get_media_user
from ..dependencies import get_services
from ..schemas import DetectionOut
from ..services import Services

router = APIRouter(prefix="/api/detections", tags=["detections"])


@router.get("", response_model=list[DetectionOut])
def list_detections(
    limit: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    return services.detections.list_recent(limit=limit)


@router.get("/{detection_id}/thumbnail")
def detection_thumbnail(
    detection_id: str,
    services: Services = Depends(get_services),
    _user: str = Depends(get_media_user),
) -> Response:
    thumbnail = services.detections.get_thumbnail(detection_id)
    if thumbnail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found"
        )
    return Response(
        content=thumbnail,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
