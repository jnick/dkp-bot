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

VIN_CHARSET = "0123456789ABCDEFGHJKLMNPRSTUVWXYZ"

FRONT_KEYS = (
    "car_make_model",
    "car_year",
    "car_vin",
    "car_body_color",
    "car_pts_series",
    "car_pts_number",
)
BACK_KEYS = ("car_pts_date",)

VIN_RE = re.compile(r"[0-9A-HJ-NPR-Z]{17}")


def extract_pts_front(lines: List[Line]) -> Dict[str, str]:
    """Лицевая сторона ПТС -> ключи договора car_* (без даты выдачи)."""
    out: Dict[str, str] = {}
    ls = sorted_by_position(lines)
    h = max(max((l.h for l in ls), default=20.0), 20.0)
    H = max((l.y1 for l in ls), default=1.0)
    W = max((l.x1 for l in ls), default=1.0)

    # ---------- VIN ----------
    vin = _find_vin(ls)
    if vin:
        out["car_vin"] = vin

    # ---------- марка / модель ----------
    make_model = _value_by_label(ls, ("марка", "марка,модель"), h, W)
    if make_model:
        out["car_make_model"] = make_model.upper()

    # ---------- год выпуска ----------
    year = _year_by_label(ls, h)
    if year:
        out["car_year"] = year

    # ---------- цвет ----------
    color = _value_by_label(ls, ("цвет", "цветкузова"), h, W)
    if color:
        out["car_body_color"] = color[:24]

    # ---------- серия / номер ПТС (верхний левый угол) ----------
    series, number = _series_number(ls, W, H)
    if series:
        out["car_pts_series"] = series
    if number:
        out["car_pts_number"] = number

    return out


def extract_pts_back(lines: List[Line]) -> Dict[str, str]:
    """Оборотная сторона ПТС -> дата выдачи."""
    out: Dict[str, str] = {}
    d = _issue_date(lines)
    if d:
        out["car_pts_date"] = d
    return out


# ---------- helpers ----------


def _norm_token(text: str) -> str:
    n = "".join(ch for ch in fold_cyr(norm(text)).strip(" :.-:,;") if ch.isalnum())
    return re.sub(r"^\d+", "", n)


def _find_label(ls: List[Line], tokens) -> Optional[Line]:
    expected = {_norm_token(t) for t in tokens}
    for l in ls:
        low = _norm_token(l.text)
        if low in expected:
            return l
        for t in tokens:
            tt = _norm_token(t)
            if low and low.startswith(tt) and len(low) > len(tt):
                return l
    return None


def _value_right(lab: Line, ls: List[Line]) -> Optional[str]:
    same_row = [c for c in sorted(right_of(lab, ls), key=lambda c: c.x0)]
    if same_row:
        return same_row[0].text
    return None


def _value_below(lab: Line, ls: List[Line], h: float) -> Optional[str]:
    below_lines = [l for l in ls if lab.y1 < l.y0 <= lab.y1 + 2.2 * h]
    if not below_lines:
        return None
    first = sorted(below_lines, key=lambda l: abs(l.x0 - lab.x1))[0]
    if first.x0 > lab.x0 - h:
        return first.text
    return None


def _value_in_line(lab: Line, tokens) -> Optional[str]:
    if ":" in lab.text:
        return lab.text.split(":", 1)[1].strip(" :.,;")
    t = lab.text
    t2 = re.sub(r"^\s*[\d\s.\-—–]+\s*", "", t)
    anchor = _norm_token(tokens[0])
    idx = t2.lower().find(anchor[:12])
    if idx >= 0:
        return t2[idx + len(anchor[:12]):].lstrip(" :.,;–—").strip()
    return None


def _value_by_label(ls: List[Line], tokens, h: float, W: float) -> Optional[str]:
    lab = _find_label(ls, tokens)
    if lab is None:
        return None
    if lab.w > 0.5 * W and len(lab.text.split()) > 2:
        value = _value_in_line(lab, tokens)
        if value:
            return value
    value = _value_right(lab, ls)
    if value:
        return value
    value = _value_below(lab, ls, h)
    if value:
        return value
    return None


def _year_by_label(ls: List[Line], h: float) -> Optional[str]:
    lab = None
    for l in ls:
        if "выпуска" in _norm_token(l.text):
            lab = l
            break
    if lab is None:
        return None
    text = _value_in_line(lab, ("год выпуска",)) or _value_right(lab, ls) or _value_below(lab, ls, h) or lab.text
    m = re.search(r"\b(19|20)\d{2}\b", text)
    if m:
        return m.group(0)
    return None


def _find_vin(ls: List[Line]) -> Optional[str]:
    for l in ls:
        up = "".join("0" if ch in "оОoO" else ch for ch in l.text).upper()
        m = VIN_RE.search(re.sub(r"\s+", "", up))
        if m:
            return m.group(0)
        for tok in up.split():
            if VIN_RE.fullmatch(tok):
                return tok
    return None


def _series_number(ls: List[Line], W: float, H: float):
    corner = [l for l in ls if l.x0 < 0.45 * W and l.y0 < 0.18 * H]
    if not corner:
        return None, None
    number = series = None
    for l in corner:
        dd = digitish(l.text)
        if len(dd) == 6 and number is None:
            number = dd
        elif len(dd) == 4 and series is None:
            series = dd
        elif len(dd) == 10:
            series, number = dd[:4], dd[6:]
            return series, number
    if number:
        if series is None:
            for l in corner:
                if digitish(l.text) == number:
                    continue
                alnum = "".join(
                    "0" if ch in "оОoO" else ch for ch in l.text.upper() if ch.isalnum()
                )
                alnum = alnum.replace(number, "")
                if alnum and len(alnum) <= 4:
                    series = alnum
                    break
    return series, number


def _issue_date(ls: List[Line]) -> Optional[str]:
    for l in ls:
        low = _norm_token(l.text)
        if "выдан" in low or "выдано" in low:
            d = parse_date(l.text)
            if d:
                return d
        d = parse_date(l.text)
        if d:
            return d
    return None