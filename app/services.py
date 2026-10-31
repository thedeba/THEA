from __future__ import annotations

import time
from dataclasses import dataclass, field

from .alerts import AlertService
from .camera_manager import CameraManager
from .controls import RuntimeControls
from .db import Database
from .detections import DetectionService
from .face_engine import FaceEngineManager
from .matching import WatchlistIndex
from .settings import Settings
from .watchlist_service import WatchlistService
from .ws import ConnectionManager


@dataclass
class Services:
    settings: Settings
    database: Database
    websocket: ConnectionManager
    face_engine: FaceEngineManager
    watchlist_index: WatchlistIndex
    watchlist: WatchlistService
    alerts: AlertService
    detections: DetectionService
    cameras: CameraManager
    controls: RuntimeControls
    started_at: float = field(default_factory=time.time)


def build_services(settings: Settings) -> Services:
    settings.ensure_dirs()
    database = Database(settings.db_path)
    database.init()
    websocket = ConnectionManager()
    face_engine = FaceEngineManager(settings, database)
    watchlist_index = WatchlistIndex(database)
    watchlist = WatchlistService(settings, database, face_engine, watchlist_index)
    alerts = AlertService(settings, database, websocket)
    detections = DetectionService(settings, websocket)
    controls = RuntimeControls(match_threshold=settings.match_threshold)
    cameras = CameraManager(
        settings, face_engine, watchlist_index, alerts, controls, detections
    )
    return Services(
        settings=settings,
        database=database,
        websocket=websocket,
        face_engine=face_engine,
        watchlist_index=watchlist_index,
        watchlist=watchlist,
        alerts=alerts,
        detections=detections,
        cameras=cameras,
        controls=controls,
    )
