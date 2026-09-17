from __future__ import annotations

import asyncio
import io
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import BufferedInputFile, Message

from app.channels.base import BaseChannel
from app.core.engine import Engine
from app.core.messages import IncomingMessage

log = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    name = "telegram"

    def __init__(self, token: str, engine: Engine):
        super().__init__(engine)
        self.token = token

    async def run(self) -> None:
        bot = Bot(self.token)
        dp = Dispatcher()

        @dp.message()
        async def on_message(message: Message) -> None:
            file_bytes, filename, mime = b"", "", ""
            text = message.text or message.caption
            if message.photo:
                photo = message.photo[-1]
                try:
                    buf = io.BytesIO()
                    await bot.download(photo.file_id, destination=buf)
                    file_bytes = buf.getvalue()
                    filename, mime = "photo.jpg", "image/jpeg"
                except Exception:
                    log.exception("Не удалось скачать фото")
            elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
                try:
                    buf = io.BytesIO()
                    await bot.download(message.document.file_id, destination=buf)
                    file_bytes = buf.getvalue()
                    filename = message.document.file_name or "document"
                    mime = message.document.mime_type
                except Exception:
                    log.exception("Не удалось скачать документ")

            incoming = IncomingMessage(
                channel=self.name,
                chat_id=str(message.chat.id),
                user_id=str(message.from_user.id or ""),
                text=text,
                file_bytes=file_bytes,
                filename=filename,
                mime=mime,
            )
            if incoming.file_bytes:
                results = await asyncio.to_thread(self.engine.process, incoming)
            else:
                results = self.engine.process(incoming)
            for out in results:
                try:
                    if out.kind == "file":
                        await message.answer_document(
                            BufferedInputFile(out.file_bytes, filename=out.filename),
                            caption=out.caption or None,
                        )
                    else:
                        await message.answer(out.text)
                except Exception:
                    log.exception("Ошибка отправки ответа в Telegram")

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)