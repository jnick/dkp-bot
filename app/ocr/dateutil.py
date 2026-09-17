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

NUMERIC_DATE = re.compile(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})")
WORD_DATE = re.compile(r"(\d{1,2})\s*[.\s]?\s*([а-яё]+)\s*[.\s]?\s*(\d{2,4})", re.IGNORECASE)


def parse_date(text: str) -> Optional[str]:
    """Возвращает ДД.ММ.ГГГГ из даты цифрами или словами, либо None."""
    if not text:
        return None
    t = "".join({"о": "0", "О": "0", "o": "0", "O": "0"}.get(ch, ch) for ch in text.strip())
    m = NUMERIC_DATE.search(t)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return _fmt_date(d, mo, y)
    m = WORD_DATE.search(t)
    if m:
        d, mo_word, y = m.group(1), m.group(2).lower(), m.group(3)
        month = MONTHS.get(mo_word.rstrip("."))
        if month is None:
            return None
        return _fmt_date(d, month, y)
    return None


def _fmt_date(day: str, month: str, year: str) -> str:
    y = year if len(year) == 4 else ("20" + year if int(year) < 90 else "19" + year)
    return f"{int(day):02d}.{int(month):02d}.{int(y):04d}"