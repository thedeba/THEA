from __future__ import annotations

import numpy as np

EMBEDDING_DIM = 512


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return vector
    return vector / norm


def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        raise ValueError("At least one embedding is required")
    stacked = np.stack([l2_normalize(embedding) for embedding in embeddings], axis=0)
    return l2_normalize(stacked.mean(axis=0))


def to_blob(embedding: np.ndarray) -> bytes:
    return np.asarray(embedding, dtype=np.float32).reshape(-1).tobytes()


def from_blob(blob: bytes | memoryview | None) -> np.ndarray:
    if not blob:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(blob, dtype=np.float32).copy()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = l2_normalize(a)
    b = l2_normalize(b)
    if a.size == 0 or a.size != b.size:
        return 0.0
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def similarity_matrix(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a query vector and a matrix of row vectors."""
    query = l2_normalize(query)
    if matrix.size == 0:
        return np.zeros(0, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms <= 1e-12] = 1.0
    return np.clip((matrix / norms) @ query, -1.0, 1.0)
