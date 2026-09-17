from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.docgen import DocGenerator  # noqa: E402
from app.core.engine import Engine  # noqa: E402
from app.core.messages import IncomingMessage  # noqa: E402
from app.core.session import SessionStore  # noqa: E402

ANSWERS_MOV = {
    "city": "Казань",
    "signing_date": "16.09.2026",
    "seller_fio": "Иванов Иван Иванович",
    "seller_birth": "01.01.1990",
    "seller_pasp_series": "9204",
    "seller_pasp_number": "123456",
    "seller_pasp_issuer": "Отделом УФМС России по РТ",
    "seller_pasp_date": "15.03.2015",
    "seller_pasp_kod": "160001",
    "seller_address": "г. Казань, ул. Ленина, д. 1",
    "seller_phone": "+7 900 000-00-01",
    "buyer_fio": "Петров Пётр Петрович",
    "buyer_birth": "02.02.1992",
    "buyer_pasp_series": "9210",
    "buyer_pasp_number": "654321",
    "buyer_pasp_issuer": "Отделом УФМС России по РТ",
    "buyer_pasp_date": "10.05.2016",
    "buyer_pasp_kod": "160002",
    "buyer_address": "г. Казань, ул. Гагарина, д. 2",
    "buyer_phone": "+7 900 000-00-02",
    "item_name": "Смартфон iPhone 15 Pro",
    "item_desc": "128 ГБ, отличное состояние, без царапин",
    "price": "95000",
    "payment_method": "наличными при получении",
    "payment_term": "в момент передачи товара",
    "transfer_term": "в течение 3 дней с момента подписания договора",
}


def run() -> None:
    store = SessionStore(Path("/tmp/dkp_test.db"))
    store.clear("t", "c1")
    engine = Engine(store, DocGenerator())

    def send(text):
        out = engine.process(IncomingMessage(channel="t", chat_id="c1", user_id="u1", text=text))
        for item in out:
            kind = item.kind
            text_p = item.text[:120].replace("\n", " | ")
            print(f"[{kind}] {text_p}")
        return out

    send("/start")
    send("1")

    from app.core.contracts import CONTRACTS, blocks_of

    fields = CONTRACTS["movables"]["fields"]
    made = []
    for _ in range(40):
        s = store.get("t", "c1")
        if s is None:
            break
        if s["state"] == "confirm":
            made += send("да")
            continue
        idx = s["index"]
        if idx >= len(fields):
            made += send("да")
            continue
        key = fields[idx].key
        block = None
        for b in blocks_of(CONTRACTS["movables"]):
            if b["start"] <= idx:
                block = b
        if block and block["doc"] and idx == block["start"] and not s["answers"].get("_mode:" + block["role"]):
            send("вручную")
            continue
        send(ANSWERS_MOV.get(key, "-"))
    else:
        raise AssertionError("цикл не завершился за 40 шагов")

    assert any(i.kind == "file" for i in made), "нет файла ДКП"

    last = send("/status")
    assert any("Активного договора нет" in i.text for i in last), "сессия должна была очиститься"

    print("\n--- проверка файлов ---")
    for slug in ("movables", "auto", "realty"):
        data = DocGenerator().render_docx(slug, ANSWERS_MOV)
        assert len(data) > 0
        print(slug, "docx bytes:", len(data))
    print("ALL OK")


if __name__ == "__main__":
    run()