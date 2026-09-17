from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional

from app.ocr.geo import Line
from app.ocr.preprocess import preprocess

log = logging.getLogger(__name__)

MODELS = Path(__file__).resolve().parent / "models"
REC_MODEL = MODELS / "cyrillic_PP-OCRv5_rec_mobile.onnx"
DET_MODEL = MODELS / "ch_PP-OCRv5_det_server.onnx"
CLS_MODEL = MODELS / "ch_PP-LCNet_x1_0_textline_ori_cls_server.onnx"


class OcrError(Exception):
    pass


class OcrProvider:
    """Обёртка над rapidocr (3.x, ONNX/CPU). Заменяема на коммерческий движок."""

    def __init__(
        self,
        rec_model_path: Optional[Path] = None,
        det_model_path: Optional[Path] = None,
        cls_model_path: Optional[Path] = None,
        min_score: float = 0.4,
    ):
        self.rec_model_path = str(rec_model_path or REC_MODEL)
        self.det_model_path = str(det_model_path or DET_MODEL)
        self.cls_model_path = str(cls_model_path or CLS_MODEL)
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
                from rapidocr import OCRVersion, RapidOCR

                self._engine = RapidOCR(
                    params={
                        "Det.model_path": self.det_model_path,
                        "Det.ocr_version": OCRVersion.PPOCRV5,
                        "Cls.model_path": self.cls_model_path,
                        "Cls.ocr_version": OCRVersion.PPOCRV5,
                        "Rec.model_path": self.rec_model_path,
                        "Rec.ocr_version": OCRVersion.PPOCRV5,
                    }
                )
            except Exception as exc:  # pragma: no cover
                raise OcrError(f"Не удалось загрузить OCR-движок: {exc}") from exc
            return self._engine

    def ocr(self, image_bytes: bytes) -> List[Line]:
        if not image_bytes:
            return []
        engine = self._get_engine()
        img = preprocess(image_bytes)
        with self._lock:
            try:
                out = engine(img)
            except Exception as exc:  # pragma: no cover
                raise OcrError(f"OCR завершился ошибкой: {exc}") from exc

        boxes = getattr(out, "boxes", None)
        txts = getattr(out, "txts", None)
        scores = getattr(out, "scores", None)
        if txts is None:
            return []
        lines: List[Line] = []
        for i, text in enumerate(txts):
            if not text:
                continue
            score = float(scores[i]) if scores is not None else 1.0
            if score < self.min_score:
                continue
            box = boxes[i]
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            lines.append(
                Line(
                    text=text,
                    x0=float(min(xs)),
                    y0=float(min(ys)),
                    x1=float(max(xs)),
                    y1=float(max(ys)),
                    score=score,
                )
            )
        return lines