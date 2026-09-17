from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.engine import Engine


class BaseChannel(ABC):
    """Адаптер канала: приводит события к IncomingMessage и отдаёт ответы Общему Engine."""

    name: str = "base"

    def __init__(self, engine: Engine):
        self.engine = engine

    @abstractmethod
    async def run(self) -> None:
        raise NotImplementedError