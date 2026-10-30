from __future__ import annotations

import asyncio
from typing import AsyncIterator

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from ..auth import get_current_user, get_media_user
from ..dependencies import get_services
from ..schemas import CameraOut
from ..services import Services

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

_placeholder_cache: dict[str, bytes] = {}


def _placeholder_jpeg(name: str) -> bytes:
    if name in _placeholder_cache:
        return _placeholder_cache[name]
    image = np.full((360, 640, 3), 20, dtype=np.uint8)
    cv2.putText(
        image,
        "NO SIGNAL",
        (210, 175),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (90, 90, 90),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        name.encode("ascii", "replace").decode("ascii")[:42],
        (20, 335),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (140, 140, 140),
        1,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".jpg", image)
    payload = encoded.tobytes() if ok else b""
    _placeholder_cache[name] = payload
    return payload


@router.get("", response_model=list[CameraOut])
def list_cameras(
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    return services.cameras.list_status()


@router.post("/reload", response_model=list[CameraOut])
def reload_cameras(
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    return services.cameras.reload()


@router.post("/{camera_id}/reconnect", response_model=list[CameraOut])
def reconnect_camera(
    camera_id: str,
    services: Services = Depends(get_services),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    statuses = services.cameras.reconnect(camera_id)
    if statuses is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return statuses


@router.get("/{camera_id}/snapshot")
def camera_snapshot(
    camera_id: str,
    services: Services = Depends(get_services),
    _user: str = Depends(get_media_user),
) -> Response:
    worker = services.cameras.get_worker(camera_id)
    if worker is None:
        camera = next(
            (item for item in services.cameras.list_status() if item["id"] == camera_id),
            None,
        )
        if camera is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
        return Response(
            content=_placeholder_jpeg(camera["name"]),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store", "X-Camera-Online": "false"},
        )
    jpeg = worker.latest_jpeg()
    if jpeg is None:
        return Response(
            content=_placeholder_jpeg(worker.camera.name),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store", "X-Camera-Online": "false"},
        )
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Camera-Online": "true"},
    )


@router.get("/{camera_id}/stream")
async def camera_stream(
    camera_id: str,
    request: Request,
    services: Services = Depends(get_services),
    _user: str = Depends(get_media_user),
) -> StreamingResponse:
    worker = services.cameras.get_worker(camera_id)
    camera_status = next(
        (item for item in services.cameras.list_status() if item["id"] == camera_id), None
    )
    if worker is None and camera_status is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    camera_name = worker.camera.name if worker is not None else camera_status["name"]

    async def frames() -> AsyncIterator[bytes]:
        boundary = b"--frame\r\n"
        delay = 1.0 / max(0.5, services.settings.stream_fps)
        while True:
            if await request.is_disconnected():
                break
            jpeg = worker.latest_jpeg() if worker is not None else None
            if jpeg is None:
                jpeg = _placeholder_jpeg(camera_name)
                await asyncio.sleep(max(1.0, delay * 2))
            else:
                await asyncio.sleep(delay)
            yield (
                boundary
                + b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                + jpeg
                + b"\r\n"
            )

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
