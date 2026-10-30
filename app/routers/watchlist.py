from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from ..auth import get_current_user, get_media_user
from ..dependencies import get_services
from ..schemas import NameUpdate, PersonOut
from ..serializers import person_to_out
from ..services import Services
from ..uploads import read_upload
from ..watchlist_service import WatchlistError

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[PersonOut])
def list_people(
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    return [person_to_out(person) for person in services.watchlist.list_people()]


@router.post("", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
async def add_person(
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    max_bytes = services.settings.max_upload_mb * 1024 * 1024
    uploads = [await read_upload(upload, max_bytes) for upload in files]
    try:
        person = await run_in_threadpool(services.watchlist.add_person, name, uploads)
    except WatchlistError as exc:
        raise _bad_request(exc) from exc
    return person_to_out(person)


@router.get("/{person_id}", response_model=PersonOut)
def get_person(
    person_id: int,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    person = services.watchlist.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return person_to_out(person)


@router.patch("/{person_id}", response_model=PersonOut)
def rename_person(
    person_id: int,
    payload: NameUpdate,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    try:
        person = services.watchlist.rename(person_id, payload.name)
    except WatchlistError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return person_to_out(person)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> Response:
    try:
        services.watchlist.delete(person_id)
    except WatchlistError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{person_id}/photos", response_model=PersonOut)
async def add_photos(
    person_id: int,
    files: list[UploadFile] = File(...),
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> dict:
    max_bytes = services.settings.max_upload_mb * 1024 * 1024
    uploads = [await read_upload(upload, max_bytes) for upload in files]
    try:
        person = await run_in_threadpool(services.watchlist.add_photos, person_id, uploads)
    except WatchlistError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise _bad_request(exc) from exc
    return person_to_out(person)


@router.get("/{person_id}/photos/{photo_id}")
def person_photo(
    person_id: int,
    photo_id: int,
    services: Services = Depends(get_services),
    _user: str = Depends(get_media_user),
) -> FileResponse:
    path = services.watchlist.get_photo_path(person_id, photo_id)
    if path is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    return FileResponse(path, media_type="image/jpeg")
