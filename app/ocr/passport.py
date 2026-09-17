from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.ocr.dateutil import parse_date
from app.ocr.geo import (
    Line,
    digitish,
    fold_cyr,
    norm,
    right_of,
    sorted_by_position,
)

ISSUER_LABELS = ("кемвыдан", "кем выдан")
DATE_ISSUE_LABELS = ("датавыдачи", "дата выдачи")
KOD_LABELS = ("кодподразделения", "код подразделения")

TOP_BAND_FRACTION = 0.32  # серия/номер ищем в верхней полосе разворота


def extract_passport(lines: List[Line], role: str) -> Dict[str, str]:
    """Разворот паспорта РФ -> ключи договора {role}_* ."""
    out: Dict[str, str] = {}
    ls = sorted_by_position(lines)
    h = max(max((l.h for l in ls), default=20.0), 20.0)
    H = max((l.y1 for l in ls), default=1.0)
    W = max((l.x1 for l in ls), default=1.0)

    # ---------- ФИО ----------
    parts = []
    for label in ("фамилия", "имя", "отчество"):
        lab = _find_label(ls, (label, f"{label}:"))
        if lab is None:
            continue
        value = _value_right_or_below(lab, ls, h)
        if value:
            parts.append(value.upper())
    if parts:
        out[f"{role}_fio"] = " ".join(parts)

    # ---------- дата рождения ----------
    lab = _find_label(ls, ("датарождения", "дата рождения", "дата рождения:"))
    if lab is not None:
        birth = _date_around(lab, ls, h)
        if birth:
            out[f"{role}_birth"] = birth

    # ---------- серия / номер (верхняя полоса) ----------
    series, number = _series_number(ls, W, H)
    if series:
        out[f"{role}_pasp_series"] = series
    if number:
        out[f"{role}_pasp_number"] = number

    # ---------- кем выдан / дата выдачи ----------
    issuer = _issuer_block(ls, W, H, h)
    if issuer:
        out[f"{role}_pasp_issuer"] = issuer
    issue = _issue_date(issuer, ls, H)
    if issue:
        out[f"{role}_pasp_date"] = issue

    # ---------- код подразделения ----------
    kod = _kod(ls, h)
    if kod:
        out[f"{role}_pasp_kod"] = kod

    return out


# ---------- helpers ----------


def _norm_token(text: str) -> str:
    return "".join(ch for ch in fold_cyr(norm(text)).strip(" :.-:,;") if ch.isalnum())


def _find_label(ls: List[Line], tokens) -> Optional[Line]:
    expected = {_norm_token(t) for t in tokens}
    for l in ls:
        if _norm_token(l.text) in expected:
            return l
    return None


def _value_right_or_below(lab: Line, ls: List[Line], h: float) -> Optional[str]:
    same_row = [c for c in sorted(right_of(lab, ls), key=lambda c: c.x0)]
    if same_row:
        return same_row[0].text
    below_lines = [l for l in ls if lab.y1 < l.y0 <= lab.y1 + 2.2 * h]
    if below_lines:
        first = sorted(below_lines, key=lambda l: abs(l.x0 - lab.x1))[0]
        if first.x0 > lab.x0 - h:
            return first.text
    return None


def _date_around(lab: Line, ls: List[Line], h: float) -> Optional[str]:
    value = _value_right_or_below(lab, ls, h)
    if value:
        d = parse_date(value)
        if d:
            return d
    window = [l for l in ls if lab.y1 - 2 * h < l.y0 <= lab.y1 + 5 * h]
    for l in sorted(window, key=lambda l: (l.y0, l.x0)):
        d = parse_date(l.text)
        if d:
            return d
    return None


def _series_number(ls: List[Line], W: float, H: float):
    band = [l for l in ls if l.y0 < TOP_BAND_FRACTION * H]
    if not band:
        return None, None
    series = number = None
    for l in band:
        dd = digitish(l.text)
        if len(dd) == 10:
            return dd[:4], dd[6:]
    for l in band:
        dd = digitish(l.text)
        if len(dd) == 6 and number is None:
            number = dd
        elif len(dd) == 4 and series is None:
            series = dd
    return series, number


def _issuer_block(ls: List[Line], W: float, H: float, h: float) -> Optional[str]:
    lab = _find_label(ls, ISSUER_LABELS)
    end_lab = _find_label(ls, DATE_ISSUE_LABELS)
    kod_lab = _find_label(ls, KOD_LABELS)
    y_start = lab.y0 if lab else 0.5 * H
    y_end = end_lab.y0 if end_lab else min(H, y_start + 6.5 * h)
    if end_lab is None and kod_lab is not None:
        y_end = min(y_end, kod_lab.y0)
    col_x = lab.x1 if lab else 0.35 * W

    words = []
    for l in ls:
        if l.cy <= y_start or l.cy >= y_end:
            continue
        if l.x0 < col_x - h:
            continue
        low = _norm_token(l.text)
        if not low or low in {_norm_token(t) for t in (*ISSUER_LABELS, *DATE_ISSUE_LABELS, *KOD_LABELS)}:
            continue
        if parse_date(l.text):
            continue
        words.append(l.text)
    return re.sub(r"\s+", " ", " ".join(words)).strip() or None


def _issue_date(issuer: Optional[str], ls: List[Line], H: float) -> Optional[str]:
    d = parse_date(issuer or "")
    if d:
        return d
    lab = _find_label(ls, DATE_ISSUE_LABELS)
    if lab is not None:
        window = [l for l in ls if abs(l.cy - lab.cy) <= 3 * lab.h]
        for l in sorted(window, key=lambda l: abs(l.cy - lab.cy)):
            d = parse_date(l.text)
            if d:
                return d
    half = [l for l in ls if l.cy > 0.45 * H]
    for l in sorted(half, key=lambda l: -l.cy):
        d = parse_date(l.text)
        if d:
            return d
    return None


def _kod(ls: List[Line], h: float) -> Optional[str]:
    lab = _find_label(ls, KOD_LABELS)
    if lab is not None:
        value = _value_right_or_below(lab, ls, h)
        dd = digitish(value or "")
        if len(dd) == 6:
            return dd
    for l in ls:
        m = re.search(r"\b\d{3}\s*[-–—]\s*\d{3}\b", l.text)
        if m:
            return digitish(m.group(0))
    return None