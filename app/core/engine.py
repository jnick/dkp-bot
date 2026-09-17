from __future__ import annotations

from typing import List

from app.core.contracts import CONTRACTS, contract_label_field
from app.core.docgen import DocGenerator
from app.core.messages import IncomingMessage, OutgoingItem
from app.core.session import SessionStore

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
    "2. Отвечайте на вопросы мастера по очереди.\n"
    "3. В конце бот сформирует DOCX и PDF, которые можно отправить сторонам и распечатать.\n\n"
    "/start — начать заново, /status — текущее состояние, /cancel — отменить.\n\n"
    + DISCLAIMER
)

NOMEN_MAP = {v["menu"]: k for k, v in CONTRACTS.items()}

CONFIRM_WORDS = {"да", "д", "yes", "y", "ок", "окей", "сформировать", "готово", "подтверждаю", "давай"}
CANCEL_WORDS = {"нет", "н", "no", "cancel", "отмена"}


class Engine:
    """Единый обработчик: не знает, из какого канала пришло сообщение."""

    def __init__(self, store: SessionStore, docgen: DocGenerator):
        self.store = store
        self.docgen = docgen

    def process(self, msg: IncomingMessage) -> List[OutgoingItem]:
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
        answered = len([k for k in sess["answers"] if sess["answers"].get(k)])
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
        index = sess["index"]
        if index >= len(fields):
            return self._to_confirm(msg, sess)

        field = fields[index]
        answers = dict(sess["answers"])
        if not field.optional and (not (msg.text or "").strip() or low == "-"):
            return [OutgoingItem.txt("Поле не может быть пустым: " + field.prompt)]
        if field.optional and low == "-":
            value = ""
        else:
            value = (msg.text or "").strip()
        if field.validator:
            error = field.validator(value)
            if error:
                return [OutgoingItem.txt(error)]

        answers[field.key] = value
        index += 1

        if index >= len(fields):
            self.store.save(msg.channel, msg.chat_id, slug, index, answers, "confirm")
            return self._to_confirm(msg, sess)
        self.store.save(msg.channel, msg.chat_id, slug, index, answers, "collecting")
        return [self._question_message(tpl, index)]

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

    # ---------- формат сообщений мастера ----------

    def _question_message(self, tpl: dict, index: int) -> OutgoingItem:
        fields = tpl["fields"]
        field = fields[index]
        text = f"Шаблон: {tpl['name']}. Вопрос {index + 1} из {len(fields)}.\n{field.prompt}"
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