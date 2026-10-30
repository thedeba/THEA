from __future__ import annotations

import numpy as np

from app.alerts import AlertService
from app.db import Database
from app.settings import Settings
from app.vectors import l2_normalize


class FakeWebsocket:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish_threadsafe(self, event: dict) -> None:
        self.events.append(event)


def test_cross_camera_path_linking_and_cooldown(settings: Settings) -> None:
    settings.ensure_dirs()
    database = Database(settings.db_path)
    database.init()
    embedding = l2_normalize(np.arange(1, 513, dtype=np.float32))
    person_id = database.create_person("Alex", embedding, [("watchlist/test/a.jpg", embedding)])
    websocket = FakeWebsocket()
    service = AlertService(settings, database, websocket)
    frame = np.full((120, 160, 3), 40, dtype=np.uint8)
    bbox = (30, 20, 90, 90)

    first = service.create_alert(
        person_id=person_id,
        person_name="Alex",
        camera_id="cam-1",
        camera_name="Camera One",
        confidence=0.88,
        frame=frame,
        bbox=bbox,
        embedding=embedding,
    )
    second = service.create_alert(
        person_id=person_id,
        person_name="Alex",
        camera_id="cam-2",
        camera_name="Camera Two",
        confidence=0.9,
        frame=frame,
        bbox=bbox,
        embedding=embedding,
    )
    blocked = service.create_alert(
        person_id=person_id,
        person_name="Alex",
        camera_id="cam-1",
        camera_name="Camera One",
        confidence=0.91,
        frame=frame,
        bbox=bbox,
        embedding=embedding,
    )

    assert first is not None
    assert second is not None
    assert blocked is None
    assert first["path_id"] == second["path_id"]
    assert len(websocket.events) == 2
    stored = database.get_alert(first["id"])
    assert stored is not None
    snapshot = settings.data_dir / stored["snapshot_path"]
    assert snapshot.is_file()

    total, rows = database.list_alerts(limit=10)
    assert total == 2
    assert len(rows) == 2
