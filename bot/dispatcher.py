"""Диспетчер сообщений: маршрутизация не зависит от транспорта."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .models import Update
from .vk_api import VKAPI

log = logging.getLogger(__name__)

Handler = Callable[["Context"], Awaitable[None]]
Matcher = Callable[[Update], bool]


def normalize(text: str) -> str:
    """Приводит текст к виду для сравнения: нижний регистр, один пробел."""
    return " ".join(text.casefold().split())


def _strip_mention(text: str) -> str:
    """'/start@my_bot' -> '/start'."""
    head, sep, tail = text.partition(" ")
    if "@" in head:
        head = head.split("@", 1)[0]
    return f"{head}{sep}{tail}".strip()


@dataclass(slots=True)
class Context:
    """То, что получает хендлер: сообщение, API и удобный reply."""

    api: VKAPI
    update: Update

    async def reply(
        self,
        text: str,
        *,
        keyboard: str | None = None,
        attachment: str | None = None,
        reply_to: bool = False,
    ) -> None:
        await self.api.send_message(
            self.update.peer_id,
            text,
            keyboard=keyboard,
            attachment=attachment,
            reply_to=self.update.message_id if reply_to else None,
        )


@dataclass(slots=True)
class Route:
    handler: Handler
    text: str | None = None
    cmd: str | None = None
    func: Matcher | None = None

    def matches(self, update: Update) -> bool:
        if self.cmd is not None:
            return update.command == self.cmd
        if self.text is not None:
            current = normalize(_strip_mention(update.text))
            if current == self.text:
                return True
            # Команды вроде "/start" допускают аргументы, обычные слова — нет.
            return self.text.startswith("/") and current.startswith(self.text + " ")
        if self.func is not None:
            return self.func(update)
        return False


class Dispatcher:
    def __init__(self) -> None:
        self.routes: list[Route] = []
        self._fallback: Handler | None = None

    def message(
        self,
        *,
        text: str | list[str] | None = None,
        cmd: str | None = None,
        func: Matcher | None = None,
    ):
        """Декоратор: регистрирует хендлер на текст, payload-команду или предикат."""
        texts = [text] if isinstance(text, str) else text

        def decorator(handler: Handler) -> Handler:
            if texts:
                for value in texts:
                    self.routes.append(Route(handler=handler, text=normalize(value)))
            if cmd is not None:
                self.routes.append(Route(handler=handler, cmd=cmd))
            if func is not None:
                self.routes.append(Route(handler=handler, func=func))
            if not texts and cmd is None and func is None:
                raise ValueError("Нужен хотя бы один критерий: text, cmd или func")
            return handler

        return decorator

    def fallback(self, handler: Handler) -> Handler:
        self._fallback = handler
        return handler

    async def dispatch(self, update: Update, ctx: Context) -> bool:
        for route in self.routes:
            try:
                matched = route.matches(update)
            except Exception:  # предикат не должен ронять бота
                log.exception("Ошибка в матчере для %r", update.text)
                continue
            if matched:
                log.debug("Обработчик: %s", getattr(route.handler, "__name__", route.handler))
                await route.handler(ctx)
                return True

        if self._fallback is not None:
            log.debug("Обработчик: fallback")
            await self._fallback(ctx)
            return True
        return False
