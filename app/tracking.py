from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .domain import FaceDetection, TrackedFace


def bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_width = max(0, inter_x2 - inter_x1)
    inter_height = max(0, inter_y2 - inter_y1)
    intersection = inter_width * inter_height
    if intersection == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    bbox: tuple[int, int, int, int]
    embedding: np.ndarray
    last_frame: int
    missed: int = 0
    hits: int = 1


class IoUTracker:
    """Lightweight face tracker that keeps identity across sampled frames."""

    def __init__(self, iou_threshold: float = 0.3, max_missed: int = 5):
        self.iou_threshold = iou_threshold
        self.max_missed = max_missed
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1
        self._frame = 0

    @property
    def active_track_ids(self) -> set[int]:
        return set(self._tracks)

    def update(self, detections: list[FaceDetection]) -> list[TrackedFace]:
        self._frame += 1
        if not detections:
            for track in list(self._tracks.values()):
                track.missed += 1
                if track.missed > self.max_missed:
                    self._tracks.pop(track.track_id, None)
            return []

        pairs: list[tuple[float, int, int]] = []
        for track in self._tracks.values():
            for detection_index, detection in enumerate(detections):
                score = bbox_iou(track.bbox, detection.bbox)
                if score >= self.iou_threshold:
                    pairs.append((score, track.track_id, detection_index))
        pairs.sort(reverse=True)

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        assignments: dict[int, int] = {}
        for _score, track_id, detection_index in pairs:
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)
            assignments[detection_index] = track_id
            track = self._tracks[track_id]
            detection = detections[detection_index]
            track.bbox = detection.bbox
            track.embedding = detection.embedding
            track.last_frame = self._frame
            track.missed = 0
            track.hits += 1

        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track = _Track(
                track_id=self._next_id,
                bbox=detection.bbox,
                embedding=detection.embedding,
                last_frame=self._frame,
            )
            self._tracks[track.track_id] = track
            self._next_id += 1
            assignments[detection_index] = track.track_id

        for track in list(self._tracks.values()):
            if track.track_id in matched_tracks:
                continue
            if track.last_frame != self._frame:
                track.missed += 1
                if track.missed > self.max_missed:
                    self._tracks.pop(track.track_id, None)

        return [
            TrackedFace(track_id=assignments[index], face=detection)
            for index, detection in enumerate(detections)
            if index in assignments and assignments[index] in self._tracks
        ]
