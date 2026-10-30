from __future__ import annotations

from fastapi import HTTPException, UploadFile, status


async def read_upload(upload: UploadFile, max_bytes: int) -> tuple[str, bytes]:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{upload.filename or 'File'} is too large",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{upload.filename or 'File'} is empty",
        )
    return upload.filename or "upload", data
