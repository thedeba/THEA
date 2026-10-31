from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .db import Database
from .settings import Settings
from .ws import ConnectionManager

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, settings: Settings, database: Database, websocket: ConnectionManager):
        self.settings = settings
        self.database = database
        self.websocket = websocket
        self._lock = threading.Lock()

    def create_alert(
        self,
        *,
        person_id: int,
        person_name: str,
        camera_id: str,
        camera_name: str,
        confidence: float,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        embedding: np.ndarray,
    ) -> dict[str, Any] | None:
        now_ts = time.time()
        with self._lock:
            if self.database.has_recent_alert(
                person_id, camera_id, now_ts - self.settings.alert_cooldown_seconds
            ):
                return None

            previous = self.database.find_recent_alert_on_other_camera(
                person_id, camera_id, now_ts - self.settings.path_window_seconds
            )
            path_id = previous["path_id"] if previous else uuid.uuid4().hex

            snapshot_relative = self._save_snapshot(
                frame=frame,
                bbox=bbox,
                label=f"{person_name} {confidence * 100:.0f}%",
                camera_id=camera_id,
            )
            try:
                alert_id = self.database.add_alert(
                    person_id=person_id,
                    person_name=person_name,
                    camera_id=camera_id,
                    camera_name=camera_name,
                    confidence=confidence,
                    snapshot_path=snapshot_relative,
                    embedding=embedding,
                    path_id=path_id,
                    created_ts=now_ts,
                )
            except Exception:
                self._remove_snapshot(snapshot_relative)
                raise

        created_at = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        event = {
            "type": "alert",
            "id": alert_id,
            "person_id": person_id,
            "person_name": person_name,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "confidence": round(float(confidence), 4),
            "confidence_percent": round(float(confidence) * 100, 1),
            "snapshot_url": f"/api/alerts/{alert_id}/snapshot",
            "path_id": path_id,
            "created_at": created_at,
            "created_ts": now_ts,
        }
        self.websocket.publish_threadsafe(event)
        logger.info(
            "Alert: %s on %s (%.1f%%)", person_name, camera_name, confidence * 100
        )
        return event

    def clear_history(self) -> tuple[int, int]:
        with self._lock:
            deleted, snapshots = self.database.clear_alerts()
        removed = 0
        for relative_path in snapshots:
            path = self.settings.data_dir / relative_path
            if path.is_file() and self._is_inside_data_dir(path):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    logger.warning("Could not remove alert snapshot %s", relative_path)
        logger.info("Cleared %s alerts (%s snapshots)", deleted, removed)
        return deleted, removed

    def _save_snapshot(
        self,
        *,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        label: str,
        camera_id: str,
    ) -> str:
        self.settings.snapshots_dir.mkdir(parents=True, exist_ok=True)
        annotated = frame.copy()
        x1, y1, x2, y2 = bbox
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (46, 204, 113), 2)
        text = label.encode("ascii", "replace").decode("ascii")
        text_y = max(18, y1 - 8)
        cv2.putText(
            annotated,
            text,
            (x1, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (46, 204, 113),
            2,
            cv2.LINE_AA,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        safe_camera = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in camera_id)
        filename = f"{timestamp}_{safe_camera}_{uuid.uuid4().hex[:8]}.jpg"
        target = self.settings.snapshots_dir / filename
        ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            raise RuntimeError("Could not encode alert snapshot")
        target.write_bytes(encoded.tobytes())
        return f"snapshots/{filename}"

    def _remove_snapshot(self, relative_path: str) -> None:
        try:
            path = self.settings.data_dir / relative_path
            if path.is_file() and self._is_inside_data_dir(path):
                path.unlink()
        except OSError:
            pass

    def _is_inside_data_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.settings.data_dir.resolve())
            return True
        except ValueError:
            return False
