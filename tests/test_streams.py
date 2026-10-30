from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from app import streams


def test_is_youtube_url_accepts_watch_and_embed_links():
    assert streams.is_youtube_url("https://www.youtube.com/watch?v=ghB-3979WwM")
    assert streams.is_youtube_url("https://www.youtube.com/embed/ghB-3979WwM")
    assert streams.is_youtube_url("https://youtu.be/ghB-3979WwM")
    assert not streams.is_youtube_url("rtsp://camera.local/stream")
    assert not streams.is_youtube_url(1)


def test_normalize_source_keeps_urls_and_converts_indices():
    assert streams.normalize_source(" 1 ") == 1
    assert streams.normalize_source("rtsp://camera.local/stream") == "rtsp://camera.local/stream"


def test_resolve_stream_url_returns_first_http_url(monkeypatch):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])
    monkeypatch.setattr(
        streams.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="\nhttps://manifest.googlevideo.com/live.m3u8\n",
            stderr="",
        ),
    )
    url = streams.resolve_stream_url("https://www.youtube.com/watch?v=ghB-3979WwM")
    assert url == "https://manifest.googlevideo.com/live.m3u8"


def test_resolve_stream_url_reports_yt_dlp_failure(monkeypatch):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])
    monkeypatch.setattr(
        streams.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: Video unavailable",
        ),
    )
    with pytest.raises(streams.StreamResolveError, match="Video unavailable"):
        streams.resolve_stream_url("https://www.youtube.com/watch?v=ghB-3979WwM")


def test_resolve_stream_url_adds_cookie_hint_for_bot_check(monkeypatch):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])
    monkeypatch.setattr(
        streams.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: Sign in to confirm you are not a bot",
        ),
    )
    with pytest.raises(streams.StreamResolveError, match="THEA_YTDLP_COOKIES_FILE"):
        streams.resolve_stream_url("https://www.youtube.com/watch?v=ghB-3979WwM")


def test_resolve_stream_url_reports_rejected_cookie_file(monkeypatch, tmp_path):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])
    cookies = tmp_path / "youtube-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setattr(
        streams.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: Sign in to confirm you are not a bot",
        ),
    )
    with pytest.raises(streams.StreamResolveError, match="rejected or have expired"):
        streams.resolve_stream_url(
            "https://www.youtube.com/watch?v=ghB-3979WwM", cookies_file=cookies
        )


def test_resolve_stream_url_times_out(monkeypatch):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1)

    monkeypatch.setattr(streams.subprocess, "run", timeout)
    with pytest.raises(streams.StreamResolveError, match="Timed out"):
        streams.resolve_stream_url("https://www.youtube.com/watch?v=ghB-3979WwM")


def test_resolve_stream_url_passes_cookie_file(monkeypatch, tmp_path):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])
    cookies = tmp_path / "youtube-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout="https://manifest.googlevideo.com/live.m3u8\n",
            stderr="",
        )

    monkeypatch.setattr(streams.subprocess, "run", run)
    streams.resolve_stream_url(
        "https://www.youtube.com/watch?v=ghB-3979WwM", cookies_file=cookies
    )
    command = captured["command"]
    assert command[command.index("--cookies") + 1] == str(cookies)
    assert command[-2:] == ["-g", "https://www.youtube.com/watch?v=ghB-3979WwM"]


def test_resolve_stream_url_rejects_missing_cookie_file(monkeypatch, tmp_path):
    monkeypatch.setattr(streams, "_ytdlp_command", lambda: ["yt-dlp"])
    with pytest.raises(streams.StreamResolveError, match="cookies file not found"):
        streams.resolve_stream_url(
            "https://www.youtube.com/watch?v=ghB-3979WwM",
            cookies_file=tmp_path / "missing.txt",
        )
