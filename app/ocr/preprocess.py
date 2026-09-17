from __future__ import annotations

import io
from typing import Optional

import cv2
import numpy as np

ASCENT_TARGET = 1600
MAX_ASCENT = 2000
MIN_ASCENT = 1200


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Подготовка кадра под OCR: EXIF-поворот, контраст (CLAHE), апскейл мелких фото."""
    bgr = _decode(image_bytes)
    if bgr is None or bgr.size == 0:
        raise ValueError("Не удалось декодировать изображение")
    bgr = _clahe(bgr)
    bgr = _upscale(bgr)
    return bgr


def _decode(image_bytes: bytes) -> Optional[np.ndarray]:
    try:
        import PIL.Image

        img = PIL.Image.open(io.BytesIO(image_bytes))
        img = PIL.ImageOps.exif_transpose(img) if hasattr(PIL, "ImageOps") else img
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        rgb = np.asarray(img)
    except Exception:
        rgb = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if rgb is None:
        return None
    if rgb.ndim == 2:
        return cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _clahe(bgr: np.ndarray, clip: float = 2.0, grid: int = 8) -> np.ndarray:
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid))
    y = clahe.apply(y)
    return cv2.cvtColor(cv2.merge((y, cr, cb)), cv2.COLOR_YCrCb2BGR)


def _upscale(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    longest = max(h, w)
    if longest < MIN_ASCENT:
        scale = ASCENT_TARGET / longest
    elif longest < ASCENT_TARGET:
        scale = ASCENT_TARGET / longest
    elif longest < MAX_ASCENT:
        return bgr
    else:
        return bgr
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    interp = cv2.INTER_LANCZOS4 if scale > 2.0 else cv2.INTER_CUBIC
    return cv2.resize(bgr, (new_w, new_h), interpolation=interp)