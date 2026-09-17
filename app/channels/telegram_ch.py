from __future__ import annotations

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
            incoming = IncomingMessage(
                channel=self.name,
                chat_id=str(message.chat.id),
                user_id=str(message.from_user.id or ""),
                text=message.text,
            )
            for out in self.engine.process(incoming):
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