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

ISSUER_LABELS = ("кем выдан", "кемвыдан")
DATE_ISSUE_LABELS = ("дата выдачи", "датавыдачи")
KOD_LABELS = ("код подразделения", "кодподразделения")

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
    for label, tokens in (("фамилия", ("фамилия", "фамилия:")),
                          ("имя", ("имя", "имя:")),
                          ("отчество", ("отчество", "отчество:"))):
        lab = _find_label(ls, tokens)
        if lab is None:
            continue
        value = _value_right_or_below(lab, tokens, ls, h)
        if value:
            parts.append(value.upper())
    if parts:
        out[f"{role}_fio"] = " ".join(parts)

    # ---------- дата рождения ----------
    birth_tokens = ("дата рождения", "дата рождения:", "датарождения")
    lab = _find_label(ls, birth_tokens)
    if lab is not None:
        birth = _date_around(lab, birth_tokens, ls, h)
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


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _find_label(ls: List[Line], tokens) -> Optional[Line]:
    expected = [_norm_token(t) for t in tokens]
    exact = set(expected)
    for l in ls:
        if _norm_token(l.text) in exact:
            return l
    # «подпись: значение» в одном боксе (в т.ч. короткие подписи типа «имя»)
    cores = [t.rstrip(":.") for t in tokens if t.rstrip(":.")]
    if cores:
        rxs = [re.compile(r"(?<![а-яё])" + re.escape(c) + r"(?=(?:[\s:,.]|$))") for c in cores]
        for l in ls:
            low = fold_cyr(l.text).lower()
            if any(rx.search(low) for rx in rxs):
                return l
    # префиксное совпадение: подпись стоит в начале строки, далее значение
    for l in ls:
        tok = _norm_token(l.text)
        if not tok:
            continue
        for e in expected:
            if len(e) >= 4 and len(tok) >= len(e) and tok.startswith(e[: min(5, len(e))]):
                return l
    # нечёткое совпадение (1 ошибка OCR)
    for l in ls:
        tok = _norm_token(l.text)
        if not tok:
            continue
        for e in expected:
            if abs(len(tok) - len(e)) <= 1 and _lev(tok, e) <= 1:
                return l
    return None


def _value_in_line(lab: Line, tokens) -> Optional[str]:
    """Подпись и значение в одном боксе: «Дата выдачи: 12.06.2014»."""
    text = lab.text
    low = fold_cyr(text).lower()
    for tok in tokens:
        core = tok.rstrip(":.").strip()
        if not core:
            continue
        rx = re.compile(r"\s*".join(re.escape(w) for w in core.split()))
        m = rx.search(low)
        if not m:
            continue
        tail = text[m.end():].strip(" :.,;–—-|")
        if tail:
            return tail
    return None


def _value_right_or_below(lab: Line, tokens, ls: List[Line], h: float) -> Optional[str]:
    in_line = _value_in_line(lab, tokens)
    if in_line:
        return in_line
    same_row = [c for c in sorted(right_of(lab, ls), key=lambda c: c.x0)]
    if same_row:
        return same_row[0].text
    below_lines = [l for l in ls if lab.y1 < l.y0 <= lab.y1 + 2.2 * h]
    if below_lines:
        first = sorted(below_lines, key=lambda l: abs(l.x0 - lab.x1))[0]
        if first.x0 > lab.x0 - h:
            return first.text
    return None


def _date_around(lab: Line, tokens, ls: List[Line], h: float) -> Optional[str]:
    value = _value_right_or_below(lab, tokens, ls, h)
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


def _cluster_rows(ls: List[Line]) -> List[List[Line]]:
    ordered = sorted(ls, key=lambda l: (l.y0, l.x0))
    rows: List[List[Line]] = []
    for l in ordered:
        if rows and abs(l.y0 - rows[-1][-1].y0) <= 0.8 * l.h:
            rows[-1].append(l)
        else:
            rows.append([l])
    return rows


def _series_number(ls: List[Line], W: float, H: float):
    band = [l for l in ls if l.y0 < TOP_BAND_FRACTION * H]
    if not band:
        return None, None
    # всё в одном боксе: «4508 123456», «45 08 № 123456»
    for l in band:
        dd = digitish(l.text)
        if len(dd) >= 10:
            return dd[:4], dd[4:10]
    # сборка по строкам верхней полосы (цифры из соседних боксов)
    joined = ""
    for row in _cluster_rows(band):
        for l in sorted(row, key=lambda l: l.x0):
            joined += l.text
    dd = re.sub(r"\D", "", joined)
    if len(dd) >= 10:
        return dd[:4], dd[4:10]
    # пара отдельных боксов: 4 цифры (серия) и 6 цифр (номер)
    four = [l for l in band if len(digitish(l.text)) == 4]
    six = [l for l in band if len(digitish(l.text)) == 6]
    if four and six:
        return digitish(sorted(four, key=lambda l: l.y0)[0].text), digitish(sorted(six, key=lambda l: l.y0)[0].text)
    return None, None


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
    in_line = _value_in_line(lab, ISSUER_LABELS) if lab else None
    if in_line:
        words.append(in_line)
    skip = {_norm_token(t) for t in (*ISSUER_LABELS, *DATE_ISSUE_LABELS, *KOD_LABELS)}
    for l in ls:
        if l.cy <= y_start or l.cy >= y_end:
            continue
        if l.x0 < col_x - h:
            continue
        low = _norm_token(l.text)
        if not low or low in skip:
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
        in_line = _value_in_line(lab, KOD_LABELS)
        if in_line:
            dd = digitish(in_line)
            if len(dd) == 6:
                return dd
        row = [l for l in ls if abs(l.cy - lab.cy) <= 0.8 * lab.h and l.x0 > lab.x1 - 0.5 * lab.h]
        row.sort(key=lambda l: l.x0)
        dd = re.sub(r"\D", "", "".join(l.text for l in row))
        if len(dd) == 6:
            return dd
    for l in ls:
        m = re.search(r"\b(\d{3})\s*[-–—]\s*(\d{3})\b", l.text)
        if m:
            return m.group(1) + m.group(2)
    for l in ls:
        m = re.search(r"(?<![\d])(\d{3})\s+(\d{3})(?![\d])", l.text)
        if m:
            return m.group(1) + m.group(2)
    return None