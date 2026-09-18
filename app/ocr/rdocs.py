from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from app.ocr.dateutil import parse_date
from app.ocr.geo import digitish

log = logging.getLogger(__name__)

PASSPORT_DOC_BASE = ("INTPASSPORT",)


@dataclass
class RdocsResult:
    doctype: str
    ocr: Dict[str, str]
    docconf: float
    timings: dict


class RdocsError(Exception):
    pass


def _to_rgb(image_bytes: bytes):
    try:
        import numpy as np
        import PIL.Image
        import PIL.ImageOps

        img = PIL.Image.open(io.BytesIO(image_bytes))
        img = PIL.ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return np.asarray(img)
    except Exception:  # pragma: no cover
        return None


def _split_licence(value: Optional[str]):
    dd = digitish(value or "")
    if len(dd) < 10:
        return None, None
    return dd[:4], dd[4:10]


def _norm_date(value: Optional[str]) -> Optional[str]:
    return parse_date(value or "") or None


def map_passport(ocr: Dict[str, str], role: str) -> Dict[str, str]:
    """OCR-поля RussianDocsOCR (INTPASSPORT) -> ключи договора {role}_*."""
    out: Dict[str, str] = {}
    parts = [ocr.get(k) for k in ("Last_name_ru", "First_name_ru", "Middle_name_ru")]
    parts = [p.strip() for p in parts if p and p.strip()]
    if parts:
        out[f"{role}_fio"] = " ".join(parts)

    birth = _norm_date(ocr.get("Birth_date"))
    if birth:
        out[f"{role}_birth"] = birth

    series, number = _split_licence(ocr.get("Licence_number"))
    if series:
        out[f"{role}_pasp_series"] = series
    if number:
        out[f"{role}_pasp_number"] = number

    issuer = (ocr.get("Issue_organization_ru") or "").strip()
    if issuer:
        out[f"{role}_pasp_issuer"] = issuer

    issue = _norm_date(ocr.get("Issue_date"))
    if issue:
        out[f"{role}_pasp_date"] = issue

    kod = digitish(ocr.get("Issue_organisation_code") or "")
    if len(kod) == 6:
        out[f"{role}_pasp_kod"] = kod
    return out


class RdocsProvider:
    """Паспорт РФ (разворот 2–3 стр.) через RussianDocsOCR.

    Lazy-синглтон Pipeline: 12 моделей (~215 МБ) грузятся один раз на процесс.
    Русские документы не рекомендуется дергать параллельно — вызовы
    сериализуются локом (0.5–1.2 с на фото на CPU). Если библиотека не
    установлена или её импорт падает (например, python 3.9 локально) —
    available()==False и паспорт уходит в rapidocr.
    """

    def __init__(self, device: Optional[str] = None, ocr: str = "accurate", min_docconf: float = 0.5):
        self.device = device
        self.ocr = ocr
        self.min_docconf = min_docconf
        self._engine = None
        self._import_error: Optional[Exception] = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self._get_engine() is not None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        if self._import_error is not None:  # pragma: no cover
            return None
        with self._lock:
            if self._engine is not None:
                return self._engine
            try:
                from document_processing import Pipeline

                self._engine = Pipeline(device=self.device, ocr=self.ocr)
            except Exception as exc:  # pragma: no cover
                self._import_error = exc
                log.warning("RussianDocsOCR недоступен, паспорт пойдёт через rapidocr: %s", exc)
                return None
            return self._engine

    def recognize(self, image_bytes: bytes) -> Optional[RdocsResult]:
        if not image_bytes:
            return None
        engine = self._get_engine()
        if engine is None:
            return None
        rgb = _to_rgb(image_bytes)
        if rgb is None:
            raise RdocsError("Не удалось декодировать изображение")
        with self._lock:
            try:
                res = engine.process_img(rgb)
            except Exception as exc:  # pragma: no cover
                raise RdocsError(f"RussianDocsOCR завершился ошибкой: {exc}") from exc
        doctype = str(getattr(res, "doctype", None) or "NONE")
        ocr = {
            str(k): str(v)
            for k, v in (getattr(res, "ocr", None) or {}).items()
            if v is not None and str(v)
        }
        quality = getattr(res, "quality", None) or {}
        docconf = 0.0
        try:
            docconf = float(quality.get("DocConf", 0.0))
        except (TypeError, ValueError):  # pragma: no cover
            docconf = 0.0
        timings = {str(k): float(v) for k, v in (getattr(res, "timings", None) or {}).items()
                   if _is_float(v)}
        return RdocsResult(doctype=doctype, ocr=ocr, docconf=docconf, timings=timings)

    def passport(self, image_bytes: bytes, role: str) -> Optional[Dict[str, str]]:
        """Паспорт РФ -> ключи договора {role}_*; None если тип/уверенность не подтверждены."""
        res = self.recognize(image_bytes)
        if res is None:
            return None
        if not res.doctype.startswith(PASSPORT_DOC_BASE) or res.docconf < self.min_docconf:
            return None
        data = map_passport(res.ocr, role)
        return data or None


def _is_float(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False