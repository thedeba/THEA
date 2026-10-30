from __future__ import annotations

import numpy as np

from app.domain import WatchlistMatch
from app.matching import ConsecutiveMatchTracker
from app.vectors import cosine_similarity, l2_normalize, similarity_matrix


def test_consecutive_match_requires_three_frames() -> None:
    tracker = ConsecutiveMatchTracker(required=3)
    match = WatchlistMatch(person_id=1, name="Alex", score=0.8)
    assert tracker.update(10, match, 0.45) is False
    assert tracker.update(10, match, 0.45) is False
    assert tracker.update(10, match, 0.45) is True


def test_consecutive_match_resets_for_different_person() -> None:
    tracker = ConsecutiveMatchTracker(required=3)
    first = WatchlistMatch(person_id=1, name="Alex", score=0.8)
    second = WatchlistMatch(person_id=2, name="Sam", score=0.7)
    tracker.update(10, first, 0.45)
    tracker.update(10, first, 0.45)
    assert tracker.update(10, second, 0.45) is False
    assert tracker.update(10, second, 0.45) is False
    assert tracker.update(10, second, 0.45) is True


def test_low_score_breaks_streak() -> None:
    tracker = ConsecutiveMatchTracker(required=3)
    match = WatchlistMatch(person_id=1, name="Alex", score=0.8)
    tracker.update(10, match, 0.45)
    tracker.update(10, match, 0.45)
    assert tracker.update(10, match, 0.9) is False
    assert tracker.update(10, match, 0.45) is False


def test_cosine_helpers() -> None:
    a = l2_normalize(np.array([1.0, 0.0, 0.0]))
    b = l2_normalize(np.array([1.0, 1.0, 0.0]))
    assert cosine_similarity(a, a) == 1.0
    assert 0.6 < cosine_similarity(a, b) < 0.8
    scores = similarity_matrix(a, np.stack([a, b]))
    assert scores.shape == (2,)
    assert scores[0] > scores[1]
