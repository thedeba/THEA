from __future__ import annotations

from pathlib import Path

from app.face_engine import _normalize_model_directory


def test_normalize_nested_model_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / ".insightface" / "models" / "antelopev2"
    nested = root / "antelopev2"
    nested.mkdir(parents=True)
    (nested / "scrfd_10g_bnkps.onnx").write_bytes(b"model")
    (nested / "glintr100.onnx").write_bytes(b"model")

    _normalize_model_directory("antelopev2")

    assert (root / "scrfd_10g_bnkps.onnx").read_bytes() == b"model"
    assert (root / "glintr100.onnx").read_bytes() == b"model"
    assert not nested.exists()


def test_normalized_model_directory_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / ".insightface" / "models" / "buffalo_l"
    root.mkdir(parents=True)
    marker = root / "det_10g.onnx"
    marker.write_bytes(b"model")

    _normalize_model_directory("buffalo_l")

    assert marker.read_bytes() == b"model"
