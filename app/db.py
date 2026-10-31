from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np

from .vectors import from_blob, similarity_matrix, to_blob


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    embedding BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_text TEXT NOT NULL UNIQUE,
    plate_image TEXT NOT NULL,
    confidence REAL,
    camera_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    embedding BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_person_photos_person ON person_photos(person_id);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    person_name TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    camera_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    snapshot_path TEXT,
    embedding BLOB,
    embedding_dim INTEGER,
    path_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_person ON alerts(person_id);
CREATE INDEX IF NOT EXISTS idx_alerts_camera ON alerts(camera_id);
CREATE INDEX IF NOT EXISTS idx_alerts_path ON alerts(path_id);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)

    # ------------------------------------------------------------------
    # Application settings
    # ------------------------------------------------------------------
    def get_setting(self, key: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, utc_now_iso()),
            )

    # ------------------------------------------------------------------
    # Watchlist people
    # ------------------------------------------------------------------
    def create_person(
        self,
        name: str,
        embedding: np.ndarray,
        photos: Sequence[tuple[str, np.ndarray]],
    ) -> int:
        now = utc_now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO persons (name, embedding, embedding_dim, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, to_blob(embedding), int(embedding.size), now, now),
            )
            person_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO person_photos (person_id, path, embedding, embedding_dim, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (person_id, path, to_blob(photo_embedding), int(photo_embedding.size), now)
                    for path, photo_embedding in photos
                ],
            )
        return person_id

    def list_persons(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            people = [dict(row) for row in connection.execute(
                "SELECT id, name, embedding_dim, created_at, updated_at FROM persons ORDER BY name COLLATE NOCASE"
            )]
            for person in people:
                person["photos"] = self._photos_for(connection, person["id"])
        return people

    def get_person(self, person_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, name, embedding_dim, created_at, updated_at FROM persons WHERE id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                return None
            person = dict(row)
            person["photos"] = self._photos_for(connection, person_id)
            return person

    def get_person_embedding(self, person_id: int) -> tuple[str, np.ndarray] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name, embedding FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
        if row is None:
            return None
        return str(row["name"]), from_blob(row["embedding"])

    def all_person_embeddings(self) -> list[tuple[int, str, np.ndarray]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, name, embedding FROM persons ORDER BY id"
            ).fetchall()
        return [
            (int(row["id"]), str(row["name"]), from_blob(row["embedding"]))
            for row in rows
        ]

    def update_person_name(self, person_id: int, name: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE persons SET name = ?, updated_at = ? WHERE id = ?",
                (name, utc_now_iso(), person_id),
            )
            return cursor.rowcount > 0

    def update_person_embedding(self, person_id: int, embedding: np.ndarray) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE persons SET embedding = ?, embedding_dim = ?, updated_at = ? WHERE id = ?",
                (to_blob(embedding), int(embedding.size), utc_now_iso(), person_id),
            )

    def replace_person_embeddings(
        self,
        updates: Sequence[
            tuple[int, np.ndarray, Sequence[tuple[int, np.ndarray]]]
        ],
    ) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            for person_id, embedding, photos in updates:
                connection.execute(
                    """
                    UPDATE persons
                    SET embedding = ?, embedding_dim = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (to_blob(embedding), int(embedding.size), now, person_id),
                )
                connection.executemany(
                    """
                    UPDATE person_photos
                    SET embedding = ?, embedding_dim = ?
                    WHERE id = ? AND person_id = ?
                    """,
                    [
                        (
                            to_blob(photo_embedding),
                            int(photo_embedding.size),
                            photo_id,
                            person_id,
                        )
                        for photo_id, photo_embedding in photos
                    ],
                )

    def add_person_photos(
        self, person_id: int, photos: Sequence[tuple[str, np.ndarray]]
    ) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO person_photos (person_id, path, embedding, embedding_dim, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (person_id, path, to_blob(embedding), int(embedding.size), now)
                    for path, embedding in photos
                ],
            )
            connection.execute(
                "UPDATE persons SET updated_at = ? WHERE id = ?", (now, person_id)
            )

    def person_photo_embeddings(self, person_id: int) -> list[np.ndarray]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT embedding FROM person_photos WHERE person_id = ? ORDER BY id",
                (person_id,),
            ).fetchall()
        return [from_blob(row["embedding"]) for row in rows]

    def get_photo(self, person_id: int, photo_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, person_id, path, created_at FROM person_photos WHERE id = ? AND person_id = ?",
                (photo_id, person_id),
            ).fetchone()
        return dict(row) if row else None

    def delete_person(self, person_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM persons WHERE id = ?", (person_id,))
            return cursor.rowcount > 0

    def count_persons(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM persons").fetchone()
        return int(row["count"])

    @staticmethod
    def _photos_for(connection: sqlite3.Connection, person_id: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT id, path, created_at FROM person_photos WHERE person_id = ? ORDER BY id",
            (person_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    def add_alert(
        self,
        *,
        person_id: int | None,
        person_name: str,
        camera_id: str,
        camera_name: str,
        confidence: float,
        snapshot_path: str,
        embedding: np.ndarray,
        path_id: str,
        created_ts: float | None = None,
    ) -> int:
        timestamp = created_ts if created_ts is not None else utc_now().timestamp()
        created_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alerts (
                    person_id, person_name, camera_id, camera_name, confidence,
                    snapshot_path, embedding, embedding_dim, path_id, created_at, created_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    person_name,
                    camera_id,
                    camera_name,
                    float(confidence),
                    snapshot_path,
                    to_blob(embedding),
                    int(embedding.size),
                    path_id,
                    created_at,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def get_alert(self, alert_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, person_id, person_name, camera_id, camera_name, confidence,
                       snapshot_path, path_id, created_at, created_ts
                FROM alerts WHERE id = ?
                """,
                (alert_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_alerts(
        self,
        *,
        person_id: int | None = None,
        person_name: str | None = None,
        camera_id: str | None = None,
        path_id: str | None = None,
        date_from_ts: float | None = None,
        date_to_ts: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[dict[str, Any]]]:
        clauses: list[str] = []
        params: list[Any] = []
        if person_id is not None:
            clauses.append("person_id = ?")
            params.append(person_id)
        if person_name:
            clauses.append("person_name LIKE ?")
            params.append(f"%{person_name}%")
        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        if path_id:
            clauses.append("path_id = ?")
            params.append(path_id)
        if date_from_ts is not None:
            clauses.append("created_ts >= ?")
            params.append(date_from_ts)
        if date_to_ts is not None:
            clauses.append("created_ts <= ?")
            params.append(date_to_ts)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS count FROM alerts {where}", params
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT id, person_id, person_name, camera_id, camera_name, confidence,
                       snapshot_path, path_id, created_at, created_ts
                FROM alerts {where}
                ORDER BY created_ts DESC
                LIMIT ? OFFSET ?
                """,
                [*params, max(1, limit), max(0, offset)],
            ).fetchall()
        return int(total_row["count"]), [dict(row) for row in rows]

    def has_recent_alert(self, person_id: int, camera_id: str, since_ts: float) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM alerts
                WHERE person_id = ? AND camera_id = ? AND created_ts >= ?
                LIMIT 1
                """,
                (person_id, camera_id, since_ts),
            ).fetchone()
        return row is not None

    def find_recent_alert_on_other_camera(
        self, person_id: int, camera_id: str, since_ts: float
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, camera_id, camera_name, path_id, created_ts
                FROM alerts
                WHERE person_id = ? AND camera_id != ? AND created_ts >= ?
                ORDER BY created_ts DESC
                LIMIT 1
                """,
                (person_id, camera_id, since_ts),
            ).fetchone()
        return dict(row) if row else None

    def search_alerts_by_embedding(
        self,
        embedding: np.ndarray,
        *,
        threshold: float,
        limit: int = 50,
        camera_id: str | None = None,
        date_from_ts: float | None = None,
        date_to_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["embedding IS NOT NULL"]
        params: list[Any] = []
        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        if date_from_ts is not None:
            clauses.append("created_ts >= ?")
            params.append(date_from_ts)
        if date_to_ts is not None:
            clauses.append("created_ts <= ?")
            params.append(date_to_ts)
        where = " AND ".join(clauses)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, person_id, person_name, camera_id, camera_name, confidence,
                       snapshot_path, path_id, created_at, created_ts, embedding
                FROM alerts
                WHERE {where}
                ORDER BY created_ts DESC
                """,
                params,
            ).fetchall()

        results: list[dict[str, Any]] = []
        if not rows:
            return results
        matrix = np.stack([from_blob(row["embedding"]) for row in rows])
        scores = similarity_matrix(embedding, matrix)
        for row, score in zip(rows, scores):
            if float(score) < threshold:
                continue
            item = dict(row)
            item.pop("embedding", None)
            item["similarity"] = float(score)
            results.append(item)
        results.sort(key=lambda item: item["similarity"], reverse=True)
        return results[: max(1, limit)]

    def list_paths(self, *, since_ts: float, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT path_id,
                       MIN(created_ts) AS start_ts,
                       MAX(created_ts) AS end_ts,
                       COUNT(*) AS event_count,
                       COUNT(DISTINCT camera_id) AS camera_count,
                       MIN(person_name) AS person_name,
                       MAX(person_id) AS person_id
                FROM alerts
                WHERE created_ts >= ?
                GROUP BY path_id
                HAVING COUNT(DISTINCT camera_id) > 1
                ORDER BY start_ts DESC
                LIMIT ?
                """,
                (since_ts, max(1, limit)),
            ).fetchall()
            results: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                camera_rows = connection.execute(
                    "SELECT camera_name FROM alerts WHERE path_id = ? ORDER BY created_ts ASC",
                    (row["path_id"],),
                ).fetchall()
                ordered_cameras: list[str] = []
                for camera_row in camera_rows:
                    name = str(camera_row["camera_name"])
                    if name not in ordered_cameras:
                        ordered_cameras.append(name)
                item["cameras"] = ",".join(ordered_cameras)
                results.append(item)
        return results

    def get_path_alerts(self, path_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, person_id, person_name, camera_id, camera_name, confidence,
                       snapshot_path, path_id, created_at, created_ts
                FROM alerts WHERE path_id = ?
                ORDER BY created_ts ASC
                """,
                (path_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_alerts(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM alerts").fetchone()
        return int(row["count"])

    def clear_alerts(self) -> tuple[int, list[str]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT snapshot_path FROM alerts WHERE snapshot_path IS NOT NULL"
            ).fetchall()
            cursor = connection.execute("DELETE FROM alerts")
            deleted = int(cursor.rowcount)
        snapshots = [str(row["snapshot_path"]) for row in rows if row["snapshot_path"]]
        return deleted, snapshots
