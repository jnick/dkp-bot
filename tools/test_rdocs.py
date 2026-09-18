from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ocr.dateutil import parse_date  # noqa: E402
from app.ocr.rdocs import RdocsProvider, map_passport, _split_licence  # noqa: E402

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_split_licence() -> None:
    assert _split_licence("4510 123456") == ("4510", "123456")
    assert _split_licence("45 08 123456") == ("4508", "123456")
    assert _split_licence("4510123456") == ("4510", "123456")
    assert _split_licence("45 08 123 456") == ("4508", "123456")
    assert _split_licence("123456") == (None, None)
    assert _split_licence(None) == (None, None)
    assert _split_licence("") == (None, None)


def test_map_passport_full() -> None:
    ocr = {
        "Last_name_ru": "ИВАНОВ",
        "First_name_ru": "ИВАН",
        "Middle_name_ru": "ИВАНОВИЧ",
        "Birth_date": "12.06.1988",
        "Licence_number": "45 08 123456",
        "Issue_organization_ru": "ОВД РАЙОНА ХАМОВНИКИ ГОРОДА МОСКВЫ",
        "Issue_date": "12.06.2014",
        "Issue_organisation_code": "770-120",
    }
    out = map_passport(ocr, "seller")
    assert out["seller_fio"] == "ИВАНОВ ИВАН ИВАНОВИЧ", out
    assert out["seller_birth"] == "12.06.1988", out
    assert out["seller_pasp_series"] == "4508", out
    assert out["seller_pasp_number"] == "123456", out
    assert out["seller_pasp_issuer"] == "ОВД РАЙОНА ХАМОВНИКИ ГОРОДА МОСКВЫ", out
    assert out["seller_pasp_date"] == "12.06.2014", out
    assert out["seller_pasp_kod"] == "770120", out


def test_map_passport_iso_dates() -> None:
    ocr = {
        "Last_name_ru": "ПЕТРОВ",
        "First_name_ru": "ПЁТР",
        "Middle_name_ru": "ПЕТРОВИЧ",
        "Birth_date": "1988-06-12",
        "Licence_number": "9210 654321",
        "Issue_organization_ru": "УВД ПО Г. МОСКВЕ",
        "Issue_date": "2014-06-12T00:00:00Z",
        "Issue_organisation_code": "770001",
    }
    out = map_passport(ocr, "buyer")
    assert out["buyer_birth"] == "12.06.1988", out
    assert out["buyer_pasp_date"] == "12.06.2014", out
    assert out["buyer_pasp_kod"] == "770001", out


def test_map_passport_empty_and_partial() -> None:
    assert map_passport({}, "seller") == {}
    out = map_passport({"Last_name_ru": "СИДОРОВ", "First_name_ru": "СИДОР"}, "seller")
    assert out["seller_fio"] == "СИДОРОВ СИДОР"
    assert "seller_birth" not in out
    assert "seller_pasp_kod" not in out


def test_map_passport_bad_kod() -> None:
    ocr = {
        "Issue_organisation_code": "77-01",
        "Licence_number": "4508 123456",
        "Birth_date": "01.01.1990",
    }
    out = map_passport(ocr, "seller")
    assert "seller_pasp_kod" not in out, out


def test_parse_date_iso() -> None:
    assert parse_date("2014-06-12") == "12.06.2014"
    assert parse_date("2014-06-12T00:00:00Z") == "12.06.2014"
    assert parse_date("2014-06-12 08:30:00") == "12.06.2014"
    assert parse_date("1988-12-31") == "31.12.1988"
    assert parse_date("yyy-12-31") is None


def test_provider_rejects_wrong_doctype() -> None:
    class _FakeRdocsResult:
        doctype = "DRIVERLICENCE_2011"
        ocr = {"Last_name_ru": "ИВАНОВ"}
        quality = {"DocConf": 0.99}
        timings = {}

    p = RdocsProvider()

    class _FakeEngine:
        def process_img(self, rgb):
            return _FakeRdocsResult()

    p._engine = _FakeEngine()
    assert p.passport(TINY_PNG, "seller") is None


def test_provider_low_docconf() -> None:
    class _FakeRdocsResult:
        doctype = "INTPASSPORT_2011"
        ocr = {"Last_name_ru": "ИВАНОВ", "Licence_number": "4508 123456"}
        quality = {"DocConf": 0.2}
        timings = {}

    p = RdocsProvider()

    class _FakeEngine:
        def process_img(self, rgb):
            return _FakeRdocsResult()

    p._engine = _FakeEngine()
    assert p.passport(TINY_PNG, "seller") is None


def test_provider_good_result_maps() -> None:
    class _FakeRdocsResult:
        doctype = "INTPASSPORT_2011"
        ocr = {
            "Last_name_ru": "ИВАНОВ",
            "First_name_ru": "ИВАН",
            "Middle_name_ru": "ИВАНОВИЧ",
            "Birth_date": "12.06.1988",
            "Licence_number": "4508 123456",
            "Issue_organization_ru": "ОВД РАЙОНА ХАМОВНИКИ",
            "Issue_date": "12.06.2014",
            "Issue_organisation_code": "770-120",
        }
        quality = {"DocConf": 0.97}
        timings = {"total": 0.8}

    p = RdocsProvider()

    class _FakeEngine:
        def process_img(self, rgb):
            return _FakeRdocsResult()

    p._engine = _FakeEngine()
    out = p.passport(TINY_PNG, "seller")
    assert out["seller_fio"] == "ИВАНОВ ИВАН ИВАНОВИЧ", out
    assert out["seller_pasp_series"] == "4508", out
    assert out["seller_pasp_number"] == "123456", out


if __name__ == "__main__":
    test_split_licence()
    test_map_passport_full()
    test_map_passport_iso_dates()
    test_map_passport_empty_and_partial()
    test_map_passport_bad_kod()
    test_parse_date_iso()
    test_provider_rejects_wrong_doctype()
    test_provider_low_docconf()
    test_provider_good_result_maps()
    print("ALL OK")