from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from .alerts import AlertService
from .cameras_config import CameraConfig, CameraConfigError, load_cameras, mask_url
from .controls import RuntimeControls
from .domain import FaceDetection
from .face_engine import FaceEngineError, FaceEngineManager
from .matching import ConsecutiveMatchTracker, WatchlistIndex
from .settings import Settings
from .streams import (
    StreamResolveError,
    is_youtube_url,
    normalize_source,
    resolve_stream_url,
)
from .tracking import IoUTracker

logger = logging.getLogger(__name__)


class CameraWorker(threading.Thread):
    def __init__(
        self,
        camera: CameraConfig,
        settings: Settings,
        face_engine: FaceEngineManager,
        watchlist: WatchlistIndex,
        alerts: AlertService,
        controls: RuntimeControls,
    ):
        super().__init__(name=f"camera-{camera.id}", daemon=True)
        self.camera = camera
        self.settings = settings
        self.face_engine = face_engine
        self.watchlist = watchlist
        self.alerts = alerts
        self.controls = controls
        self.tracker = IoUTracker(iou_threshold=0.3, max_missed=max(2, int(camera.target_fps)))
        self.streaks = ConsecutiveMatchTracker(settings.consecutive_frames)
        self._stop_event = threading.Event()
        self._capture_lock = threading.Lock()
        self._capture: cv2.VideoCapture | None = None
        self._state_lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._online = False
        self._last_error: str | None = None
        self._last_frame_at: float | None = None
        self._started_at = time.time()
        self._frames_processed = 0
        self._faces_detected = 0
        self._alerts_created = 0
        self._engine_error_logged = False
        self._engine_error: str | None = None
        self._pending_frame: np.ndarray | None = None
        self._pending_seq = 0
        self._frame_lock = threading.Lock()
        self._overlays: list[
            tuple[tuple[int, int, int, int], str, tuple[int, int, int]]
        ] = []
        self._overlay_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------
    def stop(self) -> None:
        self._stop_event.set()
        with self._capture_lock:
            capture = self._capture
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass

    def latest_jpeg(self) -> bytes | None:
        with self._state_lock:
            return self._latest_jpeg

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            last_frame = self._last_frame_at
            return {
                "id": self.camera.id,
                "name": self.camera.name,
                "location": self.camera.location,
                "target_fps": self.camera.target_fps,
                "preview_fps": max(0.5, self.settings.stream_fps),
                "width": self.camera.width,
                "height": self.camera.height,
                "enabled": True,
                "online": self._online,
                "frames_processed": self._frames_processed,
                "faces_detected": self._faces_detected,
                "alerts_created": self._alerts_created,
                "last_frame_at": (
                    datetime.fromtimestamp(last_frame, tz=timezone.utc).isoformat()
                    if last_frame
                    else None
                ),
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "started_at": datetime.fromtimestamp(
                    self._started_at, tz=timezone.utc
                ).isoformat(),
                "last_error": self._engine_error or self._last_error,
            }

    # ------------------------------------------------------------------
    # Capture loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            f"rtsp_transport;{self.settings.rtsp_transport}",
        )
        detection_thread = threading.Thread(
            target=self._detection_loop,
            name=f"{self.name}-detect",
            daemon=True,
        )
        detection_thread.start()
        try:
            while not self._stop_event.is_set():
                try:
                    self._capture_loop()
                except Exception as exc:  # keep the worker alive on camera errors
                    logger.exception("Camera %s crashed", self.camera.id)
                    self._set_offline(str(exc))
                if not self._stop_event.is_set():
                    self._stop_event.wait(self.settings.camera_reconnect_seconds)
        finally:
            detection_thread.join(timeout=5)

    def _capture_loop(self) -> None:
        source = normalize_source(self.camera.rtsp_url)
        if is_youtube_url(source):
            logger.info("Resolving YouTube live stream for camera %s", self.camera.id)
            try:
                source = resolve_stream_url(source)
            except StreamResolveError as exc:
                self._set_offline(str(exc))
                return
        logger.info("Connecting camera %s (%s)", self.camera.id, mask_url(self.camera.rtsp_url))
        capture = cv2.VideoCapture(source)
        self._apply_capture_options(capture)
        with self._capture_lock:
            self._capture = capture
        if not capture.isOpened():
            self._set_offline("Could not open camera stream")
            capture.release()
            return

        fps = capture.get(cv2.CAP_PROP_FPS)
        if not fps or fps < 1 or fps > 120:
            fps = 25.0
        preview_fps = max(0.5, self.settings.stream_fps)
        frame_interval = 1.0 / min(60.0, fps)
        publish_interval = 1.0 / min(fps, preview_fps)
        logger.info(
            "Camera %s online (source %.0f fps, preview %.0f fps, detection %.1f fps)",
            self.camera.id,
            fps,
            min(fps, preview_fps),
            self.camera.target_fps,
        )

        try:
            next_frame = time.monotonic()
            last_publish = 0.0
            failures = 0
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now < next_frame:
                    self._stop_event.wait(min(next_frame - now, 0.05))
                    continue
                publish = now - last_publish >= publish_interval
                if publish:
                    ok, frame = capture.read()
                else:
                    ok, frame = capture.grab(), None
                if not ok:
                    failures += 1
                    if failures < 10:
                        self._set_error("Waiting for video frames")
                        next_frame = time.monotonic()
                        self._stop_event.wait(0.2)
                        continue
                    self._set_offline("Stream read failed")
                    break
                failures = 0
                if publish and frame is not None:
                    self._submit_frame(frame)
                    paused = not self.controls.monitoring_enabled
                    self._publish_frame(self._render_frame(frame, paused=paused))
                    last_publish = time.monotonic()
                next_frame += frame_interval
                if next_frame < time.monotonic():
                    next_frame = time.monotonic()
        finally:
            capture.release()
            with self._capture_lock:
                self._capture = None
            with self._frame_lock:
                self._pending_frame = None
            if not self._stop_event.is_set():
                self._set_offline(self._last_error or "Stream ended")

    def _apply_capture_options(self, capture: cv2.VideoCapture) -> None:
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self.camera.width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera.width)
        if self.camera.height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera.height)
        open_timeout = getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None)
        read_timeout = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
        if open_timeout is not None:
            capture.set(open_timeout, 10000)
        if read_timeout is not None:
            capture.set(read_timeout, 10000)

    def _submit_frame(self, frame: np.ndarray) -> None:
        with self._frame_lock:
            self._pending_frame = frame.copy()
            self._pending_seq += 1

    def _detection_loop(self) -> None:
        interval = 1.0 / max(0.5, self.camera.target_fps)
        last_seq = -1
        next_detection = 0.0
        while not self._stop_event.is_set():
            if not self.controls.monitoring_enabled:
                self._set_overlays([])
                self._stop_event.wait(0.1)
                continue
            now = time.monotonic()
            if now < next_detection:
                self._stop_event.wait(min(next_detection - now, 0.05))
                continue
            with self._frame_lock:
                frame = self._pending_frame
                seq = self._pending_seq
            if frame is None or seq == last_seq:
                self._stop_event.wait(0.01)
                continue
            last_seq = seq
            try:
                self._detect_frame(frame)
            except Exception:
                logger.exception("Detection loop failed on camera %s", self.camera.id)
            next_detection += interval
            if next_detection < time.monotonic():
                next_detection = time.monotonic()

    def _detect_frame(self, frame: np.ndarray) -> None:
        detections: list[FaceDetection] = []
        try:
            detections = self.face_engine.detect(frame)
            with self._state_lock:
                self._engine_error = None
        except FaceEngineError as exc:
            if not self._engine_error_logged:
                logger.error("Face engine unavailable for camera %s: %s", self.camera.id, exc)
                self._engine_error_logged = True
            with self._state_lock:
                self._engine_error = str(exc)
            self._set_error(str(exc))
        except Exception as exc:
            logger.exception("Face detection failed on camera %s", self.camera.id)
            self._set_error(f"Face detection failed: {exc}")

        tracked_faces = self.tracker.update(detections)
        self.streaks.prune(self.tracker.active_track_ids)
        overlays: list[tuple[tuple[int, int, int, int], str, tuple[int, int, int]]] = []
        threshold = self.controls.match_threshold

        for tracked in tracked_faces:
            face = tracked.face
            match = self.watchlist.match(face.embedding)
            confirmed = self.streaks.update(tracked.track_id, match, threshold)
            known = match is not None and match.score >= threshold
            if confirmed and match is not None:
                self.streaks.reset(tracked.track_id)
                try:
                    event = self.alerts.create_alert(
                        person_id=match.person_id,
                        person_name=match.name,
                        camera_id=self.camera.id,
                        camera_name=self.camera.name,
                        confidence=match.score,
                        frame=frame,
                        bbox=face.bbox,
                        embedding=face.embedding,
                    )
                except Exception:
                    logger.exception(
                        "Could not store alert for %s on camera %s",
                        match.name,
                        self.camera.id,
                    )
                    event = None
                if event is not None:
                    with self._state_lock:
                        self._alerts_created += 1

            label = (
                f"{match.name} {match.score * 100:.0f}%"
                if known and match is not None
                else "Unknown"
            )
            color = (46, 204, 113) if known else (240, 173, 78)
            bbox = tuple(int(value) for value in face.bbox)
            overlays.append((bbox, label, color))

        self._set_overlays(overlays)
        with self._state_lock:
            self._frames_processed += 1
            self._faces_detected += len(detections)

    def _set_overlays(
        self,
        overlays: list[tuple[tuple[int, int, int, int], str, tuple[int, int, int]]],
    ) -> None:
        with self._overlay_lock:
            self._overlays = overlays

    def _render_frame(self, frame: np.ndarray, paused: bool = False) -> np.ndarray:
        annotated = frame.copy()
        if paused:
            height, _width = annotated.shape[:2]
            cv2.putText(
                annotated,
                "MONITORING PAUSED",
                (24, max(34, height - 24)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (60, 200, 255),
                2,
                cv2.LINE_AA,
            )
            return annotated
        with self._overlay_lock:
            overlays = list(self._overlays)
        for bbox, label, color in overlays:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                annotated,
                label.encode("ascii", "replace").decode("ascii"),
                (x1, max(16, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        return annotated

    def _publish_frame(self, annotated: np.ndarray) -> None:
        ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            return
        jpeg = encoded.tobytes()
        with self._state_lock:
            self._latest_jpeg = jpeg
            self._online = True
            self._last_frame_at = time.time()
            self._last_error = None

    def _set_offline(self, error: str | None) -> None:
        with self._state_lock:
            self._online = False
            if error:
                self._last_error = error
        with self._frame_lock:
            self._pending_frame = None

    def _set_error(self, error: str) -> None:
        with self._state_lock:
            self._last_error = error


class CameraManager:
    def __init__(
        self,
        settings: Settings,
        face_engine: FaceEngineManager,
        watchlist: WatchlistIndex,
        alerts: AlertService,
        controls: RuntimeControls,
    ):
        self.settings = settings
        self.face_engine = face_engine
        self.watchlist = watchlist
        self.alerts = alerts
        self.controls = controls
        self._lock = threading.RLock()
        self._configs: list[CameraConfig] = []
        self._workers: dict[str, CameraWorker] = {}
        self._config_error: str | None = None
        self._load_config()

    def _load_config(self) -> None:
        try:
            self._configs = load_cameras(
                self.settings.cameras_file, default_fps=self.settings.target_fps
            )
            self._config_error = None
        except CameraConfigError as exc:
            self._config_error = str(exc)
            logger.error("Camera config error: %s", exc)
            self._configs = []

    def start(self) -> None:
        with self._lock:
            for camera in self._configs:
                if not camera.enabled or camera.id in self._workers:
                    continue
                worker = CameraWorker(
                    camera=camera,
                    settings=self.settings,
                    face_engine=self.face_engine,
                    watchlist=self.watchlist,
                    alerts=self.alerts,
                    controls=self.controls,
                )
                worker.start()
                self._workers[camera.id] = worker

    def stop(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=5)

    def reload(self) -> list[dict[str, Any]]:
        self.stop()
        with self._lock:
            self._load_config()
        self.start()
        return self.list_status()

    def get_worker(self, camera_id: str) -> CameraWorker | None:
        with self._lock:
            return self._workers.get(camera_id)

    def reconnect(self, camera_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            camera = next((item for item in self._configs if item.id == camera_id), None)
            worker = self._workers.pop(camera_id, None)
        if worker is not None:
            worker.stop()
            worker.join(timeout=5)
        if camera is None:
            return None
        if camera.enabled:
            new_worker = CameraWorker(
                camera=camera,
                settings=self.settings,
                face_engine=self.face_engine,
                watchlist=self.watchlist,
                alerts=self.alerts,
                controls=self.controls,
            )
            new_worker.start()
            with self._lock:
                self._workers[camera_id] = new_worker
        return self.list_status()

    def list_status(self) -> list[dict[str, Any]]:
        with self._lock:
            configs = list(self._configs)
            workers = dict(self._workers)
            config_error = self._config_error
        statuses: list[dict[str, Any]] = []
        for camera in configs:
            worker = workers.get(camera.id)
            if worker is not None:
                status = worker.status()
                status["configured"] = True
                statuses.append(status)
            else:
                statuses.append(
                    {
                        "id": camera.id,
                        "name": camera.name,
                        "location": camera.location,
                        "target_fps": camera.target_fps,
                        "preview_fps": max(0.5, self.settings.stream_fps),
                        "width": camera.width,
                        "height": camera.height,
                        "enabled": camera.enabled,
                        "online": False,
                        "frames_processed": 0,
                        "faces_detected": 0,
                        "alerts_created": 0,
                        "last_frame_at": None,
                        "uptime_seconds": 0,
                        "started_at": None,
                        "last_error": None if camera.enabled else "Camera is disabled",
                        "configured": True,
                    }
                )
        if config_error:
            statuses.append(
                {
                    "id": "_config",
                    "name": "Camera config",
                    "location": "",
                    "target_fps": self.settings.target_fps,
                    "preview_fps": max(0.5, self.settings.stream_fps),
                    "enabled": False,
                    "online": False,
                    "frames_processed": 0,
                    "faces_detected": 0,
                    "alerts_created": 0,
                    "last_frame_at": None,
                    "uptime_seconds": 0,
                    "started_at": None,
                    "last_error": config_error,
                    "configured": False,
                }
            )
        return statuses

    @property
    def config_error(self) -> str | None:
        with self._lock:
            return self._config_error
