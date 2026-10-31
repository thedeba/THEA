from __future__ import annotations

import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.domain import WatchlistMatch
from conftest import sample_jpeg


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["face_engine"]["requested_mode"] == "mock"


def test_cameras_require_auth(client: TestClient) -> None:
    assert client.get("/api/cameras").status_code == 401


def test_login_and_me(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/auth/me", headers=auth_headers).json()["username"] == "admin"
    bad = client.post(
        "/api/auth/login", json={"username": "admin", "password": "nope"}
    )
    assert bad.status_code == 401


def test_watchlist_search_and_history(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    image = sample_jpeg()
    files = [("files", ("photo-1.jpg", image, "image/jpeg"))]
    created = client.post(
        "/api/watchlist",
        data={"name": "Alex Morgan"},
        files=files,
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    person = created.json()
    person_id = person["id"]
    assert person["photo_count"] == 1
    assert person["thumbnail_url"]

    photo = client.get(person["thumbnail_url"], headers=auth_headers)
    assert photo.status_code == 200
    assert photo.headers["content-type"].startswith("image/jpeg")

    services = client.app.state.services
    name, embedding = services.database.get_person_embedding(person_id)
    alert_id = services.database.add_alert(
        person_id=person_id,
        person_name=name,
        camera_id="cam-1",
        camera_name="Camera One",
        confidence=0.93,
        snapshot_path=None,
        embedding=embedding,
        path_id="path-1",
        created_ts=time.time(),
    )

    history = client.get("/api/alerts?person=Alex", headers=auth_headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == alert_id

    search = client.post(
        "/api/search/face",
        files={"file": ("query.jpg", image, "image/jpeg")},
        data={"threshold": "0.2"},
        headers=auth_headers,
    )
    assert search.status_code == 200, search.text
    result = search.json()
    assert result["count"] >= 1
    assert result["results"][0]["id"] == alert_id
    assert result["results"][0]["similarity"] > 0.9

    extra = [("files", ("extra.jpg", image, "image/jpeg"))]
    added = client.post(
        f"/api/watchlist/{person_id}/photos",
        files=extra,
        headers=auth_headers,
    )
    assert added.status_code == 200
    assert added.json()["photo_count"] == 2
    too_many = client.post(
        f"/api/watchlist/{person_id}/photos",
        files=[
            ("files", ("extra-2.jpg", image, "image/jpeg")),
            ("files", ("extra-3.jpg", image, "image/jpeg")),
        ],
        headers=auth_headers,
    )
    assert too_many.status_code == 400

    renamed = client.patch(
        f"/api/watchlist/{person_id}",
        json={"name": "Alex M."},
        headers=auth_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Alex M."

    deleted = client.delete(f"/api/watchlist/{person_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get("/api/watchlist", headers=auth_headers).json() == []

    remaining = client.get("/api/alerts", headers=auth_headers).json()
    assert remaining["total"] == 1
    assert remaining["items"][0]["person_name"] == "Alex Morgan"


def test_admin_can_clear_alert_history(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    services = client.app.state.services
    snapshot = services.settings.snapshots_dir / "manual.jpg"
    snapshot.write_bytes(b"snapshot")
    services.database.add_alert(
        person_id=None,
        person_name="Unknown",
        camera_id="cam-1",
        camera_name="Camera One",
        confidence=0.8,
        snapshot_path="snapshots/manual.jpg",
        embedding=np.zeros(4, dtype=np.float32),
        path_id="path-clear",
        created_ts=time.time(),
    )

    assert client.delete("/api/alerts").status_code == 401

    response = client.delete("/api/alerts", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted"] == 1
    assert body["snapshots_removed"] == 1
    assert not snapshot.exists()
    assert client.get("/api/alerts", headers=auth_headers).json()["total"] == 0


def test_websocket_requires_token_and_accepts_valid_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    token = auth_headers["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(f"/ws/alerts?token={token}") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "connected"
        websocket.send_text("ping")
        assert websocket.receive_json()["type"] == "pong"


def test_face_detection_feed_and_thumbnails(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    services = client.app.state.services
    frame = cv2.imdecode(np.frombuffer(sample_jpeg(), np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None

    known = services.detections.record(
        camera_id="cam-1",
        camera_name="Camera One",
        track_id=4,
        bbox=(70, 40, 250, 220),
        detection_score=0.97,
        frame=frame,
        match=WatchlistMatch(person_id=7, name="Alex Morgan", score=0.91),
        threshold=0.45,
    )
    assert known is not None
    assert known["type"] == "face"
    assert known["known"] is True
    assert known["person_name"] == "Alex Morgan"
    assert known["match_percent"] == 91.0

    throttled = services.detections.record(
        camera_id="cam-1",
        camera_name="Camera One",
        track_id=4,
        bbox=(70, 40, 250, 220),
        detection_score=0.97,
        frame=frame,
        match=WatchlistMatch(person_id=7, name="Alex Morgan", score=0.91),
        threshold=0.45,
    )
    assert throttled is None

    unknown = services.detections.record(
        camera_id="cam-1",
        camera_name="Camera One",
        track_id=5,
        bbox=(80, 50, 240, 210),
        detection_score=0.82,
        frame=frame,
        match=None,
        threshold=0.45,
    )
    assert unknown is not None
    assert unknown["known"] is False
    assert unknown["person_name"] is None

    assert client.get("/api/detections").status_code == 401

    response = client.get("/api/detections?limit=5", headers=auth_headers)
    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["id"] for item in items] == [unknown["id"], known["id"]]
    assert "thumbnail" not in items[0]
    assert items[0]["thumbnail_url"].endswith("/thumbnail")

    thumbnail = client.get(items[0]["thumbnail_url"], headers=auth_headers)
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/jpeg"
    assert len(thumbnail.content) > 0
    assert client.get("/api/detections/missing/thumbnail", headers=auth_headers).status_code == 404


def test_runtime_controls(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/controls").status_code == 401
    initial = client.get("/api/controls", headers=auth_headers)
    assert initial.status_code == 200
    assert initial.json()["monitoring_enabled"] is True

    updated = client.patch(
        "/api/controls",
        json={"monitoring_enabled": False, "match_threshold": 0.62},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["monitoring_enabled"] is False
    assert body["match_threshold"] == 0.62

    health = client.get("/api/health").json()
    assert health["monitoring_enabled"] is False
    assert health["match_threshold"] == 0.62

    restored = client.patch(
        "/api/controls",
        json={"monitoring_enabled": True, "match_threshold": 0.45},
        headers=auth_headers,
    )
    assert restored.status_code == 200


def test_face_engine_catalog_and_selection(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/api/face-engines").status_code == 401

    response = client.get("/api/face-engines", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_id"] == "mock"
    ids = {engine["id"] for engine in body["engines"]}
    assert {"buffalo_l", "buffalo_s", "buffalo_sc", "antelopev2", "mock"} <= ids
    assert body["status"]["requested_mode"] == "mock"

    current = client.post("/api/face-engines/mock/select", headers=auth_headers)
    assert current.status_code == 200, current.text
    assert current.json()["changed"] is False

    missing = client.post("/api/face-engines/does-not-exist/select", headers=auth_headers)
    assert missing.status_code == 404


def test_face_engine_switch_reindexes_watchlist(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    from app.face_engine import FaceEngine, FaceEngineManager

    created = client.post(
        "/api/watchlist",
        data={"name": "Switch Test"},
        files=[("files", ("photo.jpg", sample_jpeg(), "image/jpeg"))],
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    services = client.app.state.services
    manager = services.face_engine
    monkeypatch.setattr(
        manager,
        "_build_engine",
        lambda engine_id: FaceEngine(mode="mock", model_name=engine_id),
    )
    switched = client.post(
        "/api/face-engines/buffalo_s/select", headers=auth_headers
    )
    assert switched.status_code == 200, switched.text
    body = switched.json()
    assert body["changed"] is True
    assert body["active_id"] == "buffalo_s"
    assert body["reindexed_people"] == 1
    assert body["reindexed_photos"] == 1
    assert body["status"]["switching"] is False
    assert manager.database.get_setting("face_engine") == "buffalo_s"
    assert services.watchlist_index.size == 1

    restarted = FaceEngineManager(services.settings, services.database)
    assert restarted.active_id == "buffalo_s"
