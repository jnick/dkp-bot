from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from num2words import num2words

Validator = Callable[[str], Optional[str]]


class Field:
    def __init__(self, key: str, prompt: str, validator: Optional[Validator] = None, example: str = "", optional: bool = False):
        self.key = key
        self.prompt = prompt
        self.validator = validator
        self.example = example
        self.optional = optional


# ---------- валидаторы ----------

def ask_text(value: str) -> Optional[str]:
    if not (value or "").strip():
        return "Поле не может быть пустым. Введите значение или отправьте «-», чтобы пропустить."
    return None


def optional_text(value: str) -> Optional[str]:
    return None


def ask_price(value: str) -> Optional[str]:
    v = (value or "").strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        price = float(v)
    except ValueError:
        return "Цена должна быть числом. Пример: 25000"
    if price < 0:
        return "Цена не может быть отрицательной."
    return None


def ask_digits(n: int, label: str) -> Validator:
    def _inner(value: str) -> Optional[str]:
        v = re.sub(r"\s+", "", value or "")
        if not v.isdigit() or len(v) != n:
            return f"{label} должно содержать {n} цифр. Пример: {'9' * n}"
        return None

    return _inner


def ask_date(value: str) -> Optional[str]:
    v = (value or "").strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", v):
        return "Дата должна быть в формате ДД.ММ.ГГГГ. Пример: 16.09.2026"
    return None


def ask_int(label: str) -> Validator:
    def _inner(value: str) -> Optional[str]:
        v = (value or "").strip().replace(" ", "")
        if not v.isdigit():
            return f"{label} должно быть целым числом. Пример: 5"
        return None

    return _inner


def money_words(amount: float) -> str:
    return num2words(float(amount), lang="ru", to="currency", currency="RUB")


# ---------- общие поля сторон ----------

def _party_fields(role: str) -> List[Field]:
    who = "продавца" if role == "seller" else "покупателя"
    return [
        Field(f"{role}_fio", f"ФИО {who} (полностью)", validator=ask_text, example="Иванов Иван Иванович"),
        Field(f"{role}_birth", f"Дата рождения {who} (ДД.ММ.ГГГГ)", validator=ask_date, example="01.01.1990"),
        Field(f"{role}_pasp_series", f"Серия паспорта {who} (4 цифры)", validator=ask_digits(4, "Серия паспорта")),
        Field(f"{role}_pasp_number", f"Номер паспорта {who} (6 цифр)", validator=ask_digits(6, "Номер паспорта")),
        Field(f"{role}_pasp_issuer", f"Кем выдан паспорт {who}", validator=ask_text),
        Field(f"{role}_pasp_date", f"Дата выдачи паспорта {who} (ДД.ММ.ГГГГ)", validator=ask_date),
        Field(f"{role}_pasp_kod", f"Код подразделения (6 цифр)", validator=ask_digits(6, "Код подразделения")),
        Field(f"{role}_address", f"Адрес регистрации {who}", validator=ask_text),
        Field(f"{role}_phone", f"Телефон {who} (по желанию, «-» чтобы пропустить)", validator=optional_text, optional=True),
    ]


META_FIELDS: List[Field] = [
    Field("city", "Место заключения договора (город)", validator=ask_text, example="Москва"),
    Field("signing_date", "Дата заключения договора (ДД.ММ.ГГГГ)", validator=ask_date, example="16.09.2026"),
]

# ---------- сборка контекста ----------

def _party_in_context(answers: Dict[str, str], role: str) -> Dict[str, str]:
    pasp = (
        f"серия {answers.get(f'{role}_pasp_series', '')} № {answers.get(f'{role}_pasp_number', '')}, "
        f"выдан {answers.get(f'{role}_pasp_issuer', '')} {answers.get(f'{role}_pasp_date', '')}, "
        f"код подразделения {answers.get(f'{role}_pasp_kod', '')}"
    )
    return {
        f"{role}_fio": answers.get(f"{role}_fio", ""),
        f"{role}_birth": answers.get(f"{role}_birth", ""),
        f"{role}_passport_line": pasp,
        f"{role}_address": answers.get(f"{role}_address", ""),
        f"{role}_phone": answers.get(f"{role}_phone", "") or "—",
    }


def _price_in_context(answers: Dict[str, str]) -> Dict[str, str]:
    raw = (answers.get("price", "0") or "0").strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        amount = 0.0
    return {
        "price_digits": f"{amount:,.2f}".replace(",", " "),
        "price_words": money_words(amount),
    }


