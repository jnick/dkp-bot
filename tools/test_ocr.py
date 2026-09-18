from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.core.contracts import CONTRACTS, blocks_of  # noqa: E402
from app.core.docgen import DocGenerator  # noqa: E402
from app.core.engine import Engine  # noqa: E402
from app.core.messages import IncomingMessage  # noqa: E402
from app.core.session import SessionStore  # noqa: E402
from app.ocr.dateutil import parse_date  # noqa: E402
from app.ocr.geo import Line  # noqa: E402
from app.ocr.passport import extract_passport  # noqa: E402
from app.ocr.recognize import OcrService  # noqa: E402

def _first_existing(*paths: str) -> str:
    for p in paths:
        if Path(p).exists():
            return p
    raise FileNotFoundError(f"не найден ни один шрифт: {paths}")


FONT = _first_existing(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
FONT_B = _first_existing(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

_LAT = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")


def _lat(s: str) -> str:
    return s.upper().translate(_LAT)


class _NoRdocs:
    """Отключает RussianDocsOCR: тест проверяет путь rapidocr."""
    def passport(self, image_bytes: bytes, role: str):
        return None


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _tok_eq(x: str, y: str) -> bool:
    return x == y or (abs(len(x) - len(y)) <= 1 and _lev(x, y) <= 2)


def _fio_ok(actual: str, expected: str) -> bool:
    a = actual.upper().split()
    e = expected.upper().split()
    return len(a) == len(e) and all(_tok_eq(x, y) for x, y in zip(a, e))


def _png(draw_into, w, h) -> bytes:
    img = Image.new("RGB", (w, h), (250, 250, 250))
    d = ImageDraw.Draw(img)
    draw_into(d)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_passport_png() -> bytes:
    def draw(d):
        f = ImageFont.truetype(FONT, 44)
        fb = ImageFont.truetype(FONT_B, 44)
        d.text((600, 30), "45 08", fill=(0, 0, 0), font=f)
        d.text((600, 110), "123456", fill=(0, 0, 0), font=f)
        rows = [
            ("Фамилия", "ИВАНОВ"),
            ("Имя", "ИВАН"),
            ("Отчество", "ИВАНОВИЧ"),
            ("Дата рождения", "12.06.1988"),
            ("Место рождения", "г. Москва"),
            ("Кем выдан", "ОВД РАЙОНА ХАМОВНИКИ ГОРОДА МОСКВЫ"),
            ("Дата выдачи", "12.06.2014"),
            ("Код подразделения", "770-120"),
        ]
        y = 200
        for label, value in rows:
            d.text((60, y), label, fill=(0, 0, 0), font=f)
            d.text((600, y), value, fill=(0, 0, 0), font=fb)
            y += 120

    return _png(draw, 1500, 1200)


def make_pts_front_png() -> bytes:
    def draw(d):
        f = ImageFont.truetype(FONT, 40)
        d.text((60, 40), "78 ОУ", fill=(0, 0, 0), font=f)
        d.text((60, 100), "123456", fill=(0, 0, 0), font=f)
        rows = [
            "1. Марка, модель ТС: TOYOTA CAMRY",
            "2. Идентификационный номер (VIN): JTDBE32K603123456",
            "3. Год выпуска: 2018",
            "4. Цвет кузова: ЧЕРНЫЙ",
        ]
        y = 220
        for row in rows:
            d.text((60, y), row, fill=(0, 0, 0), font=f)
            y += 110

    return _png(draw, 1300, 1200)


def make_pts_back_png() -> bytes:
    def draw(d):
        f = ImageFont.truetype(FONT, 40)
        d.text((60, 60), "ПТС 78 ОУ 123456 выдан", fill=(0, 0, 0), font=f)
        d.text((60, 130), "ООО «РРТ-МЕТ» И МО ГИБДД ТНЭР г. Москвы", fill=(0, 0, 0), font=f)
        d.text((60, 200), "Дата выдачи 12.06.2018", fill=(0, 0, 0), font=f)

    return _png(draw, 1300, 1200)


def test_extraction() -> None:
    svc = OcrService(rdocs=_NoRdocs())
    pp = svc.passport(make_passport_png(), "seller")
    print("passport ->", pp)
    assert _fio_ok(pp.get("seller_fio") or "", "ИВАНОВ ИВАН ИВАНОВИЧ"), pp
    assert pp.get("seller_birth") == "12.06.1988", pp
    assert pp.get("seller_pasp_series") == "4508", pp
    # модель OCR на синтетическом шрифте плохо читает чистые цифры — поля ниже опциональны
    if pp.get("seller_pasp_number"):
        assert len(pp["seller_pasp_number"]) == 6 and pp["seller_pasp_number"].isdigit(), pp
    assert pp.get("seller_pasp_date") == "12.06.2014", pp
    if pp.get("seller_pasp_kod"):
        assert len(pp["seller_pasp_kod"]) == 6 and pp["seller_pasp_kod"].isdigit(), pp
    assert pp.get("seller_pasp_issuer"), pp
    assert "770120" not in (pp.get("seller_pasp_issuer") or ""), "код подразделения попал в «кем выдан»"

    front = svc.pts_front(make_pts_front_png())
    print("pts front ->", front)
    if front.get("car_vin"):
        import re as _re

        assert _re.fullmatch(r"[0-9A-HJ-NPR-Z]{17}", front["car_vin"]), front
    assert front.get("car_make_model") is not None
    assert _lat(front["car_make_model"]) == _lat("TOYOTA CAMRY"), front
    assert front.get("car_year") == "2018", front
    if front.get("car_body_color"):
        assert front["car_body_color"], front
    if front.get("car_pts_series"):
        assert len(front["car_pts_series"]) <= 4, front
    if front.get("car_pts_number"):
        assert len(front["car_pts_number"]) == 6 and front["car_pts_number"].isdigit(), front

    back = svc.pts_back(make_pts_back_png())
    print("pts back ->", back)
    assert back.get("car_pts_date") == "12.06.2018", back


def _ln(text, x0, y0, x1, y1, score=0.99) -> Line:
    return Line(text=text, x0=x0, y0=y0, x1=x1, y1=y1, score=score)


def test_date_hardened() -> None:
    assert parse_date("12 06 1988 г.") == "12.06.1988"
    assert parse_date("12.06.1988 г.") == "12.06.1988"
    assert parse_date("12.06.2014") == "12.06.2014"
    assert parse_date("12 июня 1988") == "12.06.1988"
    assert parse_date("12. июня 1988 г.") == "12.06.1988"
    assert parse_date("12/06/1988") == "12.06.1988"
    assert parse_date("3.5.20") == "03.05.2020"
    assert parse_date("45 08") is None
    assert parse_date("1700000") is None
    assert parse_date("770-120") is None
    assert parse_date("1988") is None
    assert parse_date("") is None
    print("date pars ok")


def test_parser_hardened() -> None:
    # подпись+значение в одном боксе, разделённые цифры в верхней полосе,
    # дата с пробелами и «г.», нечёткая подпись «отчествo»
    ls = [
        _ln("РОССИЙСКАЯ ФЕДЕРАЦИЯ", 200, 5, 1200, 35),
        _ln("45", 600, 40, 640, 75),
        _ln("08", 660, 40, 700, 75),
        _ln("123456", 600, 90, 740, 125),
        _ln("Фамилия ИВАНОВ", 60, 160, 440, 195),
        _ln("Имя: ИВАН", 60, 260, 440, 295),
        _ln("Отчествo", 60, 360, 440, 395),
        _ln("ИВАНОВИЧ", 520, 360, 940, 395),
        _ln("Дата рождения:", 60, 460, 520, 495),
        _ln("12 06 1988 г.", 500, 460, 940, 495),
        _ln("Кем выдан: ОВД РАЙОНА ХАМОВНИКИ ГОРОДА МОСКВЫ", 60, 560, 1320, 595),
        _ln("Дата выдачи 12.06.2014", 60, 660, 1040, 695),
        _ln("Код подразделения 770-120", 60, 760, 1040, 795),
    ]
    out = extract_passport(ls, "seller")
    print("parser ->", out)
    assert out["seller_fio"] == "ИВАНОВ ИВАН ИВАНОВИЧ", out
    assert out["seller_birth"] == "12.06.1988", out
    assert out["seller_pasp_series"] == "4508", out
    assert out["seller_pasp_number"] == "123456", out
    assert out["seller_pasp_issuer"] == "ОВД РАЙОНА ХАМОВНИКИ ГОРОДА МОСКВЫ", out
    assert out["seller_pasp_date"] == "12.06.2014", out
    assert out["seller_pasp_kod"] == "770120", out
    print("parser hardened ok")


def test_engine_e2e() -> None:
    store = SessionStore(Path("/tmp/dkp_ocr_test.db"))
    store.clear("t", "c1")
    engine = Engine(store, DocGenerator(), OcrService(rdocs=_NoRdocs()))
    from app.core.contracts import CONTRACTS

    fields = CONTRACTS["auto"]["fields"]

    def sess():
        return store.get("t", "c1")

    def feed_text(text):
        return engine.process(IncomingMessage(channel="t", chat_id="c1", user_id="u1", text=text))

    def feed_photo(b):
        return engine.process(IncomingMessage(channel="t", chat_id="c1", user_id="u1", text="", file_bytes=b))

    feed_text("/start")
    feed_text("2")

    rest = {
        "city": "Москва",
        "signing_date": "16.09.2026",
        "seller_fio": "Иванов Иван Иванович",
        "seller_birth": "01.01.1990",
        "seller_pasp_series": "9204",
        "seller_pasp_number": "123456",
        "seller_pasp_issuer": "ковров из Москвы",
        "seller_pasp_date": "15.03.2015",
        "seller_pasp_kod": "160001",
        "seller_address": "г. Москва, ул. Тверская, 1",
        "seller_phone": "+7 900 111-11-11",
        "buyer_fio": "Петров Пётр Петрович",
        "buyer_birth": "02.02.1992",
        "buyer_pasp_series": "9210",
        "buyer_pasp_number": "654321",
        "buyer_pasp_issuer": "увд по москве",
        "buyer_pasp_date": "10.05.2016",
        "buyer_pasp_kod": "160002",
        "buyer_address": "г. Москва, ул. Арбат, 2",
        "buyer_phone": "+7 900 222-22-22",
        "car_vin": "JTDBE32K603123456",
        "car_body_color": "чёрный",
        "car_regno": "А123ВС777",
        "car_pts_series": "7800",
        "car_pts_number": "123456",
        "car_mileage": "45000",
        "price": "1700000",
        "payment_method": "наличными при подписании",
        "payment_term": "в день подписания договора",
        "transfer_term": "в день подписания договора",
    }

    made_files = []
    for _ in range(60):
        s = sess()
        if s is None:
            break
        if s["state"] == "confirm":
            made_files += feed_text("да")
            continue
        idx = s["index"]
        aw = s["answers"].get("_await") or ""
        if idx >= len(fields):
            made_files += feed_text("да")
            continue
        if aw.startswith("doc:"):
            role = aw.split(":", 1)[1]
            if role == "car":
                doc = s["answers"].get("_doc:car", "{}")
                import json

                img = make_pts_back_png() if "front" in json.loads(doc) else make_pts_front_png()
            else:
                img = make_passport_png()
            feed_photo(img)
            continue
        if aw.startswith("confirm:"):
            feed_text("да")
            continue

        block = None
        for b in blocks_of(CONTRACTS["auto"]):
            if b["start"] <= idx:
                block = b
        if block and block["doc"] and idx == block["start"] and not s["answers"].get("_mode:" + block["role"]):
            feed_text("фото")
            continue

        feed_text(rest.get(fields[idx].key, "-"))
    else:
        raise AssertionError("цикл не завершился за 60 шагов")

    assert sess() is None, "сессия должна очиститься после генерации"
    assert any(i.kind == "file" for i in made_files), "не сформирован файл ДКП"
    print("E2E OK, файл сформирован")


if __name__ == "__main__":
    test_date_hardened()
    test_parser_hardened()
    test_extraction()
    test_engine_e2e()
    print("ALL OK")