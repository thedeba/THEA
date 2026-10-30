from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user
from ..dependencies import get_services
from ..face_engine import (
    EngineSelectionError,
    FaceEngineError,
    get_engine_profile,
)
from ..schemas import EngineSelectOut, FaceEnginesOut
from ..services import Services

router = APIRouter(prefix="/api/face-engines", tags=["system"])


@router.get("", response_model=FaceEnginesOut)
def list_face_engines(
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    return services.face_engine.snapshot()


@router.post("/{engine_id}/select", response_model=EngineSelectOut)
def select_face_engine(
    engine_id: str,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    try:
        profile = get_engine_profile(engine_id)
    except EngineSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    try:
        result = services.face_engine.select(
            profile.id,
            services.watchlist.reindex_with_engine,
        )
    except FaceEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    people = result["reindexed_people"]
    photos = result["reindexed_photos"]
    if not result["changed"]:
        message = f"{profile.label} is already active"
    else:
        message = f"{profile.label} activated"
        if photos:
            message += f"; re-indexed {people} people across {photos} photos"
    return {
        **result,
        "message": message,
    }
