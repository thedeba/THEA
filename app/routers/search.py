from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from ..auth import get_current_user
from ..dates import parse_timestamp
from ..dependencies import get_services
from ..face_engine import FaceEngineError
from ..images import ImageError, decode_image
from ..schemas import SearchResponse
from ..serializers import alert_to_out
from ..services import Services
from ..uploads import read_upload

router = APIRouter(prefix="/api/search", tags=["search"])


def _run_search(
    services: Services,
    data: bytes,
    threshold: float,
    limit: int,
    camera_id: str | None,
    date_from_ts: float | None,
    date_to_ts: float | None,
) -> dict:
    try:
        image = decode_image(data)
    except ImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        detection = services.face_engine.detect_largest(image)
    except FaceEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No face found in the uploaded photo",
        )
    rows = services.database.search_alerts_by_embedding(
        detection.embedding,
        threshold=threshold,
        limit=limit,
        camera_id=camera_id,
        date_from_ts=date_from_ts,
        date_to_ts=date_to_ts,
    )
    results = []
    for row in rows:
        item = alert_to_out(row)
        item["similarity"] = round(float(row["similarity"]), 4)
        results.append(item)
    return {
        "query_face": {
            "bbox": list(detection.bbox),
            "detection_score": round(float(detection.score), 4),
        },
        "threshold": threshold,
        "count": len(results),
        "results": results,
    }


@router.post("/face", response_model=SearchResponse)
async def search_face(
    file: UploadFile = File(...),
    threshold: float | None = Form(None, ge=0.0, le=1.0),
    limit: int = Form(50, ge=1, le=200),
    camera_id: str | None = Form(None),
    date_from: str | None = Form(None),
    date_to: str | None = Form(None),
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    max_bytes = services.settings.max_upload_mb * 1024 * 1024
    _filename, data = await read_upload(file, max_bytes)
    try:
        date_from_ts = parse_timestamp(date_from)
        date_to_ts = parse_timestamp(date_to, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    effective_threshold = threshold if threshold is not None else services.settings.match_threshold
    return await run_in_threadpool(
        _run_search,
        services,
        data,
        effective_threshold,
        limit,
        camera_id or None,
        date_from_ts,
        date_to_ts,
    )
