from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

import cv2
import numpy as np

from .domain import FaceDetection
from .vectors import EMBEDDING_DIM, l2_normalize

if TYPE_CHECKING:
    from .db import Database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineProfile:
    id: str
    label: str
    model: str | None
    description: str
    tag: str
    recommended: bool = False
    development: bool = False

    def public(self) -> dict[str, Any]:
        cached = self.id == "mock"
        if not cached:
            cached = (Path.home() / ".insightface" / "models" / self.id).is_dir()
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "tag": self.tag,
            "recommended": self.recommended,
            "development": self.development,
            "cached": cached,
        }


ENGINE_PROFILES: tuple[EngineProfile, ...] = (
    EngineProfile(
        id="buffalo_l",
        label="Buffalo L",
        model="buffalo_l",
        description="Balanced accuracy and speed for home and office cameras.",
        tag="Recommended",
        recommended=True,
    ),
    EngineProfile(
        id="buffalo_s",
        label="Buffalo S",
        model="buffalo_s",
        description="Lighter model that uses less CPU and memory.",
        tag="Fast",
    ),
    EngineProfile(
        id="buffalo_sc",
        label="Buffalo SC",
        model="buffalo_sc",
        description="Compact model for lower-powered machines.",
        tag="Light",
    ),
    EngineProfile(
        id="antelopev2",
        label="Antelope V2",
        model="antelopev2",
        description="Higher accuracy for difficult angles; heavier to run.",
        tag="Accurate",
    ),
    EngineProfile(
        id="mock",
        label="Mock engine",
        model=None,
        description="Development-only Haar detector without real recognition.",
        tag="Debug",
        development=True,
    ),
)

_PROFILES_BY_ID = {profile.id: profile for profile in ENGINE_PROFILES}
DEFAULT_ENGINE_ID = "buffalo_l"
ENGINE_SETTING_KEY = "face_engine"


class EngineSelectionError(ValueError):
    pass


def engine_profiles() -> tuple[EngineProfile, ...]:
    return ENGINE_PROFILES


def get_engine_profile(engine_id: str) -> EngineProfile:
    profile = _PROFILES_BY_ID.get((engine_id or "").strip())
    if profile is None:
        raise EngineSelectionError(f"Unknown face engine: {engine_id}")
    return profile


def default_engine_id(settings: Any) -> str:
    requested = (getattr(settings, "face_engine", "auto") or "auto").lower()
    if requested == "mock":
        return "mock"
    model_name = getattr(settings, "insightface_model", DEFAULT_ENGINE_ID)
    return model_name if model_name in _PROFILES_BY_ID else DEFAULT_ENGINE_ID


def _normalize_model_directory(model_name: str) -> None:
    """Flatten archives (notably antelopev2) extracted into a nested folder."""
    root = Path.home() / ".insightface" / "models" / model_name
    if not root.is_dir() or any(root.glob("*.onnx")):
        return
    nested = root / model_name
    if not nested.is_dir() or not any(nested.glob("*.onnx")):
        return
    for child in list(nested.iterdir()):
        target = root / child.name
        if target.exists():
            continue
        shutil.move(str(child), str(target))
    try:
        nested.rmdir()
    except OSError:
        pass
    logger.info("Normalized nested InsightFace model directory for %s", model_name)


class FaceEngineError(RuntimeError):
    pass


