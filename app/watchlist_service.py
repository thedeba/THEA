from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .db import Database
from .face_engine import FaceEngine, FaceEngineError, FaceEngineManager
from .images import ImageError, decode_image, encode_jpeg, resample_image
from .matching import WatchlistIndex
from .settings import Settings
from .vectors import average_embeddings

logger = logging.getLogger(__name__)


class WatchlistError(ValueError):
    pass


class WatchlistService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        face_engine: FaceEngine | FaceEngineManager,
        index: WatchlistIndex,
    ):
        self.settings = settings
        self.database = database
        self.face_engine = face_engine
        self.index = index

    def list_people(self) -> list[dict[str, Any]]:
        return self.database.list_persons()

    def get_person(self, person_id: int) -> dict[str, Any] | None:
        return self.database.get_person(person_id)

    def add_person(self, name: str, uploads: Iterable[tuple[str, bytes]]) -> dict[str, Any]:
        clean_name = self._validate_name(name)
        processed = self._process_uploads(
            uploads,
            minimum=self.settings.min_watchlist_photos,
            maximum=self.settings.max_watchlist_photos,
        )
        embedding = average_embeddings([item["embedding"] for item in processed])
        folder_name = uuid.uuid4().hex
        folder = self.settings.watchlist_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        try:
            photos: list[tuple[str, np.ndarray]] = []
            for index, item in enumerate(processed, start=1):
                filename = f"photo_{index:02d}.jpg"
                (folder / filename).write_bytes(item["jpeg"])
                relative = f"watchlist/{folder_name}/{filename}"
                photos.append((relative, item["embedding"]))
            person_id = self.database.create_person(clean_name, embedding, photos)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        self.index.reload()
        person = self.database.get_person(person_id)
        if person is None:
            raise WatchlistError("Person was created but could not be read back")
        return person

    def add_photos(self, person_id: int, uploads: Iterable[tuple[str, bytes]]) -> dict[str, Any]:
        person = self.database.get_person(person_id)
        if person is None:
            raise WatchlistError("Watchlist person not found")
        processed = self._process_uploads(
            uploads,
            minimum=1,
            maximum=self.settings.max_watchlist_photos,
        )
        folder_name = uuid.uuid4().hex
        folder = self.settings.watchlist_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        try:
            photos: list[tuple[str, np.ndarray]] = []
            for index, item in enumerate(processed, start=1):
                filename = f"photo_{index:02d}.jpg"
                (folder / filename).write_bytes(item["jpeg"])
                relative = f"watchlist/{folder_name}/{filename}"
                photos.append((relative, item["embedding"]))
            self.database.add_person_photos(person_id, photos)
            all_embeddings = self.database.person_photo_embeddings(person_id)
            self.database.update_person_embedding(person_id, average_embeddings(all_embeddings))
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        self.index.reload()
        updated = self.database.get_person(person_id)
        if updated is None:
            raise WatchlistError("Watchlist person not found")
        return updated

    def reindex_with_engine(self, engine: FaceEngine | FaceEngineManager) -> dict[str, int]:
        updates: list[tuple[int, np.ndarray, list[tuple[int, np.ndarray]]]] = []
        photo_count = 0
        for person in self.database.list_persons():
            person_photos: list[tuple[int, np.ndarray]] = []
            embeddings: list[np.ndarray] = []
            for photo in person["photos"]:
                path = self.resolve_media_path(photo["path"])
                if path is None or not path.is_file():
                    raise WatchlistError(
                        f"Could not re-index {person['name']}: photo file is missing"
                    )
                try:
                    image = decode_image(path.read_bytes())
                except ImageError as exc:
                    raise WatchlistError(
                        f"Could not re-index {person['name']}: {exc}"
                    ) from exc
                detection = engine.detect_largest(image)
                if detection is None:
                    raise WatchlistError(
                        f"Could not re-index {person['name']}: no face found in a saved photo"
                    )
                person_photos.append((int(photo["id"]), detection.embedding))
                embeddings.append(detection.embedding)
                photo_count += 1
            if not person_photos:
                raise WatchlistError(
                    f"Could not re-index {person['name']}: no saved photos"
                )
            updates.append(
                (
                    int(person["id"]),
                    average_embeddings(embeddings),
                    person_photos,
                )
            )

        self.database.replace_person_embeddings(updates)
        self.index.reload()
        logger.info(
            "Re-indexed %s watchlist people across %s photos",
            len(updates),
            photo_count,
        )
        return {"people": len(updates), "photos": photo_count}

    def rename(self, person_id: int, name: str) -> dict[str, Any]:
        clean_name = self._validate_name(name)
        if not self.database.update_person_name(person_id, clean_name):
            raise WatchlistError("Watchlist person not found")
        self.index.reload()
        person = self.database.get_person(person_id)
        if person is None:
            raise WatchlistError("Watchlist person not found")
        return person

    def delete(self, person_id: int) -> None:
        person = self.database.get_person(person_id)
        if person is None:
            raise WatchlistError("Watchlist person not found")
        photo_paths = [photo["path"] for photo in person["photos"]]
        self.database.delete_person(person_id)
        for relative in photo_paths:
            path = self.resolve_media_path(relative)
            if path is not None and path.is_file():
                path.unlink(missing_ok=True)
            parent = path.parent if path else None
            if parent and parent.is_dir() and parent != self.settings.watchlist_dir:
                try:
                    parent.rmdir()
                except OSError:
                    pass
        self.index.reload()

    def get_photo_path(self, person_id: int, photo_id: int) -> Path | None:
        photo = self.database.get_photo(person_id, photo_id)
        if photo is None:
            return None
        return self.resolve_media_path(photo["path"])

    def resolve_media_path(self, relative_path: str) -> Path | None:
        path = (self.settings.data_dir / relative_path).resolve()
        try:
            path.relative_to(self.settings.data_dir.resolve())
        except ValueError:
            return None
        return path

    def _process_uploads(
        self,
        uploads: Iterable[tuple[str, bytes]],
        *,
        minimum: int,
        maximum: int,
    ) -> list[dict[str, Any]]:
        files = list(uploads)
        if len(files) < minimum:
            raise WatchlistError(f"Upload at least {minimum} photos")
        if len(files) > maximum:
            raise WatchlistError(f"Upload at most {maximum} photos")
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        processed: list[dict[str, Any]] = []
        for filename, data in files:
            if len(data) > max_bytes:
                raise WatchlistError(
                    f"{filename or 'upload'} is larger than {self.settings.max_upload_mb} MB"
                )
            try:
                image = decode_image(data)
            except ImageError as exc:
                raise WatchlistError(f"{filename or 'upload'}: {exc}") from exc
            image = resample_image(image)
            try:
                detection = self.face_engine.detect_largest(image)
            except FaceEngineError as exc:
                raise WatchlistError(str(exc)) from exc
            if detection is None:
                raise WatchlistError(f"No face found in {filename or 'upload'}")
            processed.append(
                {
                    "embedding": detection.embedding,
                    "jpeg": encode_jpeg(image, quality=90),
                }
            )
        return processed

    @staticmethod
    def _validate_name(name: str) -> str:
        clean_name = (name or "").strip()
        if not clean_name:
            raise WatchlistError("Name is required")
        if len(clean_name) > 80:
            raise WatchlistError("Name must be 80 characters or fewer")
        return clean_name
