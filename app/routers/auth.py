from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import authenticate, create_access_token, get_current_user
from ..schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request) -> TokenResponse:
    settings = request.app.state.services.settings
    if not authenticate(payload.username, payload.password, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(payload.username, settings)
    return TokenResponse(
        access_token=token,
        expires_in=settings.token_ttl_seconds,
        username=payload.username,
    )


@router.get("/me", response_model=UserOut)
def me(username: str = Depends(get_current_user)) -> UserOut:
    return UserOut(username=username)
