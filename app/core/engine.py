from __future__ import annotations

import json
from typing import List, Optional

from app.core.contracts import CONTRACTS, blocks_of, contract_label_field
from app.core.docgen import DocGenerator
from app.core.messages import IncomingMessage, OutgoingItem
from app.core.session import SessionStore
from app.ocr.providers import OcrError
from app.ocr.recognize import OcrService

DISCLAIMER = "Типовой шаблон. Перед подписанием проверьте условия договора при необходимости у юриста."

MENU = (
    "Договор купли-продажи (ДКП). Выберите шаблон — пришлите номер:\n\n"
    "1 — движимое имущество / товар\n"
    "2 — транспортное средство\n"
    "3 — недвижимость\n\n"
    "Команды: /cancel — прервать и удалить черновик, /status — текущее состояние."
)

HELP = (
    "Бот составляет договор купли-продажи (ст. 454 ГК РФ).\n\n"
    "Как работает:\n"
    "1. Пришлите «1», «2» или «3», чтобы выбрать шаблон.\n"
    "2. Отвечайте на вопросы мастера по очереди. В блоках «продавец», «покупатель» "
    "и «автомобиль» можно вместо ручного ввода отправить фото документа — бот "
    "распознает данные автоматически.\n"
    "3. В конце бот сформирует DOCX и PDF, которые можно отправить сторонам и распечатать.\n\n"
    "/start — начать заново, /status — текущее состояние, /cancel — отменить.\n\n"
    + DISCLAIMER
)

NOMEN_MAP = {v["menu"]: k for k, v in CONTRACTS.items()}

CONFIRM_WORDS = {"да", "д", "yes", "y", "ок", "окей", "сформировать", "готово", "подтверждаю", "давай"}
CANCEL_WORDS = {"нет", "н", "no", "cancel", "отмена"}
PHOTO_WORDS = {"фото", "фотку", "фотографию", "фотография", "снимок", "скан", "сканы", "pic", "photo"}
MANUAL_WORDS = {"вручную", "вручн", "ручной", "ручн", "текстом", "введу", "text", "manual"}
SKIP_OPTS = {"далее", "дальше", "продолжить", "продолжаем", "без оборотной", "skip"}

DOC_TYPE_HINTS = {
    "passport": "фото паспорта (разворот стр. 2–3)",
    "pts": "фото ПТС (лицевая и оборотная стороны)",
}