def _common_context(answers: Dict[str, str]) -> Dict[str, str]:
    ctx: Dict[str, str] = {}
    ctx.update(_party_in_context(answers, "seller"))
    ctx.update(_party_in_context(answers, "buyer"))
    ctx.update(_price_in_context(answers))
    ctx["city"] = answers.get("city", "")
    ctx["signing_date"] = answers.get("signing_date", "")
    return ctx


# ---------- три шаблона ----------

def _build_movable(answers: Dict[str, str]) -> Dict[str, str]:
    ctx = _common_context(answers)
    ctx.update(
        {
            "item_name": answers.get("item_name", ""),
            "item_desc": answers.get("item_desc", ""),
            "payment_method": answers.get("payment_method", ""),
            "payment_term": answers.get("payment_term", ""),
            "transfer_term": answers.get("transfer_term", ""),
        }
    )
    return ctx


def _build_auto(answers: Dict[str, str]) -> Dict[str, str]:
    ctx = _common_context(answers)
    ctx.update(
        {
            "car_make_model": answers.get("car_make_model", ""),
            "car_year": answers.get("car_year", ""),
            "car_vin": answers.get("car_vin", ""),
            "car_body_color": answers.get("car_body_color", ""),
            "car_regno": answers.get("car_regno", ""),
            "car_mileage": answers.get("car_mileage", ""),
            "car_pts_series": answers.get("car_pts_series", ""),
            "car_pts_number": answers.get("car_pts_number", ""),
            "car_pts_date": answers.get("car_pts_date", ""),
            "payment_method": answers.get("payment_method", ""),
            "payment_term": answers.get("payment_term", ""),
            "transfer_term": answers.get("transfer_term", ""),
        }
    )
    return ctx


def _build_realty(answers: Dict[str, str]) -> Dict[str, str]:
    ctx = _common_context(answers)
    ctx.update(
        {
            "realty_address": answers.get("realty_address", ""),
            "realty_cadastral": answers.get("realty_cadastral", ""),
            "realty_area": answers.get("realty_area", ""),
            "realty_floor": answers.get("realty_floor", ""),
            "realty_floors": answers.get("realty_floors", ""),
            "realty_rooms": answers.get("realty_rooms", ""),
            "realty_year": answers.get("realty_year", ""),
            "realty_doc_num": answers.get("realty_doc_num", ""),
            "payment_method": answers.get("payment_method", ""),
            "payment_term": answers.get("payment_term", ""),
        }
    )
    return ctx


MOVABLE_FIELDS: List[Field] = [
    Field("item_name", "Наименование товара", validator=ask_text, example="Смартфон iPhone 15 Pro"),
    Field("item_desc", "Характеристики и состояние товара", validator=ask_text, example="128 ГБ, отличное состояние, без царапин"),
    Field("price", "Цена товара, руб. (числом)", validator=ask_price, example="95000"),
    Field("payment_method", "Способ оплаты", validator=ask_text, example="наличными при получении"),
    Field("payment_term", "Срок оплаты", validator=ask_text, example="в момент передачи товара"),
    Field("transfer_term", "Срок передачи товара", validator=ask_text, example="в течение 3 дней с момента подписания договора"),
]

AUTO_FIELDS: List[Field] = [
    Field("car_make_model", "Марка и модель автомобиля", validator=ask_text, example="Toyota Camry"),
    Field("car_year", "Год выпуска", validator=ask_digits(4, "Год выпуска")),
    Field("car_vin", "VIN-номер (17 знаков)", validator=ask_text, example="JTDBE32K603123456"),
    Field("car_body_color", "Цвет кузова", validator=ask_text, example="чёрный"),
    Field("car_regno", "Государственный регистрационный знак", validator=ask_text, example="А123ВС777"),
    Field("car_pts_series", "Серия ПТС", validator=ask_digits(4, "Серия ПТС")),
    Field("car_pts_number", "Номер ПТС", validator=ask_digits(6, "Номер ПТС")),
    Field("car_pts_date", "Дата выдачи ПТС (ДД.ММ.ГГГГ)", validator=ask_date),
    Field("car_mileage", "Пробег, км (числом)", validator=ask_int("Пробег")),
    Field("price", "Цена автомобиля, руб. (числом)", validator=ask_price, example="2500000"),
    Field("payment_method", "Способ оплаты", validator=ask_text, example="наличными при подписании"),
    Field("payment_term", "Срок оплаты", validator=ask_text, example="в день подписания договора"),
    Field("transfer_term", "Срок передачи автомобиля", validator=ask_text, example="в день подписания договора"),
]

