from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float = 1.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return max(self.y1 - self.y0, 1e-6)

    @property
    def w(self) -> float:
        return max(self.x1 - self.x0, 1e-6)


def norm(text: str) -> str:
    """Нижний регистр без пробелов-мусора."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


CYR_FOLD = {
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н",
    "k": "к", "m": "м", "o": "о", "p": "р", "t": "т",
    "x": "х", "y": "у",
}
DIGIT_FOLD = {"о": "0", "o": "0", "О": "0", "O": "0", "ᅳ": "0"}


def fold_cyr(text: str) -> str:
    """Приводит похожие латинские буквы к кириллице (для сравнения подписей)."""
    return "".join(CYR_FOLD.get(ch, ch) for ch in (text or ""))


def digitish(text: str) -> str:
    """Цифры с учётом 0, который OCR часто читает как 'о'."""
    return re.sub(r"\D", "", "".join(DIGIT_FOLD.get(ch, ch) for ch in (text or "")))


def sorted_by_position(lines: Iterable[Line]) -> List[Line]:
    return sorted(lines, key=lambda l: (l.cy, l.cx))


def median_height(lines: List[Line]) -> float:
    if not lines:
        return 20.0
    hs = sorted(l.h for l in lines)
    return hs[len(hs) // 2]


def same_row(a: Line, b: Line, tol: float = 0.6) -> bool:
    return abs(a.cy - b.cy) <= tol * (a.h + b.h) / 2


def right_of(a: Line, lines: List[Line], tol: float = 0.6) -> List[Line]:
    """Строки на той же строке справа от a, ближайшие к a.cy."""
    cands = [l for l in lines if l.x0 > a.x1 and same_row(a, l, tol)]
    return sorted(cands, key=lambda l: abs(l.cy - a.cy))


def below(a: Line, lines: List[Line], max_rows: float = 1.0) -> List[Line]:
    """Строки сразу под a (в пределах max_rows высоты строки)."""
    top = a.y1
    bottom = a.y1 + max_rows * median_height(lines)
    return [l for l in lines if top < l.y0 <= bottom]


def find_label(lines: List[Line], tokens: Iterable[str]) -> Optional[Line]:
    """Находит строку, совпадающую с одним из ожидаемых токенов."""
    expected = {norm(t) for t in tokens}
    for l in sorted_by_position(lines):
        n = norm(l.text).strip(" :.-:,;")
        if n in expected or any(n == e for e in expected):
            return l
    return None


def value_for_label(
    lines: List[Line],
    label: str,
    *alt_labels: str,
    extend_below: bool = True,
) -> Optional[str]:
    """Значение поля по подписи: справа на той же строке или сразу под ней."""
    lab = find_label(
        lines,
        [label, *alt_labels],
    )
    if lab is None:
        return None
    for cand in right_of(lab, lines):
        return cand.text
    if extend_below:
        below_lines = below(lab, lines)
        if below_lines:
            col = sorted(below_lines, key=lambda l: abs(l.x0 - lab.x1))
            first = col[0]
            if first.x0 > lab.x0 - median_height(lines):
                return first.text
    return None


def all_texts_in_region(
    lines: List[Line],
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> List[Line]:
    return [
        l
        for l in lines
        if l.cx >= x_min and l.cx <= x_max and l.cy >= y_min and l.cy <= y_max
    ]


def region(bound: tuple) -> dict:
    x0, y0, x1, y1 = bound
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")