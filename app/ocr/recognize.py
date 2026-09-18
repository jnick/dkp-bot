from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from app.ocr.geo import Line
from app.ocr.passport import extract_passport
from app.ocr.providers import OcrProvider
from app.ocr.pts import extract_pts_back, extract_pts_front
from app.ocr.rdocs import RdocsError, RdocsProvider

log = logging.getLogger(__name__)


class OcrService:
    """Точка входа OCR: фото -> поля договора."""

    def __init__(self, provider: OcrProvider = None, rdocs: Optional[RdocsProvider] = None):
        self.provider = provider or OcrProvider()
        self.rdocs = rdocs if rdocs is not None else RdocsProvider()

    def lines(self, image_bytes: bytes) -> List[Line]:
        return self.provider.ocr(image_bytes)

    def passport(self, image_bytes: bytes, role: str) -> Dict[str, str]:
        if self.rdocs is not None:
            t0 = time.perf_counter()
            try:
                data = self.rdocs.passport(image_bytes, role)
            except RdocsError as exc:
                log.warning("rdocs: %s; фолбэк на rapidocr", exc)
                data = None
            if data:
                log.info("rdocs распознал паспорт %s за %.2fs", role, time.perf_counter() - t0)
                return data
        return extract_passport(self.lines(image_bytes), role)

    def pts_front(self, image_bytes: bytes) -> Dict[str, str]:
        return extract_pts_front(self.lines(image_bytes))

    def pts_back(self, image_bytes: bytes) -> Dict[str, str]:
        return extract_pts_back(self.lines(image_bytes))