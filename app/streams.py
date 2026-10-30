from __future__ import annotations

import shutil
import subprocess
import sys
from urllib.parse import urlsplit

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_FORMAT = "bestvideo[height<=720][protocol^=m3u8]/bestvideo[height<=720]/bestvideo/best"


class StreamResolveError(RuntimeError):
    pass


def is_youtube_url(url: str | int) -> bool:
    if not isinstance(url, str):
        return False
    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return False
    return host in _YOUTUBE_HOSTS


def normalize_source(source: str) -> str | int:
    value = source.strip()
    return int(value) if value.isdigit() else value


def resolve_stream_url(source: str, timeout: float = 45.0) -> str:
    if not is_youtube_url(source):
        return source
    command = _ytdlp_command() + [
        "--no-warnings",
        "--no-playlist",
        "-f",
        _FORMAT,
        "-g",
        source.strip(),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise StreamResolveError(
            "yt-dlp is not installed; install it to use YouTube live cameras."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise StreamResolveError(
            "Timed out resolving the YouTube live stream."
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1] if detail else "no details returned"
        raise StreamResolveError(f"Could not resolve YouTube live stream: {message}")
    urls = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().lower().startswith(("http://", "https://"))
    ]
    if not urls:
        raise StreamResolveError("YouTube returned no playable stream URL.")
    return urls[0]


def _ytdlp_command() -> list[str]:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        pass
    else:
        return [sys.executable, "-m", "yt_dlp"]
    executable = shutil.which("yt-dlp")
    return [executable] if executable else [sys.executable, "-m", "yt_dlp"]
