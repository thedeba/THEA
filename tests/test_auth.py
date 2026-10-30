from __future__ import annotations

from dataclasses import replace

from app.auth import authenticate, create_access_token, verify_access_token
from app.settings import Settings


def settings() -> Settings:
    return Settings(secret_key="secret-one", admin_username="admin", admin_password="hunter2")


def test_token_round_trip() -> None:
    config = settings()
    token = create_access_token("admin", config, ttl_seconds=60)
    payload = verify_access_token(token, config)
    assert payload is not None
    assert payload["sub"] == "admin"


def test_expired_token_is_rejected() -> None:
    config = settings()
    token = create_access_token("admin", config, ttl_seconds=-1)
    assert verify_access_token(token, config) is None


def test_token_signed_with_other_secret_is_rejected() -> None:
    config = settings()
    other = replace(config, secret_key="secret-two")
    token = create_access_token("admin", config, ttl_seconds=60)
    assert verify_access_token(token, other) is None


def test_password_check() -> None:
    config = settings()
    assert authenticate("admin", "hunter2", config)
    assert not authenticate("admin", "wrong", config)
    assert not authenticate("nobody", "hunter2", config)
