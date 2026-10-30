from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any


class RuntimeControls:
    def __init__(self, match_threshold: float = 0.45, monitoring_enabled: bool = True):
        self._lock = threading.RLock()
        self._monitoring_enabled = bool(monitoring_enabled)
        self._match_threshold = self._clamp_threshold(match_threshold)
        self._updated_at = time.time()

    @staticmethod
    def _clamp_threshold(value: float) -> float:
        return min(0.95, max(0.1, round(float(value), 3)))

    @property
    def monitoring_enabled(self) -> bool:
        with self._lock:
            return self._monitoring_enabled

    @property
    def match_threshold(self) -> float:
        with self._lock:
            return self._match_threshold

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "monitoring_enabled": self._monitoring_enabled,
                "match_threshold": self._match_threshold,
                "updated_at": datetime.fromtimestamp(
                    self._updated_at, tz=timezone.utc
                ).isoformat(),
            }

    def update(
        self,
        *,
        monitoring_enabled: bool | None = None,
        match_threshold: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if monitoring_enabled is not None:
                self._monitoring_enabled = bool(monitoring_enabled)
            if match_threshold is not None:
                self._match_threshold = self._clamp_threshold(match_threshold)
            self._updated_at = time.time()
        return self.snapshot()
