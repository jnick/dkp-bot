from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class IncomingMessage:
    """Нормализованное входящее сообщение из любого канала."""

    channel: str
    chat_id: str
    user_id: str
    text: Optional[str] = None
    file_bytes: bytes = field(default_factory=bytes)
    filename: str = ""
    mime: str = ""


@dataclass
class OutgoingItem:
    """Готовый ответ каналу: текст или файл."""

    kind: str  # "text" | "file"
    text: str = ""
    file_bytes: bytes = field(default_factory=bytes)
    filename: str = ""
    caption: str = ""

    @staticmethod
    def txt(value: str) -> "OutgoingItem":
        return OutgoingItem(kind="text", text=value)

    @staticmethod
    def file(data: bytes, filename: str, caption: str = "") -> "OutgoingItem":
        return OutgoingItem(kind="file", file_bytes=data, filename=filename, caption=caption)