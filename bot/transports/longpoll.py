"""Транспорт LongPoll (Bots LongPoll API сообщества)."""

from __future__ import annotations

import httpx
import asyncio
import logging

from ..config import Config
from ..dispatcher import Context, Dispatcher
from ..models import Update
from ..vk_api import VKAPI, VKAPIError

log = logging.getLogger(__name__)
RETRY_DELAY = 3.0


async def run(config: Config, dispatcher: Dispatcher, api: VKAPI) -> None:
    """Бесконечный цикл получения событий. Останавливается по Ctrl+C."""
    log.info("LongPoll запущен для сообщества %s", config.group_id)
    while True:
        try:
            await _poll_loop(config, dispatcher, api)
        except asyncio.CancelledError:
            raise
        except (
            VKAPIError,
            OSError,
            ValueError,
            httpx.TransportError,
        ) as exc:
            log.warning(
                "LongPoll упал: %s. Переподключаюсь через %.0f с",
                exc,
                RETRY_DELAY,
            )
            await asyncio.sleep(RETRY_DELAY)



async def _poll_loop(config: Config, dispatcher: Dispatcher, api: VKAPI) -> None:
    server_info = await api.get_longpoll_server()
    server = str(server_info["server"])
    key = str(server_info["key"])
    ts = str(server_info["ts"])
    log.info("LongPoll-сервер получен: %s", server)

    while True:
        data = await api.longpoll_check(server, key, ts)

        failed = data.get("failed")
        if failed is not None:
            if failed == 1:
                ts = str(data["ts"])
                log.debug("LongPoll: обновлён ts")
                continue
            # failed == 2 (ключ устарел) или 3 (потеряна история) — пересоздаём сессию.
            log.info("LongPoll: failed=%s, пересоздаю сессию", failed)
            server_info = await api.get_longpoll_server()
            server = str(server_info["server"])
            key = str(server_info["key"])
            ts = str(server_info["ts"])
            continue

        ts = str(data["ts"])
        for event in data.get("updates", []):
            if event.get("type") != "message_new":
                continue
            message = event.get("object", {}).get("message", {})
            update = Update.from_message(message)
            if update.from_id <= 0:  # сообщения самого сообщества
                continue
            try:
                await dispatcher.dispatch(update, Context(api=api, update=update))
            except Exception:
                log.exception("Ошибка обработки сообщения от %s", update.from_id)