REALTY_FIELDS: List[Field] = [
    Field("realty_address", "Адрес объекта недвижимости", validator=ask_text, example="г. Москва, ул. Примерная, д. 1, кв. 10"),
    Field("realty_cadastral", "Кадастровый номер", validator=ask_text, example="77:01:0000001:1234"),
    Field("realty_area", "Площадь объекта, кв. м", validator=ask_text, example="54.6"),
    Field("realty_rooms", "Количество комнат", validator=ask_int("Количество комнат")),
    Field("realty_floor", "Этаж", validator=ask_int("Этаж")),
    Field("realty_floors", "Этажей в доме", validator=ask_int("Этажей в доме")),
    Field("realty_year", "Год постройки", validator=ask_digits(4, "Год постройки")),
    Field("realty_doc_num", "Основание права собственности (документ, дата, № записи ЕГРН)", validator=ask_text, example="Договор купли-продажи от 01.01.2010, № записи 77-77-01/123/2010-456"),
    Field("price", "Цена объекта, руб. (числом)", validator=ask_price, example="8500000"),
    Field("payment_method", "Способ оплаты", validator=ask_text, example="банковским переводом"),
    Field("payment_term", "Срок оплаты", validator=ask_text, example="в течение 3 рабочих дней с даты регистрации перехода права"),
]

CONTRACTS: Dict[str, dict] = {
    "movables": {
        "name": "движимое имущество / товар",
        "docx": "movables",
        "fields": META_FIELDS + _party_fields("seller") + _party_fields("buyer") + MOVABLE_FIELDS,
        "menu": "1",
        "build": _build_movable,
    },
    "auto": {
        "name": "транспортное средство",
        "docx": "auto",
        "fields": META_FIELDS + _party_fields("seller") + _party_fields("buyer") + AUTO_FIELDS,
        "menu": "2",
        "build": _build_auto,
    },
    "realty": {
        "name": "недвижимость",
        "docx": "realty",
        "fields": META_FIELDS + _party_fields("seller") + _party_fields("buyer") + REALTY_FIELDS,
        "menu": "3",
        "build": _build_realty,
    },
}


def contract_label_field(field: Field) -> str:
    labels = {
        "city": "Место заключения",
        "signing_date": "Дата заключения",
        "seller_fio": "ФИО продавца",
        "buyer_fio": "ФИО покупателя",
        "price": "Цена, руб.",
        "item_name": "Товар",
        "car_make_model": "Автомобиль",
        "realty_address": "Объект",
    }
    return labels.get(field.key, field.key.replace("_", " "))


# ---------- блоки мастера и OCR-поля ----------

ROLE_PREFIX = {"seller": "seller_", "buyer": "buyer_", "car": "car_"}

PASSPORT_OCR_KEYS = (
    "fio",
    "birth",
    "pasp_series",
    "pasp_number",
    "pasp_issuer",
    "pasp_date",
    "pasp_kod",
)

PTS_OCR_KEYS = (
    "car_make_model",
    "car_year",
    "car_vin",
    "car_body_color",
    "car_pts_series",
    "car_pts_number",
    "car_pts_date",
)


def blocks_of(tpl: dict) -> List[dict]:
    """Блоки полей шаблона: {id, role, name, start, doc, ocr_keys}.

    doc: None | "passport" | "pts" — тип документа, который можно распознать с фото.
    """
    fields = tpl["fields"]
    starts: Dict[str, int] = {}
    for i, f in enumerate(fields):
        if f.key in ("city", "signing_date") and "meta" not in starts:
            starts["meta"] = i
        for role, prefix in ROLE_PREFIX.items():
            if f.key.startswith(prefix) and role not in starts:
                starts[role] = i

    blocks: List[dict] = []
    if "meta" in starts:
        blocks.append({"id": "meta", "role": "_meta", "name": "Общие данные", "start": starts["meta"], "doc": None, "ocr_keys": []})
    for role in ("seller", "buyer", "car"):
        if role not in starts:
            continue
        prefix = ROLE_PREFIX[role]
        if role == "car":
            name, doc, ocr_keys = "Данные автомобиля", "pts", list(PTS_OCR_KEYS)
        else:
            name = "Данные продавца" if role == "seller" else "Данные покупателя"
            doc = "passport"
            ocr_keys = [prefix + k for k in PASSPORT_OCR_KEYS]
        blocks.append({"id": role, "role": role, "name": name, "start": starts[role], "doc": doc, "ocr_keys": ocr_keys})
    blocks.sort(key=lambda b: b["start"])
    return blocks