from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def build_test_settings(tmp_path: Path) -> Settings:
    base = Settings.load()
    cameras_file = tmp_path / "cameras.yaml"
    cameras_file.write_text("cameras: []\n", encoding="utf-8")
    settings = replace(
        base,
        admin_username="admin",
        admin_password="test-password",
        secret_key="test-secret-key",
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "thea.db",
        snapshots_dir=tmp_path / "data" / "snapshots",
        watchlist_dir=tmp_path / "data" / "watchlist",
        cameras_file=cameras_file,
        face_engine="mock",
        match_threshold=0.45,
        consecutive_frames=3,
        alert_cooldown_seconds=60,
        path_window_seconds=120,
        cors_origins=(),
        frontend_dist=tmp_path / "dist",
    )
    settings.ensure_dirs()
    return settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return build_test_settings(tmp_path)


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "test-password"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def sample_jpeg(seed: int = 0) -> bytes:
    image = np.full((240, 320, 3), 30, dtype=np.uint8)
    cv2.rectangle(image, (70, 40), (250, 220), (70 + seed * 5, 110, 160), -1)
    cv2.circle(image, (160, 120), 48, (190, 175, 155), -1)
    cv2.circle(image, (142, 108), 5, (30, 30, 30), -1)
    cv2.circle(image, (178, 108), 5, (30, 30, 30), -1)
    cv2.ellipse(image, (160, 145), (18, 8), 0, 0, 180, (60, 50, 45), 2)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()
