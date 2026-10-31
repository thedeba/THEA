from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str


class UserOut(BaseModel):
    username: str


class NameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PersonPhotoOut(BaseModel):
    id: int
    url: str
    created_at: str


class PersonOut(BaseModel):
    id: int
    name: str
    photo_count: int
    thumbnail_url: str | None
    photos: list[PersonPhotoOut]
    created_at: str
    updated_at: str


class CameraOut(BaseModel):
    id: str
    name: str
    location: str
    target_fps: float
    preview_fps: float
    width: int | None = None
    height: int | None = None
    enabled: bool
    online: bool
    frames_processed: int
    faces_detected: int
    alerts_created: int
    last_frame_at: str | None
    uptime_seconds: float
    started_at: str | None = None
    last_error: str | None
    configured: bool


class AlertOut(BaseModel):
    id: int
    person_id: int | None
    person_name: str
    camera_id: str
    camera_name: str
    confidence: float
    confidence_percent: float
    snapshot_url: str | None
    path_id: str
    created_at: str
    created_ts: float


class AlertListOut(BaseModel):
    total: int
    items: list[AlertOut]
    limit: int
    offset: int


class ClearAlertsOut(BaseModel):
    deleted: int
    snapshots_removed: int


class DetectionOut(BaseModel):
    id: str
    camera_id: str
    camera_name: str
    track_id: int
    person_id: int | None
    person_name: str | None
    known: bool
    match_score: float | None
    match_percent: float | None
    detection_score: float
    bbox: list[int]
    width: int
    height: int
    thumbnail_url: str
    created_at: str
    created_ts: float


class PathOut(BaseModel):
    path_id: str
    person_id: int | None
    person_name: str | None
    start_ts: float
    end_ts: float
    event_count: int
    camera_count: int
    cameras: list[str]


class SearchFaceInfo(BaseModel):
    bbox: list[int]
    detection_score: float


class SearchResultOut(AlertOut):
    similarity: float


class SearchResponse(BaseModel):
    query_face: SearchFaceInfo | None
    threshold: float
    count: int
    results: list[SearchResultOut]


class HealthOut(BaseModel):
    status: str
    face_engine: dict
    watchlist_index: str
    watchlist_people: int
    cameras: int
    cameras_online: int
    alerts: int
    monitoring_enabled: bool = True
    match_threshold: float = 0.45
    uptime_seconds: float = 0.0
    started_at: str | None = None


class EngineProfileOut(BaseModel):
    id: str
    label: str
    description: str
    tag: str
    recommended: bool
    development: bool
    cached: bool


class FaceEnginesOut(BaseModel):
    active_id: str
    status: dict
    engines: list[EngineProfileOut]


class EngineSelectOut(BaseModel):
    active_id: str
    changed: bool
    reindexed_people: int
    reindexed_photos: int
    status: dict
    message: str


class ControlsOut(BaseModel):
    monitoring_enabled: bool
    match_threshold: float
    consecutive_frames: int
    cameras: int
    cameras_online: int
    uptime_seconds: float
    server_time: str


class ControlsUpdate(BaseModel):
    monitoring_enabled: bool | None = None
    match_threshold: float | None = Field(default=None, ge=0.1, le=0.95)
