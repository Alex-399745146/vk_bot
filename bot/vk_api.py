"""Единственная точка общения с API ВКонтакте."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import httpx

API_URL = "https://api.vk.com/method"
LONGPOLL_WAIT = 25

log = logging.getLogger(__name__)


class VKAPIError(RuntimeError):
    def __init__(self, method: str, code: int, message: str, params: dict[str, Any] | None = None):
        super().__init__(f"{method}: [{code}] {message}")
        self.method = method
        self.code = code
        self.message = message
        self.params = params or {}


class VKAPI:
    def __init__(
        self,
        token: str,
        api_version: str = "5.199",
        *,
        group_id: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.api_version = api_version
        self.group_id = group_id
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "VKAPI":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(self, method: str, *, http_timeout: float | None = None, **params: Any) -> Any:
        """Вызов метода API. Ошибки ВК превращаются в VKAPIError."""
        if self._client is None:
            raise RuntimeError("VKAPI используется вне 'async with'")

        payload = {"access_token": self.token, "v": self.api_version, **params}
        response = await self._client.post(
            f"{API_URL}/{method}", data=payload, timeout=http_timeout
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            error = data["error"]
            code = int(error.get("error_code", 0))
            message = str(error.get("error_msg", "unknown error"))
            if code == 911:
                message += (
                    " — клавиатура не разрешена: включите «Возможности ботов»"
                    " в Управление → Сообщения → Настройки для бота"
                )
            raise VKAPIError(method, code, message, error.get("request_params"))
        return data.get("response")

    async def send_message(
        self,
        peer_id: int,
        text: str,
        *,
        keyboard: str | None = None,
        attachment: str | None = None,
        reply_to: int | None = None,
        dont_parse_links: bool = False,
    ) -> int | None:
        params: dict[str, Any] = {
            "peer_id": peer_id,
            "message": text,
            # Без уникального random_id ВК считает сообщения дублями.
            "random_id": secrets.randbits(63),
        }
        if keyboard:
            params["keyboard"] = keyboard
        if attachment:
            params["attachment"] = attachment
        if reply_to:
            params["reply_to"] = reply_to
        if dont_parse_links:
            params["dont_parse_links"] = 1
        return await self.call("messages.send", **params)

    async def answer_button(self, event: ButtonEventLike, text: str | None = None) -> None:
        """Ответ на нажатие callback-кнопки (message_event)."""
        params: dict[str, Any] = {
            "event_id": event.event_id,
            "user_id": event.from_id,
            "peer_id": event.peer_id,
        }
        if text:
            params["event_data"] = (text[:1000])
        else:
            params["event_data"] = "{}"
        await self.call("messages.sendMessageEventAnswer", **params)

    async def get_longpoll_server(self) -> dict[str, Any]:
        if not self.group_id:
            raise RuntimeError("Для LongPoll нужен group_id")
        return await self.call("groups.getLongPollServer", group_id=self.group_id)

    async def longpoll_check(self, server: str, key: str, ts: str | int) -> dict[str, Any]:
        """Один цикл a_check. Таймаут HTTP больше wait, чтобы не рвать ожидание."""
        if self._client is None:
            raise RuntimeError("VKAPI используется вне 'async with'")
        params = {"act": "a_check", "key": key, "ts": ts, "wait": LONGPOLL_WAIT}

        # print("LongPoll URL:", repr(f"https://{server}"))

        async with self._client.stream(
            "GET", server, params=params,
            timeout=httpx.Timeout(LONGPOLL_WAIT + 15, connect=10.0),
        ) as response:
            response.raise_for_status()
            await response.aread()
            return response.json()

    async def delete_message(self, peer_id: int, message_id: int, *, for_all: bool = False) -> None:
        await self.call(
            "messages.delete",
            peer_id=peer_id,
            message_ids=message_id,
            delete_for_all=int(for_all),
        )

    async def set_activity(self, peer_id: int, kind: str = "typing") -> None:
        """Показать «печатает…» в диалоге."""
        try:
            await self.call("messages.setActivity", peer_id=peer_id, type=kind, group_id=self.group_id)
        except VKAPIError as exc:  # не критично, просто пропускаем
            log.debug("setActivity failed: %s", exc)


class ButtonEventLike:
    """Протокол-подобный тип, чтобы не тянуть модели в клиент."""

    event_id: str
    from_id: int
    peer_id: int


async def retry(coro_factory, *, attempts: int = 3, delay: float = 1.0):
    """Повтор для сетевых операций: 5xx и таймауты."""
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == attempts:
                raise
            log.warning("Сетевая ошибка (попытка %s/%s): %s", attempt, attempts, exc)
            await asyncio.sleep(delay * attempt)
