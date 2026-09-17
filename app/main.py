from __future__ import annotations

import asyncio
import logging
import sys

from app import config
from app.channels.telegram_ch import TelegramChannel
from app.core.docgen import DocGenerator
from app.core.engine import Engine
from app.core.session import SessionStore
from app.ocr.recognize import OcrService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("dkp")


def main() -> None:
    store = SessionStore(config.DB_PATH)
    engine = Engine(store, DocGenerator(), OcrService())

    channels = []
    if config.TELEGRAM_BOT_TOKEN:
        channels.append(TelegramChannel(config.TELEGRAM_BOT_TOKEN, engine))
    else:
        log.error("TELEGRAM_BOT_TOKEN не задан. Создайте бота через @BotFather и укажите токен в .env")
        sys.exit(1)

    async def _run_all() -> None:
        await asyncio.gather(*(ch.run() for ch in channels))

    asyncio.run(_run_all())


if __name__ == "__main__":
    main()