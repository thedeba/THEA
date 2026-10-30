from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from .db import Database
from .domain import WatchlistMatch
from .vectors import l2_normalize

logger = logging.getLogger(__name__)


class WatchlistIndex:
    """In-memory cosine index over averaged watchlist embeddings.

    FAISS is used when available; otherwise a NumPy dot product is used. The
    NumPy path is perfectly fine for a home/office watchlist and keeps the
    system usable if faiss-cpu cannot be installed on a platform.
    """

    def __init__(self, database: Database, prefer_faiss: bool = True):
        self.database = database
        self._lock = threading.RLock()
        self._ids: list[int] = []
        self._names: list[str] = []
        self._matrix = np.zeros((0, 0), dtype=np.float32)
        self._index = None
        self._faiss = None
        if prefer_faiss:
            try:
                import faiss  # type: ignore

                self._faiss = faiss
            except Exception:
                logger.info("FAISS not available; using NumPy cosine search")
        self.reload()

    @property
    def backend(self) -> str:
        return "faiss" if self._index is not None else "numpy"

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._ids)

    def reload(self) -> None:
        rows = self.database.all_person_embeddings()
        ids = [row[0] for row in rows]
        names = [row[1] for row in rows]
        matrix = (
            np.stack([l2_normalize(row[2]) for row in rows]).astype(np.float32)
            if rows
            else np.zeros((0, 0), dtype=np.float32)
        )
        index = None
        if self._faiss is not None and matrix.size:
            index = self._faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
        with self._lock:
            self._ids = ids
            self._names = names
            self._matrix = matrix
            self._index = index

    def match(
        self, embedding: np.ndarray, threshold: float | None = None
    ) -> WatchlistMatch | None:
        query = l2_normalize(embedding).astype(np.float32)
        with self._lock:
            if not self._ids:
                return None
            if self._index is not None:
                scores, indices = self._index.search(query.reshape(1, -1), 1)
                score = float(scores[0][0])
                position = int(indices[0][0])
            else:
                scores = self._matrix @ query
                position = int(np.argmax(scores))
                score = float(scores[position])
            person_id = self._ids[position]
            name = self._names[position]
        if threshold is not None and score < threshold:
            return None
        return WatchlistMatch(person_id=person_id, name=name, score=score)


@dataclass
class _Streak:
    person_id: int
    name: str
    count: int
    score: float


class ConsecutiveMatchTracker:
    """Require N consecutive frames with the same person before confirming."""

    def __init__(self, required: int = 3):
        self.required = max(1, int(required))
        self._states: dict[int, _Streak] = {}
        self._lock = threading.Lock()

    def update(
        self,
        track_id: int,
        match: WatchlistMatch | None,
        threshold: float,
    ) -> bool:
        with self._lock:
            if match is None or match.score < threshold:
                self._states.pop(track_id, None)
                return False
            state = self._states.get(track_id)
            if state is not None and state.person_id == match.person_id:
                state.count += 1
                state.score = match.score
                state.name = match.name
            else:
                state = _Streak(
                    person_id=match.person_id,
                    name=match.name,
                    count=1,
                    score=match.score,
                )
                self._states[track_id] = state
            return state.count == self.required

    def reset(self, track_id: int) -> None:
        with self._lock:
            self._states.pop(track_id, None)

    def prune(self, active_track_ids: set[int]) -> None:
        with self._lock:
            for track_id in list(self._states):
                if track_id not in active_track_ids:
                    self._states.pop(track_id, None)