class FaceEngine:
    """Lazy InsightFace wrapper.

    `THEA_FACE_ENGINE=mock` provides a deterministic development fallback that
    uses OpenCV's Haar detector and a simple pixel embedding. It is useful for
    UI work and tests, but it is not a substitute for InsightFace.
    """

    def __init__(
        self,
        mode: str = "auto",
        model_name: str = "buffalo_l",
        det_size: int = 640,
        min_face_score: float = 0.5,
    ):
        self.requested_mode = (mode or "auto").lower()
        self.model_name = model_name
        self.det_size = det_size
        self.min_face_score = min_face_score
        self._app: Any = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._loaded = False
        self._error: str | None = None
        self._backend = "unloaded"
        self._mock_cascade: cv2.CascadeClassifier | None = None

    @property
    def status(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "backend": self._backend,
            "ready": self._loaded,
            "model": self.model_name,
            "error": self._error,
        }

    def warmup(self) -> None:
        try:
            self._ensure_loaded()
            if self._backend == "mock":
                logger.info("Face engine ready: %s", self._backend)
                return
            blank = np.zeros((self.det_size, self.det_size, 3), dtype=np.uint8)
            self.detect(blank)
            logger.info("Face engine ready: %s", self._backend)
        except Exception as exc:  # pragma: no cover - depends on local install
            logger.warning("Face engine warmup failed: %s", exc)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            if self.requested_mode == "mock":
                self._mock_cascade = cv2.CascadeClassifier(
                    os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                )
                self._backend = "mock"
                self._loaded = True
                return

            try:
                import onnxruntime
                from insightface.app import FaceAnalysis
            except Exception as exc:
                self._error = (
                    "InsightFace is not installed. Install backend requirements or set "
                    "THEA_FACE_ENGINE=mock for a development-only fallback."
                )
                raise FaceEngineError(self._error) from exc

            try:
                available = onnxruntime.get_available_providers()
                if "CUDAExecutionProvider" in available:
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    ctx_id = 0
                else:
                    providers = ["CPUExecutionProvider"]
                    ctx_id = -1
                _normalize_model_directory(self.model_name)
                app = FaceAnalysis(name=self.model_name, providers=providers)
                app.prepare(ctx_id=ctx_id, det_size=(self.det_size, self.det_size))
                self._app = app
                self._backend = "insightface"
                self._loaded = True
                self._error = None
            except Exception as exc:
                detail = str(exc).strip() or exc.__class__.__name__
                self._error = (
                    f"Could not initialize InsightFace ({self.model_name}): {detail}"
                )
                raise FaceEngineError(self._error) from exc

    def detect(self, image_bgr: np.ndarray) -> list[FaceDetection]:
        if image_bgr is None or image_bgr.size == 0:
            return []
        self._ensure_loaded()
        if self._backend == "mock":
            with self._lock:
                return self._mock_detect(image_bgr)
        assert self._app is not None
        with self._lock:
            faces = self._app.get(image_bgr, max_num=0)
        detections: list[FaceDetection] = []
        height, width = image_bgr.shape[:2]
        for face in faces:
            score = float(getattr(face, "det_score", 0.0))
            if score < self.min_face_score:
                continue
            embedding = getattr(face, "normed_embedding", None)
            if embedding is None:
                embedding = getattr(face, "embedding", None)
            if embedding is None:
                continue
            x1, y1, x2, y2 = [int(round(value)) for value in face.bbox[:4]]
            bbox = (
                max(0, min(width - 1, x1)),
                max(0, min(height - 1, y1)),
                max(0, min(width - 1, x2)),
                max(0, min(height - 1, y2)),
            )
            detections.append(
                FaceDetection(
                    bbox=bbox,
                    score=score,
                    embedding=l2_normalize(np.asarray(embedding, dtype=np.float32)),
                )
            )
        return detections

    def detect_largest(self, image_bgr: np.ndarray) -> FaceDetection | None:
        detections = self.detect(image_bgr)
        if not detections:
            return None
        return max(detections, key=lambda detection: detection.area)

    def _mock_detect(self, image_bgr: np.ndarray) -> list[FaceDetection]:
        height, width = image_bgr.shape[:2]
        boxes: list[tuple[int, int, int, int]] = []
        if self._mock_cascade is not None and not self._mock_cascade.empty():
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            found = self._mock_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
            boxes = [
                (int(x), int(y), int(x + w), int(y + h))
                for x, y, w, h in found
            ]
        if not boxes:
            side = max(40, int(min(width, height) * 0.45))
            x1 = max(0, (width - side) // 2)
            y1 = max(0, (height - side) // 2)
            boxes = [(x1, y1, min(width, x1 + side), min(height, y1 + side))]

        detections: list[FaceDetection] = []
        for x1, y1, x2, y2 in boxes:
            crop = image_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (16, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
            vector = resized.reshape(-1)
            vector -= float(vector.mean())
            if vector.size < EMBEDDING_DIM:
                vector = np.pad(vector, (0, EMBEDDING_DIM - vector.size))
            detections.append(
                FaceDetection(
                    bbox=(x1, y1, x2, y2),
                    score=1.0,
                    embedding=l2_normalize(vector[:EMBEDDING_DIM]),
                )
            )
        return detections


class FaceEngineManager:
    """Owns the active face engine and swaps profiles at runtime.

    Detection calls are serialized with switches so a camera never matches
    against embeddings from a different model while the watchlist is being
    re-indexed.
    """

    def __init__(self, settings: Any, database: "Database"):
        self.settings = settings
        self.database = database
        self._lock = threading.RLock()
        self._switch_lock = threading.RLock()
        self._switching = False
        stored = None
        getter = getattr(database, "get_setting", None)
        if callable(getter):
            stored = getter(ENGINE_SETTING_KEY)
        if stored not in _PROFILES_BY_ID:
            stored = default_engine_id(settings)
        self._active_id = stored
        self._engine = self._build_engine(stored)

    def _build_engine(self, engine_id: str) -> FaceEngine:
        profile = get_engine_profile(engine_id)
        return FaceEngine(
            mode="mock" if profile.id == "mock" else "auto",
            model_name=profile.model or getattr(self.settings, "insightface_model", "buffalo_l"),
            det_size=getattr(self.settings, "det_size", 640),
            min_face_score=getattr(self.settings, "min_face_score", 0.5),
        )

    @property
    def requested_mode(self) -> str:
        with self._lock:
            return self._engine.requested_mode

    @property
    def active_id(self) -> str:
        with self._lock:
            return self._active_id

    @property
    def status(self) -> dict[str, Any]:
        with self._lock:
            status = dict(self._engine.status)
            status["active_id"] = self._active_id
            status["switching"] = self._switching
            return status

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_id = self._active_id
        return {
            "active_id": active_id,
            "status": self.status,
            "engines": [profile.public() for profile in ENGINE_PROFILES],
        }

    def warmup(self) -> None:
        with self._switch_lock:
            with self._lock:
                engine = self._engine
            engine.warmup()

    def detect(self, image_bgr: np.ndarray) -> list[FaceDetection]:
        with self._switch_lock:
            with self._lock:
                engine = self._engine
            return engine.detect(image_bgr)

    def detect_largest(self, image_bgr: np.ndarray) -> FaceDetection | None:
        with self._switch_lock:
            with self._lock:
                engine = self._engine
            return engine.detect_largest(image_bgr)

    def select(
        self,
        engine_id: str,
        reindex: Callable[[FaceEngine], dict[str, int]] | None = None,
    ) -> dict[str, Any]:
        profile = get_engine_profile(engine_id)
        with self._switch_lock:
            with self._lock:
                current_id = self._active_id
            if profile.id == current_id:
                self.warmup()
                return {
                    "active_id": current_id,
                    "changed": False,
                    "reindexed_people": 0,
                    "reindexed_photos": 0,
                    "status": self.status,
                }

            with self._lock:
                self._switching = True
            try:
                replacement = self._build_engine(profile.id)
                replacement.warmup()
                reindex_result = reindex(replacement) if reindex is not None else {}
                setter = getattr(self.database, "set_setting", None)
                if callable(setter):
                    setter(ENGINE_SETTING_KEY, profile.id)
                with self._lock:
                    self._engine = replacement
                    self._active_id = profile.id
                    self._switching = False
                logger.info("Activated face engine %s", profile.id)
                return {
                    "active_id": profile.id,
                    "changed": True,
                    "reindexed_people": int(reindex_result.get("people", 0)),
                    "reindexed_photos": int(reindex_result.get("photos", 0)),
                    "status": self.status,
                }
            except EngineSelectionError:
                raise
            except Exception as exc:
                logger.exception("Could not switch face engine to %s", profile.id)
                raise FaceEngineError(
                    f"Could not activate {profile.label}: {exc}"
                ) from exc
            finally:
                with self._lock:
                    self._switching = False
