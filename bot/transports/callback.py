"""Транспорт Callback API: HTTP-сервер, который принимает события ВК."""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from aiohttp import web

from ..config import Config
from ..dispatcher import Context, Dispatcher
from ..models import ButtonEvent, Update
from ..vk_api import VKAPI, retry

log = logging.getLogger(__name__)

MAX_SEEN_EVENTS = 1000


class CallbackServer:
    def __init__(self, config: Config, dispatcher: Dispatcher, api: VKAPI) -> None:
        self.config = config
        self.dispatcher = dispatcher
        self.api = api
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()
        self._tasks: set[asyncio.Task[None]] = set()

    # ---------- HTTP ----------

    async def handle(self, request: web.Request) -> web.Response:
        try:
            event = await request.json()
        except ValueError:
            return web.Response(status=400, text="bad json")

        if self.config.secret_key and event.get("secret") != self.config.secret_key:
            log.warning("Отклонён запрос с неверным secret")
            return web.Response(status=403, text="forbidden")

        event_type = event.get("type")
        if event_type == "confirmation":
            return web.Response(text=self.config.confirmation_code, content_type="text/plain")

        event_id = str(event.get("event_id") or "")
        if event_id and not self._register(event_id):
            # ВК повторяет доставку при таймауте — второй раз не обрабатываем.
            return web.Response(text="ok")

        # ВК ждёт ответ быстро, поэтому обработку уводим в фон.
        self._spawn(self._process(event_type, event))
        return web.Response(text="ok")

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "group_id": self.config.group_id})

    # ---------- События ----------

    async def _process(self, event_type: str | None, event: dict) -> None:
        try:
            if event_type == "message_new":
                message = event.get("object", {}).get("message", {})
                update = Update.from_message(message)
                if update.from_id <= 0:
                    return
                await self.dispatcher.dispatch(update, Context(api=self.api, update=update))
            elif event_type == "message_event":
                await self._on_button(event.get("object", {}))
        except Exception:
            log.exception("Ошибка обработки события %s", event_type)

    async def _on_button(self, raw: dict) -> None:
        """Нажатие inline-кнопки: прогоняем через диспетчер и гасим событие."""
        event = ButtonEvent.from_event(raw)
        update = Update(
            peer_id=event.peer_id,
            from_id=event.from_id,
            text="",
            payload=event.payload,
            raw=raw,
        )
        try:
            await self.dispatcher.dispatch(update, Context(api=self.api, update=update))
        finally:
            try:
                await retry(lambda: self.api.answer_button(event))
            except Exception:
                log.warning("Не удалось ответить на message_event %s", event.event_id, exc_info=True)

    # ---------- Служебное ----------

    def _register(self, event_id: str) -> bool:
        if event_id in self._seen:
            return False
        self._seen.add(event_id)
        self._seen_order.append(event_id)
        if len(self._seen_order) > MAX_SEEN_EVENTS:
            self._seen.discard(self._seen_order.popleft())
        return True

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Дождаться завершения фоновых обработчиков (используется в тестах)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


async def run(config: Config, dispatcher: Dispatcher, api: VKAPI) -> None:
    server = CallbackServer(config, dispatcher, api)
    app = web.Application()
    app.router.add_post(config.callback_path, server.handle)
    app.router.add_get("/health", server.health)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, config.callback_host, config.callback_port)
    await site.start()
    log.info("Callback API слушает http://%s:%s%s", config.callback_host, config.callback_port, config.callback_path)

    try:
        await asyncio.Event().wait()  # живём до отмены
    finally:
        await server.shutdown()
        await runner.cleanup()
