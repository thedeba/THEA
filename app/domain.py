from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]
    score: float
    embedding: np.ndarray

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bbox
        return max(0, x2 - x1) * max(0, y2 - y1)


@dataclass
class TrackedFace:
    track_id: int
    face: FaceDetection


@dataclass
class WatchlistMatch:
    person_id: int
    name: str
    score: float
