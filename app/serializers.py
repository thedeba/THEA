from __future__ import annotations

from typing import Any


def person_to_out(person: dict[str, Any]) -> dict[str, Any]:
    photos = [
        {
            "id": photo["id"],
            "url": f"/api/watchlist/{person['id']}/photos/{photo['id']}",
            "created_at": photo["created_at"],
        }
        for photo in person.get("photos", [])
    ]
    return {
        "id": person["id"],
        "name": person["name"],
        "photo_count": len(photos),
        "thumbnail_url": photos[0]["url"] if photos else None,
        "photos": photos,
        "created_at": person["created_at"],
        "updated_at": person["updated_at"],
    }


def alert_to_out(alert: dict[str, Any]) -> dict[str, Any]:
    confidence = float(alert["confidence"])
    return {
        "id": alert["id"],
        "person_id": alert.get("person_id"),
        "person_name": alert["person_name"],
        "camera_id": alert["camera_id"],
        "camera_name": alert["camera_name"],
        "confidence": round(confidence, 4),
        "confidence_percent": round(confidence * 100, 1),
        "snapshot_url": (
            f"/api/alerts/{alert['id']}/snapshot" if alert.get("snapshot_path") else None
        ),
        "path_id": alert["path_id"],
        "created_at": alert["created_at"],
        "created_ts": alert["created_ts"],
    }


def path_to_out(row: dict[str, Any]) -> dict[str, Any]:
    cameras = [item for item in str(row.get("cameras") or "").split(",") if item]
    return {
        "path_id": row["path_id"],
        "person_id": row.get("person_id"),
        "person_name": row.get("person_name"),
        "start_ts": row["start_ts"],
        "end_ts": row["end_ts"],
        "event_count": row["event_count"],
        "camera_count": row["camera_count"],
        "cameras": cameras,
    }
