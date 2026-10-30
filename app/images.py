from __future__ import annotations

import cv2
import numpy as np


class ImageError(ValueError):
    pass


def decode_image(data: bytes) -> np.ndarray:
    if not data:
        raise ImageError("Empty image upload")
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ImageError("Unsupported or corrupt image file")
    return image


def resample_image(image: np.ndarray, max_dim: int = 1280) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_dim:
        return image
    scale = max_dim / float(longest)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def encode_jpeg(image: np.ndarray, quality: int = 90) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ImageError("Could not encode image")
    return encoded.tobytes()
