from __future__ import annotations

import numpy as np

from app.domain import FaceDetection
from app.tracking import IoUTracker, bbox_iou


def detection(box: tuple[int, int, int, int]) -> FaceDetection:
    return FaceDetection(bbox=box, score=0.9, embedding=np.ones(8, dtype=np.float32))


def test_iou_tracker_keeps_identity_across_frames() -> None:
    tracker = IoUTracker(iou_threshold=0.3, max_missed=2)
    first = tracker.update([detection((10, 10, 60, 60))])
    second = tracker.update([detection((12, 12, 62, 62))])
    assert len(first) == 1
    assert len(second) == 1
    assert first[0].track_id == second[0].track_id


def test_iou_tracker_assigns_new_id_for_separate_face() -> None:
    tracker = IoUTracker(iou_threshold=0.3, max_missed=2)
    first = tracker.update([detection((10, 10, 60, 60))])
    second = tracker.update([detection((200, 200, 250, 250))])
    assert first[0].track_id != second[0].track_id


def test_iou_tracker_expires_missing_tracks() -> None:
    tracker = IoUTracker(iou_threshold=0.3, max_missed=1)
    tracker.update([detection((10, 10, 60, 60))])
    tracker.update([])
    tracker.update([])
    assert tracker.active_track_ids == set()


def test_bbox_iou() -> None:
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