class Engine:
    """Единый обработчик: не знает, из какого канала пришло сообщение."""

    def __init__(self, store: SessionStore, docgen: DocGenerator, ocr: Optional[OcrService] = None):
        self.store = store
        self.docgen = docgen
        self.ocr = ocr

    def process(self, msg: IncomingMessage) -> List[OutgoingItem]:
        if msg.file_bytes:
            return self._handle_file(msg)
        text = (msg.text or "").strip()
        if not text:
            return [OutgoingItem.txt("Пришлите команду. " + HELP)]

        low = text.lower()
        if low.startswith("/start"):
            return self._start(msg)
        if low.startswith("/cancel"):
            return self._cancel(msg)
        if low.startswith("/status"):
            return self._status(msg)
        if low.startswith("/help"):
            return [OutgoingItem.txt(HELP)]
        return self._handle_text(msg, low)

    # ---------- команды ----------

    def _start(self, msg: IncomingMessage) -> List[OutgoingItem]:
        self.store.clear(msg.channel, msg.chat_id)
        return [OutgoingItem.txt(MENU)]

    def _cancel(self, msg: IncomingMessage) -> List[OutgoingItem]:
        self.store.clear(msg.channel, msg.chat_id)
        return [OutgoingItem.txt("Договор отменён, черновик удалён. /start — начать заново.")]

    def _status(self, msg: IncomingMessage) -> List[OutgoingItem]:
        sess = self.store.get(msg.channel, msg.chat_id)
        if not sess or sess["state"] not in ("collecting", "confirm"):
            return [OutgoingItem.txt("Активного договора нет. " + MENU)]
        tpl = CONTRACTS[sess["template"]]
        total = len(tpl["fields"])
        answered = len([k for k, v in sess["answers"].items() if k and not k.startswith("_") and v])
        return [
            OutgoingItem.txt(
                f"Шаблон: {tpl['name']}. Заполнено полей: {answered} из {total}. "
                "Продолжайте отвечать, или /cancel чтобы отменить."
            )
        ]

    # ---------- обычный текст ----------

    def _handle_text(self, msg: IncomingMessage, low: str) -> List[OutgoingItem]:
        sess = self.store.get(msg.channel, msg.chat_id)
        if not sess:
            if low in NOMEN_MAP:
                return self._begin_collection(msg, NOMEN_MAP[low])
            return [OutgoingItem.txt("Начните с выбора шаблона. " + MENU)]

        state = sess["state"]
        if state == "collecting":
            return self._collect(msg, sess, low)
        if state == "confirm":
            return self._confirm(msg, sess, low)
        return [OutgoingItem.txt(MENU)]

    def _begin_collection(self, msg: IncomingMessage, slug: str) -> List[OutgoingItem]:
        tpl = CONTRACTS[slug]
        self.store.save(msg.channel, msg.chat_id, slug, 0, {}, "collecting")
        return [self._question_message(tpl, 0)]

    def _collect(self, msg: IncomingMessage, sess: dict, low: str) -> List[OutgoingItem]:
        slug = sess["template"]
        tpl = CONTRACTS[slug]
        fields = tpl["fields"]
        blocks = self._blocks(tpl)
        index = sess["index"]
        if index >= len(fields):
            return self._to_confirm(msg, sess)

        answers = dict(sess["answers"])
        await_state = answers.get("_await") or ""

        # --- ожидание фото / подтверждение распознавания ---
        if await_state.startswith("doc:"):
            return self._await_doc_text(msg, sess, tpl, blocks, answers, low)
        if await_state.startswith("confirm:"):
            return self._await_confirm_text(msg, sess, tpl, blocks, answers, low)

        # --- выбор способа ввода в начале блока ---
        block = self._block_at(blocks, index)
        if block and block["doc"] and index == block["start"] and not answers.get("_mode:" + block["role"]):
            if low in PHOTO_WORDS:
                answers["_mode:" + block["role"]] = "photo"
                answers["_await"] = f"doc:{block['role']}"
                self._persist(msg, sess, index, answers, "collecting")
                return [self._doc_hint_message(block)]
            answers["_mode:" + block["role"]] = "manual"
            self._persist(msg, sess, index, answers, "collecting")
            return [self._question_message(tpl, index, blocks, answers)]

        # --- пропуск полей, уже заполненных распознаванием ---
        while index < len(fields):
            f = fields[index]
            b = self._block_at(blocks, index)
            if b and f.key in b["ocr_keys"] and answers.get(f.key):
                index += 1
                continue
            break
        if index >= len(fields):
            self._persist(msg, sess, index, answers, "confirm")
            return self._to_confirm(msg, sess)
        if index != sess["index"]:
            self._persist(msg, sess, index, answers, "collecting")
            return [self._question_message(tpl, index, blocks, answers)]

        # --- обычное поле ---
        field = fields[index]
        value = (msg.text or "").strip()
        if not field.optional and (not value or low == "-"):
            return [OutgoingItem.txt("Поле не может быть пустым: " + field.prompt)]
        if field.optional and low == "-":
            value = ""
        if field.validator:
            error = field.validator(value)
            if error:
                return [OutgoingItem.txt(error)]

        answers[field.key] = value
        index += 1

        if index >= len(fields):
            self._persist(msg, sess, index, answers, "confirm")
            return self._to_confirm(msg, sess)
        self._persist(msg, sess, index, answers, "collecting")
        return [self._question_message(tpl, index, blocks, answers)]

    # ---------- файл (фото) ----------

    def _handle_file(self, msg: IncomingMessage) -> List[OutgoingItem]:
        if self.ocr is None:
            return [OutgoingItem.txt("Распознавание фото в этой сборке отключено.")]

        sess = self.store.get(msg.channel, msg.chat_id)
        if not sess or sess["state"] != "collecting":
            return [OutgoingItem.txt("Фото сейчас не нужно. Начните с /start и дождитесь запроса.")]

        tpl = CONTRACTS[sess["template"]]
        blocks = self._blocks(tpl)
        answers = dict(sess["answers"])
        await_state = answers.get("_await") or ""

        # фото отправлено сразу в начале блока с документом
        if not await_state.startswith("doc:"):
            block = self._block_at(blocks, sess["index"])
            if (
                block
                and block["doc"]
                and sess["index"] == block["start"]
                and not answers.get("_mode:" + block["role"])
            ):
                answers["_mode:" + block["role"]] = "photo"
                answers["_await"] = f"doc:{block['role']}"
                self._persist(msg, sess, sess["index"], answers, "collecting")
                return self._handle_file(msg)
            return [OutgoingItem.txt("Сейчас фото не нужно: напишите ответ текстом или начните с /start.")]

        role = await_state.split(":", 1)[1]
        block = next((b for b in blocks if b["role"] == role), None)
        if block is None:
            return [OutgoingItem.txt("Не понял, для чего фото. /start")]

        try:
            if block["doc"] == "passport":
                return self._process_passport_photo(msg, sess, tpl, block, answers)
            if block["doc"] == "pts":
                return self._process_pts_photo(msg, sess, tpl, block, answers)
        except OcrError as exc:
            log_exc = exc
            return [
                OutgoingItem.txt(
                    f"Ошибка распознавания: {log_exc}. Попробуйте другое фото или напишите «вручную»."
                )
            ]
        return [OutgoingItem.txt("Не понимаю этот тип документа. /start")]

    def _process_passport_photo(self, msg, sess, tpl, block, answers) -> List[OutgoingItem]:
        data = self.ocr.passport(msg.file_bytes, block["role"])
        if not data:
            return [
                OutgoingItem.txt(
                    "Не удалось распознать разворот паспорта. Отправьте чёткое фото "
                    "(стр. 2–3 с фото владельца) или напишите «вручную»."
                )
            ]
        answers["_ocr"] = json.dumps(data, ensure_ascii=False)
        answers["_await"] = f"confirm:{block['role']}"
        self._persist(msg, sess, sess["index"], answers, "collecting")
        return [self._ocr_confirm_message(tpl, block, data)]

    def _process_pts_photo(self, msg, sess, tpl, block, answers) -> List[OutgoingItem]:
        acc = json.loads(answers.get("_doc:" + block["role"], "{}"))
        if "front" not in acc:
            data = self.ocr.pts_front(msg.file_bytes)
            front = {k: v for k, v in data.items() if v}
            if not front:
                return [
                    OutgoingItem.txt(
                        "Не удалось распознать лицевую сторону ПТС. Отправьте чёткое фото "
                        "или напишите «вручную»."
                    )
                ]
            acc["front"] = front
            answers["_doc:" + block["role"]] = json.dumps(acc, ensure_ascii=False)
            self._persist(msg, sess, sess["index"], answers, "collecting")
            text = "Получил лицевую сторону ПТС:\n" + self._summary(tpl, front) + \
                "\n\nТеперь отправьте фото оборотной стороны ПТС (или «далее», если её нет)."
            return [OutgoingItem.txt(text)]

        back = self.ocr.pts_back(msg.file_bytes)
        merged = dict(acc["front"])
        merged.update({k: v for k, v in back.items() if v})
        if not merged:
            return [
                OutgoingItem.txt(
                    "Не удалось извлечь данные (лицевая сторона распознана ранее). "
                    "Напишите «далее», чтобы продолжить."
                )
            ]
        answers["_ocr"] = json.dumps(merged, ensure_ascii=False)
        answers["_await"] = f"confirm:{block['role']}"
        self._persist(msg, sess, sess["index"], answers, "collecting")
        return [self._ocr_confirm_message(tpl, block, merged)]

    # ---------- текст во время ожидания фото / подтверждения ----------

    def _await_doc_text(self, msg, sess, tpl, blocks, answers, low) -> List[OutgoingItem]:
        role = (answers["_await"]).split(":", 1)[1]
        block = next((b for b in blocks if b["role"] == role), None)
        index = sess["index"]

        if low in MANUAL_WORDS:
            answers["_mode:" + role] = "manual"
            for key in ("_await", "_ocr", "_doc:" + role):
                answers.pop(key, None)
            self._persist(msg, sess, index, answers, "collecting")
            return [self._question_message(tpl, index, blocks, answers)]

        if block and block["doc"] == "pts":
            acc = json.loads(answers.get("_doc:" + role, "{}"))
            if acc.get("front") and low in SKIP_OPTS:
                answers["_ocr"] = json.dumps(acc["front"], ensure_ascii=False)
                answers["_await"] = f"confirm:{role}"
                self._persist(msg, sess, index, answers, "collecting")
                return [self._ocr_confirm_message(tpl, block, acc["front"])]

        doc_name = DOC_TYPE_HINTS.get(block["doc"], "") if block else ""
        return [
            OutgoingItem.txt(
                f"Жду фото: {doc_name}. Или напишите «вручную», чтобы ввести данные текстом."
            )
        ]

    def _await_confirm_text(self, msg, sess, tpl, blocks, answers, low) -> List[OutgoingItem]:
        role = (answers["_await"]).split(":", 1)[1]
        block = next((b for b in blocks if b["role"] == role), None)
        data = json.loads(answers.get("_ocr", "{}"))

        if low in CONFIRM_WORDS:
            answers.update({k: v for k, v in data.items() if v})
            for key in ("_await", "_ocr"):
                answers.pop(key, None)
            if role:
                answers.pop("_doc:" + role, None)
            index = self._skip_filled(blocks, tpl["fields"], sess["index"], answers)
            if index >= len(tpl["fields"]):
                self._persist(msg, sess, index, answers, "confirm")
                return self._to_confirm(msg, sess)
            self._persist(msg, sess, index, answers, "collecting")
            return [self._question_message(tpl, index, blocks, answers)]

        if low in CANCEL_WORDS:
            answers["_await"] = f"doc:{role}"
            answers.pop("_ocr", None)
            answers.pop("_doc:" + role, None)
            self._persist(msg, sess, sess["index"], answers, "collecting")
            return [self._doc_hint_message(block)] if block else [OutgoingItem.txt("Попробуйте ещё раз.")]

        return [self._ocr_confirm_message(tpl, block, data)]

    # ---------- подтверждение всего договора ----------

    def _to_confirm(self, msg: IncomingMessage, sess: dict) -> List[OutgoingItem]:
        tpl = CONTRACTS[sess["template"]]
        return [self._confirm_message(tpl, sess["answers"])]

    def _confirm(self, msg: IncomingMessage, sess: dict, low: str) -> List[OutgoingItem]:
        if low in CONFIRM_WORDS:
            return self._generate(msg, sess)
        if low in CANCEL_WORDS:
            self.store.clear(msg.channel, msg.chat_id)
            return [OutgoingItem.txt("Отменено. Черновик удалён.")]
        tpl = CONTRACTS[sess["template"]]
        return [self._confirm_message(tpl, sess["answers"])]

    def _generate(self, msg: IncomingMessage, sess: dict) -> List[OutgoingItem]:
        slug = sess["template"]
        tpl = CONTRACTS[slug]
        answers = sess["answers"]
        context = tpl["build"](answers)
        base = f"ДКП_{slug}_{answers.get('signing_date', 'x')}"
        docx = self.docgen.render_docx(tpl["docx"], context)
        pdf = self.docgen.render_pdf(docx, base)
        self.store.clear(msg.channel, msg.chat_id)

        items = [
            OutgoingItem.txt(
                f"Договор готов: {tpl['name']}. Файлы ниже — DOCX (можно править) и PDF (для печати/подписи).\n"
                + DISCLAIMER
            )
        ]
        items.append(
            OutgoingItem.file(docx, f"{base}.docx", caption="ДКП (DOCX, редактируемый)")
        )
        if pdf:
            items.append(
                OutgoingItem.file(pdf, f"{base}.pdf", caption="ДКП (PDF, для печати)")
            )
        else:
            items.append(
                OutgoingItem.txt("PDF-конвертация недоступна на этом сервере — отправлен только DOCX.")
            )
        return items

    # ---------- формат сообщений ----------

    def _question_message(self, tpl: dict, index: int, blocks: Optional[list] = None,
                          answers: Optional[dict] = None) -> OutgoingItem:
        fields = tpl["fields"]
        field = fields[index]
        text = f"Шаблон: {tpl['name']}. Вопрос {index + 1} из {len(fields)}.\n"

        block = self._block_at(blocks or self._blocks(tpl), index)
        if (
            block and block["doc"]
            and index == block["start"]
            and (answers is not None) and not answers.get("_mode:" + block["role"])
        ):
            doc_name = DOC_TYPE_HINTS[block["doc"]]
            text += (
                f"\nБлок «{block['name']}»: могу заполнить автоматически — "
                f"отправьте {doc_name}, или введите данные вручную.\n"
            )

        text += field.prompt
        if field.example:
            text += f"\nНапример: {field.example}"
        if field.optional:
            text += "\nМожно пропустить — отправьте «-»."
        return OutgoingItem.txt(text)

    def _confirm_message(self, tpl: dict, answers: dict) -> OutgoingItem:
        lines = [f"Шаблон: {tpl['name']}. Проверьте данные:\n"]
        for field in tpl["fields"]:
            value = answers.get(field.key, "")
            lines.append(f"• {contract_label_field(field)}: {value or '—'}")
        lines.append("\nВсё верно? Пришлите «да», чтобы сформировать документ, или «нет», чтобы отменить.")
        return OutgoingItem.txt("\n".join(lines))

    def _doc_hint_message(self, block: dict) -> OutgoingItem:
        doc_name = DOC_TYPE_HINTS.get(block["doc"], "фото документа")
        return OutgoingItem.txt(
            f"Отправьте {doc_name}. Распознаю и подставлю данные. "
            "Чтобы ввести вручную — напишите «вручную»."
        )

    def _ocr_confirm_message(self, tpl: dict, block: dict, data: dict) -> OutgoingItem:
        return OutgoingItem.txt(
            f"Распознал данные блока «{block['name']}»:\n"
            + self._summary(tpl, data)
            + "\n\nВсё верно? «да» — принять и продолжить. «нет» — распознать заново, или «вручную»."
        )

    def _summary(self, tpl: dict, data: dict) -> str:
        field_map = {f.key: f for f in tpl["fields"]}
        lines = []
        for key, value in data.items():
            f = field_map.get(key)
            label = contract_label_field(f) if f else key.replace("_", " ")
            lines.append(f"• {label}: {value}")
        return "\n".join(lines) if lines else "— данных не извлечено —"

    # ---------- вспомогательное ----------

    def _blocks(self, tpl: dict) -> list:
        return blocks_of(tpl)

    def _block_at(self, blocks: list, index: int) -> Optional[dict]:
        cur = None
        for b in blocks:
            if b["start"] <= index:
                cur = b
            else:
                break
        return cur

    def _skip_filled(self, blocks: list, fields: list, index: int, answers: dict) -> int:
        while index < len(fields):
            f = fields[index]
            block = self._block_at(blocks, index)
            if block and f.key in block["ocr_keys"] and answers.get(f.key):
                index += 1
                continue
            break
        return index

    def _persist(self, msg: IncomingMessage, sess: dict, index: int, answers: dict, state: str) -> None:
        self.store.save(msg.channel, msg.chat_id, sess["template"], index, answers, state)