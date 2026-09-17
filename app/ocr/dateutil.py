from __future__ import annotations

import re
from typing import Optional

MONTHS = {
    "января": "01", "январь": "01", "янв": "01",
    "февраля": "02", "февраль": "02", "фев": "02",
    "марта": "03", "март": "03",
    "апреля": "04", "апрель": "04", "апр": "04",
    "мая": "05", "май": "05",
    "июня": "06", "июнь": "06",
    "июля": "07", "июль": "07",
    "августа": "08", "август": "08", "авг": "08",
    "сентября": "09", "сентябрь": "09", "сен": "09",
    "октября": "10", "октябрь": "10", "окт": "10",
    "ноября": "11", "ноябрь": "11", "ноя": "11",
    "декабря": "12", "декабрь": "12", "дек": "12",
}

_O = {"о": "0", "О": "0", "o": "0", "O": "0", "ᅳ": "0"}

NUMERIC_DATE = re.compile(
    r"(?<![\d])(\d{1,2})\s*[./\-–—]\s*(\d{1,2})\s*[./\-–—]\s*(\d{2,4})\s*г?\.?(?![\d])",
    re.IGNORECASE,
)
SPACED_DATE = re.compile(r"(?<![\d])(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})(?![\d])", re.IGNORECASE)
WORD_DATE = re.compile(
    r"(?<![\d])(\d{1,2})\s*[.\s]?\s*([а-яё]+)\s*[.\s]?\s*(\d{2,4})\s*г?\.?(?![\d])",
    re.IGNORECASE,
)

DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def parse_date(text: str) -> Optional[str]:
    """Возвращает ДД.ММ.ГГГГ из даты (цифрами, с пробелами, словами, «г.»), иначе None."""
    if not text:
        return None
    t = "".join(_O.get(ch, ch) for ch in text.strip())
    for m in (NUMERIC_DATE.search(t), SPACED_DATE.search(t), WORD_DATE.search(t)):
        if not m:
            continue
        if m.re is WORD_DATE:
            month = MONTHS.get(m.group(2).rstrip(".").lower())
            if month is None:
                continue
            res = _fmt_date(m.group(1), month, m.group(3))
        else:
            res = _fmt_date(m.group(1), m.group(2), m.group(3))
        if res:
            return res
    return None


def _fmt_date(day: str, month: str, year: str) -> Optional[str]:
    d, mo = int(day), int(month)
    if mo < 1 or mo > 12:
        return None
    if d < 1 or d > DAYS_IN_MONTH[mo - 1]:
        return None
    y = year if len(year) == 4 else ("20" + year if int(year) < 90 else "19" + year)
    return f"{d:02d}.{mo:02d}.{int(y):04d}"