from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from .domain import WatchlistMatch
from .settings import Settings
from .ws import ConnectionManager


class DetectionService:
    """Keeps a small in-memory feed of recent faces for live analysis."""

    def __init__(
        self,
        settings: Settings,
        websocket: ConnectionManager,
        max_items: int = 40,
        min_interval: float = 1.8,
    ):
        self.settings = settings
        self.websocket = websocket
        self._lock = threading.Lock()
        self._items: deque[dict[str, Any]] = deque(maxlen=max_items)
        self._last_seen: dict[tuple[str, int], tuple[float, str]] = {}
        self._min_interval = max(0.2, float(min_interval))

    def record(
        self,
        *,
        camera_id: str,
        camera_name: str,
        track_id: int,
        bbox: tuple[int, int, int, int],
        detection_score: float,
        frame: np.ndarray,
        match: WatchlistMatch | None,
        threshold: float,
    ) -> dict[str, Any] | None:
        now = time.time()
        known = match is not None and match.score >= threshold
        signature = f"person:{match.person_id}" if known and match is not None else "unknown"
        key = (camera_id, track_id)

        with self._lock:
            previous = self._last_seen.get(key)
            if (
                previous is not None
                and previous[1] == signature
                and now - previous[0] < self._min_interval
            ):
                return None
            self._last_seen[key] = (now, signature)
            if len(self._last_seen) > 256:
                cutoff = now - 120
                self._last_seen = {
                    item_key: value
                    for item_key, value in self._last_seen.items()
                    if value[0] >= cutoff
                }

        thumbnail = self._crop_face(frame, bbox)
        if thumbnail is None:
            return None

        detection_id = uuid.uuid4().hex
        item: dict[str, Any] = {
            "id": detection_id,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "track_id": int(track_id),
            "person_id": match.person_id if known and match is not None else None,
            "person_name": match.name if match is not None else None,
            "known": known,
            "match_score": round(float(match.score), 4) if match is not None else None,
            "match_percent": (
                round(float(match.score) * 100, 1) if match is not None else None
            ),
            "detection_score": round(float(detection_score), 4),
            "bbox": [int(value) for value in bbox],
            "width": max(0, int(bbox[2]) - int(bbox[0])),
            "height": max(0, int(bbox[3]) - int(bbox[1])),
            "created_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "created_ts": now,
            "thumbnail": thumbnail,
        }

        with self._lock:
            self._items.appendleft(item)

        event = self._public(item)
        event["type"] = "face"
        self.websocket.publish_threadsafe(event)
        return event

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items)[: max(1, int(limit))]
        return [self._public(item) for item in items]

    def get_thumbnail(self, detection_id: str) -> bytes | None:
        with self._lock:
            for item in self._items:
                if item["id"] == detection_id:
                    return item["thumbnail"]
        return None

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        public = {key: value for key, value in item.items() if key != "thumbnail"}
        public["thumbnail_url"] = f"/api/detections/{item['id']}/thumbnail"
        return public

    def _crop_face(
        self, frame: np.ndarray, bbox: tuple[int, int, int, int]
    ) -> bytes | None:
        if frame is None or frame.size == 0:
            return None
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = (int(value) for value in bbox)
        face_width = x2 - x1
        face_height = y2 - y1
        if face_width <= 0 or face_height <= 0:
            return None

        margin_x = int(face_width * 0.35)
        margin_y = int(face_height * 0.35)
        x1 = max(0, x1 - margin_x)
        y1 = max(0, y1 - margin_y)
        x2 = min(width, x2 + margin_x)
        y2 = min(height, y2 + margin_y)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        side = max(crop.shape[0], crop.shape[1])
        square = np.zeros((side, side, 3), dtype=crop.dtype)
        offset_y = (side - crop.shape[0]) // 2
        offset_x = (side - crop.shape[1]) // 2
        square[
            offset_y : offset_y + crop.shape[0],
            offset_x : offset_x + crop.shape[1],
        ] = crop
        target = 320
        resized = cv2.resize(square, (target, target), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(
            ".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 88]
        )
        if not ok:
            return None
        return encoded.tobytes()
