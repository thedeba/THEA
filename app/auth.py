from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Depends, HTTPException, Query, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signature(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_access_token(username: str, settings: Settings, ttl_seconds: int | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + int(ttl_seconds if ttl_seconds is not None else settings.token_ttl_seconds),
    }
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{encoded_payload}.{_signature(settings.secret_key, encoded_payload)}"


def verify_access_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = _signature(settings.secret_key, encoded_payload)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not payload.get("sub"):
        return None
    try:
        expires_at = int(payload.get("exp", 0))
    except (TypeError, ValueError):
        return None
    if expires_at <= int(time.time()):
        return None
    return payload


def authenticate(username: str, password: str, settings: Settings) -> bool:
    username_ok = hmac.compare_digest(username.encode("utf-8"), settings.admin_username.encode("utf-8"))
    password_ok = hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))
    return username_ok and password_ok


def settings_from_app(app: Any) -> Settings:
    return getattr(app.state, "settings", None) or get_settings()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    settings = settings_from_app(request.app)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_access_token(credentials.credentials, settings)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(payload["sub"])


def get_media_user(
    request: Request,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Authenticate media requests. Browser <img> tags can pass ?token=..."""
    settings = settings_from_app(request.app)
    candidate = token or (credentials.credentials if credentials else None)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_access_token(candidate, settings)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return str(payload["sub"])


def get_websocket_user(websocket: WebSocket, token: str | None = None) -> str | None:
    settings = settings_from_app(websocket.app)
    if not token:
        return None
    payload = verify_access_token(token, settings)
    return str(payload["sub"]) if payload else None
