"""Тесты диспетчера: без сети и без токена."""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from bot.dispatcher import Context, Dispatcher
from bot.handlers import build_dispatcher
from bot.models import Update


class FakeAPI:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, peer_id: int, text: str, **kwargs) -> None:
        self.sent.append({"peer_id": peer_id, "text": text, **kwargs})

    async def call(self, method: str, **params):
        if method == "users.get":
            return [{"first_name": "Иван"}]
        return None


def make_update(text: str = "", *, payload: dict | None = None, from_id: int = 42, peer_id: int | None = None) -> Update:
    return Update(peer_id=peer_id or from_id, from_id=from_id, text=text, message_id=1, payload=payload)


async def send(dispatcher: Dispatcher, update: Update) -> list[dict]:
    api = FakeAPI()
    await dispatcher.dispatch(update, Context(api=api, update=update))
    return api.sent


@pytest.fixture(scope="module")
def dp() -> Dispatcher:
    return build_dispatcher()


def test_help_by_text(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("/help")))
    assert len(sent) == 1
    assert "Я умею" in sent[0]["text"]
    assert sent[0]["keyboard"]
    # LongPoll: reply-клавиатура, inline-кнопки тут не сработают.
    assert json.loads(sent[0]["keyboard"])["inline"] is False


def test_help_inline_for_callback() -> None:
    dp = build_dispatcher(inline_buttons=True)
    sent = asyncio.run(send(dp, make_update("/help")))
    assert json.loads(sent[0]["keyboard"])["inline"] is True


def test_help_with_mention(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("/help@my_bot")))
    assert "Я умею" in sent[0]["text"]


def test_help_by_button_payload(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("", payload={"cmd": "help"})))
    assert "Я умею" in sent[0]["text"]


def test_start_button_payload_command(dp: Dispatcher) -> None:
    # Кнопка «Начать» присылает {"command": "start"} без текста.
    sent = asyncio.run(send(dp, make_update("", payload={"command": "start"})))
    assert "Привет" in sent[0]["text"]
    assert sent[0]["keyboard"]


def test_start_greets_by_name(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("/start")))
    assert "Привет, Иван" in sent[0]["text"]
    assert sent[0]["keyboard"]


def test_time(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("/time")))
    assert re.search(r"\d{2}:\d{2}:\d{2}", sent[0]["text"])


def test_fallback_echoes(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("привет как дела")))
    assert sent[0]["text"] == "Ты написал: привет как дела"


def test_unknown_command(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("/abracadabra")))
    assert "Неизвестная команда" in sent[0]["text"]


def test_chat_replies_to_peer_id(dp: Dispatcher) -> None:
    sent = asyncio.run(send(dp, make_update("тест", from_id=42, peer_id=2_000_000_001)))
    assert sent[0]["peer_id"] == 2_000_000_001


def test_no_match_without_fallback() -> None:
    dp = Dispatcher()

    @dp.message(text="да")
    async def yes(ctx: Context) -> None:  # pragma: no cover - не должен вызываться
        await ctx.reply("ok")

    sent = asyncio.run(send(dp, make_update("нет")))
    assert sent == []


def test_matcher_error_does_not_crash() -> None:
    dp = Dispatcher()

    @dp.message(func=lambda u: 1 / 0)  # type: ignore[arg-type]
    async def broken(ctx: Context) -> None:  # pragma: no cover
        await ctx.reply("не должно случиться")

    @dp.fallback
    async def fallback(ctx: Context) -> None:
        await ctx.reply("fallback")

    sent = asyncio.run(send(dp, make_update("что угодно")))
    assert sent[0]["text"] == "fallback"
