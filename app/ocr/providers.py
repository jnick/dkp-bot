from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional

from app.ocr.geo import Line

log = logging.getLogger(__name__)

DEFAULT_REC_MODEL = Path(__file__).resolve().parent / "models" / "cyrillic_PP-OCRv3_rec_mobile.onnx"


class OcrError(Exception):
    pass


class OcrProvider:
    """Тонкая обёртка над RapidOCR (ONNX, CPU). Заменяема на коммерческий движок."""

    def __init__(self, rec_model_path: Optional[Path] = None, min_score: float = 0.45):
        self.rec_model_path = str(rec_model_path or DEFAULT_REC_MODEL)
        self.min_score = min_score
        self._engine = None
        self._lock = threading.Lock()

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        with self._lock:
            if self._engine is not None:
                return self._engine
            try:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR(rec_model_path=self.rec_model_path)
            except Exception as exc:  # pragma: no cover
                raise OcrError(f"Не удалось загрузить OCR-движок: {exc}") from exc
            return self._engine

    def ocr(self, image_bytes: bytes) -> List[Line]:
        if not image_bytes:
            return []
        engine = self._get_engine()
        try:
            result, _ = engine(image_bytes)
        except Exception as exc:  # pragma: no cover
            raise OcrError(f"OCR завершился ошибкой: {exc}") from exc
        lines: List[Line] = []
        for box, text, score in result or []:
            if not text or score < self.min_score:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(Line(text=text, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), score=score))
        return lines