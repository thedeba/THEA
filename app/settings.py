from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so the project has no runtime dotenv dependency."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for _env_file in (PROJECT_ROOT / ".env", APP_DIR / ".env"):
    _load_dotenv(_env_file)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _load_or_create_secret(data_dir: Path) -> str:
    env_secret = os.getenv("THEA_SECRET_KEY")
    if env_secret:
        return env_secret
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = data_dir / "secret.key"
    if secret_file.is_file():
        value = secret_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    secret_file.write_text(value, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = "THEA"
    admin_username: str = "admin"
    admin_password: str = "admin"
    secret_key: str = ""
    token_ttl_seconds: int = 12 * 60 * 60
    match_threshold: float = 0.45
    consecutive_frames: int = 3
    alert_cooldown_seconds: float = 60.0
    path_window_seconds: float = 120.0
    target_fps: float = 4.0
    face_engine: str = "auto"
    insightface_model: str = "buffalo_l"
    det_size: int = 640
    min_face_score: float = 0.5
    data_dir: Path = PROJECT_ROOT / "data"
    db_path: Path = PROJECT_ROOT / "data" / "thea.db"
    snapshots_dir: Path = PROJECT_ROOT / "data" / "snapshots"
    watchlist_dir: Path = PROJECT_ROOT / "data" / "watchlist"
    cameras_file: Path = PROJECT_ROOT / "config" / "cameras.yaml"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    stream_fps: float = 30.0
    max_upload_mb: int = 12
    min_watchlist_photos: int = 1
    max_watchlist_photos: int = 1
    camera_reconnect_seconds: float = 5.0
    rtsp_transport: str = "tcp"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"
    ytdlp_cookies_file: Path | None = None

    @property
    def using_default_password(self) -> bool:
        return self.admin_password == "admin"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.snapshots_dir, self.watchlist_dir):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> "Settings":
        data_dir = _resolve_path(_env_str("THEA_DATA_DIR", str(PROJECT_ROOT / "data")), PROJECT_ROOT)
        data_dir.mkdir(parents=True, exist_ok=True)
        origins = tuple(
            origin.strip()
            for origin in _env_str(
                "THEA_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        )
        cookies_file = _env_str("THEA_YTDLP_COOKIES_FILE", "").strip()
        settings = cls(
            admin_username=_env_str("THEA_ADMIN_USERNAME", "admin"),
            admin_password=_env_str("THEA_ADMIN_PASSWORD", "admin"),
            secret_key=_load_or_create_secret(data_dir),
            token_ttl_seconds=_env_int("THEA_TOKEN_TTL_SECONDS", 12 * 60 * 60),
            match_threshold=_env_float("THEA_MATCH_THRESHOLD", 0.45),
            consecutive_frames=max(1, _env_int("THEA_CONSECUTIVE_FRAMES", 3)),
            alert_cooldown_seconds=_env_float("THEA_ALERT_COOLDOWN_SECONDS", 60.0),
            path_window_seconds=_env_float("THEA_PATH_WINDOW_SECONDS", 120.0),
            target_fps=max(0.5, _env_float("THEA_TARGET_FPS", 4.0)),
            face_engine=_env_str("THEA_FACE_ENGINE", "auto").lower(),
            insightface_model=_env_str("THEA_INSIGHTFACE_MODEL", "buffalo_l"),
            det_size=max(160, _env_int("THEA_DET_SIZE", 640)),
            min_face_score=_env_float("THEA_MIN_FACE_SCORE", 0.5),
            data_dir=data_dir,
            db_path=data_dir / "thea.db",
            snapshots_dir=data_dir / "snapshots",
            watchlist_dir=data_dir / "watchlist",
            cameras_file=_resolve_path(
                _env_str("THEA_CAMERAS_FILE", str(PROJECT_ROOT / "config" / "cameras.yaml")),
                PROJECT_ROOT,
            ),
            cors_origins=origins,
            stream_fps=max(0.5, _env_float("THEA_STREAM_FPS", 30.0)),
            max_upload_mb=max(1, _env_int("THEA_MAX_UPLOAD_MB", 12)),
            min_watchlist_photos=max(1, _env_int("THEA_MIN_WATCHLIST_PHOTOS", 1)),
            max_watchlist_photos=max(1, _env_int("THEA_MAX_WATCHLIST_PHOTOS", 1)),
            camera_reconnect_seconds=max(1.0, _env_float("THEA_CAMERA_RECONNECT_SECONDS", 5.0)),
            rtsp_transport=_env_str("THEA_RTSP_TRANSPORT", "tcp"),
            frontend_dist=_resolve_path(
                _env_str("THEA_FRONTEND_DIST", str(PROJECT_ROOT / "frontend" / "dist")),
                PROJECT_ROOT,
            ),
            ytdlp_cookies_file=(
                _resolve_path(cookies_file, PROJECT_ROOT) if cookies_file else None
            ),
        )
        settings.ensure_dirs()
        return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
