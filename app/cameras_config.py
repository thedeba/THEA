from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class CameraConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CameraConfig:
    id: str
    name: str
    rtsp_url: str
    location: str
    target_fps: float
    enabled: bool
    width: int | None = None
    height: int | None = None


def load_cameras(path: Path | str, default_fps: float = 4.0) -> list[CameraConfig]:
    config_path = Path(path)
    if not config_path.is_file():
        return []
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CameraConfigError(f"Could not parse {config_path}: {exc}") from exc
    entries = raw.get("cameras", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        raise CameraConfigError("cameras.yaml must contain a 'cameras' list")

    cameras: list[CameraConfig] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CameraConfigError(f"Camera entry #{index + 1} is not a mapping")
        camera_id = str(entry.get("id", "")).strip()
        if not _ID_RE.match(camera_id):
            raise CameraConfigError(
                f"Camera entry #{index + 1} has an invalid id; use letters, numbers, '.', '_' or '-'"
            )
        if camera_id in seen:
            raise CameraConfigError(f"Duplicate camera id: {camera_id}")
        seen.add(camera_id)
        url = str(entry.get("rtsp_url") or entry.get("url") or "").strip()
        name = str(entry.get("name") or camera_id).strip()
        location = str(entry.get("location") or "").strip()
        try:
            target_fps = float(entry.get("target_fps", default_fps))
        except (TypeError, ValueError):
            target_fps = default_fps
        target_fps = max(0.5, min(30.0, target_fps))
        enabled = bool(entry.get("enabled", True))
        if enabled and not url:
            raise CameraConfigError(f"Camera '{camera_id}' is enabled but has no rtsp_url")
        width = _optional_positive_int(entry.get("width"))
        height = _optional_positive_int(entry.get("height"))
        cameras.append(
            CameraConfig(
                id=camera_id,
                name=name,
                rtsp_url=url,
                location=location,
                target_fps=target_fps,
                enabled=enabled,
                width=width,
                height=height,
            )
        )
    return cameras


def mask_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "***"
    if parts.scheme and parts.hostname:
        host = parts.hostname
        if parts.port:
            host = f"{host}:{parts.port}"
        if parts.username:
            user = parts.username
            host = f"{user}:***@{host}"
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return url


def _optional_positive_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
