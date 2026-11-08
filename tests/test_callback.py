"""Интеграционные тесты Callback-сервера: aiohttp без сети и без токена."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Config
from bot.handlers import build_dispatcher
from bot.transports.callback import CallbackServer


class FakeAPI:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.answers: list[tuple[str, str]] = []

    async def send_message(self, peer_id: int, text: str, **kwargs) -> None:
        self.sent.append({"peer_id": peer_id, "text": text, **kwargs})

    async def call(self, method: str, **params):
        if method == "users.get":
            return [{"first_name": "Иван"}]
        return None

    async def answer_button(self, event, text: str | None = None) -> None:
        self.answers.append((event.event_id, text or ""))


def config(**overrides) -> Config:
    base = dict(token="test", group_id=1, transport="callback", confirmation_code="confirm-me", secret_key="s3cret")
    base.update(overrides)
    return Config(**base)  # type: ignore[arg-type]


def build_app(server: CallbackServer) -> web.Application:
    app = web.Application()
    app.router.add_post(server.config.callback_path, server.handle)
    app.router.add_get("/health", server.health)
    return app


@pytest.mark.asyncio
async def test_confirmation() -> None:
    server = CallbackServer(config(), build_dispatcher(), FakeAPI())
    async with TestClient(TestServer(build_app(server))) as client:
        response = await client.post("/vk/callback", json={"type": "confirmation", "secret": "s3cret"})
        assert response.status == 200
        assert await response.text() == "confirm-me"


@pytest.mark.asyncio
async def test_secret_is_checked() -> None:
    server = CallbackServer(config(), build_dispatcher(), FakeAPI())
    async with TestClient(TestServer(build_app(server))) as client:
        response = await client.post("/vk/callback", json={"type": "message_new", "secret": "wrong"})
        assert response.status == 403


@pytest.mark.asyncio
async def test_message_new_is_dispatched() -> None:
    api = FakeAPI()
    server = CallbackServer(config(), build_dispatcher(), api)
    async with TestClient(TestServer(build_app(server))) as client:
        payload = {
            "type": "message_new",
            "secret": "s3cret",
            "event_id": "evt-1",
            "object": {"message": {"id": 10, "peer_id": 42, "from_id": 42, "text": "/help"}},
        }
        response = await client.post("/vk/callback", json=payload)
        assert response.status == 200
        assert await response.text() == "ok"

        await server.drain()
        assert len(api.sent) == 1
        assert "Я умею" in api.sent[0]["text"]


@pytest.mark.asyncio
async def test_duplicate_event_is_ignored() -> None:
    api = FakeAPI()
    server = CallbackServer(config(), build_dispatcher(), api)
    payload = {
        "type": "message_new",
        "secret": "s3cret",
        "event_id": "evt-2",
        "object": {"message": {"id": 11, "peer_id": 42, "from_id": 42, "text": "раз"}},
    }
    async with TestClient(TestServer(build_app(server))) as client:
        await client.post("/vk/callback", json=payload)
        await client.post("/vk/callback", json=payload)
        await server.drain()

    assert len(api.sent) == 1


@pytest.mark.asyncio
async def test_message_event_is_answered() -> None:
    api = FakeAPI()
    server = CallbackServer(config(), build_dispatcher(inline_buttons=True), api)
    payload = {
        "type": "message_event",
        "secret": "s3cret",
        "event_id": "evt-3",
        "object": {"event_id": "btn-1", "peer_id": 42, "user_id": 42, "payload": {"cmd": "time"}},
    }
    async with TestClient(TestServer(build_app(server))) as client:
        await client.post("/vk/callback", json=payload)
        await server.drain()

    # Кнопка не просто «гасится»: хендлер отправляет реальный ответ в чат.
    assert len(api.sent) == 1
    assert "по Москве" in api.sent[0]["text"]
    assert api.answers[0][0] == "btn-1"


@pytest.mark.asyncio
async def test_health() -> None:
    server = CallbackServer(config(), build_dispatcher(), FakeAPI())
    async with TestClient(TestServer(build_app(server))) as client:
        response = await client.get("/health")
        assert response.status == 200
        assert (await response.json())["status"] == "ok"
