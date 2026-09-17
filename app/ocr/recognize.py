from __future__ import annotations

from typing import Dict, List

from app.ocr.geo import Line
from app.ocr.passport import extract_passport
from app.ocr.providers import OcrProvider
from app.ocr.pts import extract_pts_back, extract_pts_front


class OcrService:
    """Точка входа OCR: фото -> поля договора."""

    def __init__(self, provider: OcrProvider = None):
        self.provider = provider or OcrProvider()

    def lines(self, image_bytes: bytes) -> List[Line]:
        return self.provider.ocr(image_bytes)

    def passport(self, image_bytes: bytes, role: str) -> Dict[str, str]:
        return extract_passport(self.lines(image_bytes), role)

    def pts_front(self, image_bytes: bytes) -> Dict[str, str]:
        return extract_pts_front(self.lines(image_bytes))

    def pts_back(self, image_bytes: bytes) -> Dict[str, str]:
        return extract_pts_back(self.lines(image_bytes))