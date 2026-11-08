"""Бизнес-логика бота: только хендлеры, без сети и транспортов."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .dispatcher import Context, Dispatcher
from .keyboards import inline_menu, main_keyboard
from .models import Update

log = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")

HELP_TEXT = (
    "Я умею немногое, но честно:\n"
    "• /start — поздороваться и показать кнопки\n"
    "• /help — эта справка\n"
    "• /time — текущее время по Москве\n"
    "• любой текст — повторю его эхом\n\n"
    "Кнопки тоже работают."
)


def build_dispatcher(*, inline_buttons: bool = False) -> Dispatcher:
    """inline_buttons=True — для Callback API (кнопки type=callback).

    В LongPoll inline-кнопки не приходят, поэтому там отдаём reply-клавиатуру.
    """
    dp = Dispatcher()
    help_keyboard = inline_menu if inline_buttons else main_keyboard

    @dp.message(cmd="help")
    @dp.message(text=["/help", "помощь", "help"])
    async def help_handler(ctx: Context) -> None:
        await ctx.reply(HELP_TEXT, keyboard=help_keyboard())

    @dp.message(cmd="time")
    @dp.message(text=["/time", "время"])
    async def time_handler(ctx: Context) -> None:
        now = datetime.now(MSK)
        await ctx.reply(f"Сейчас {now:%H:%M:%S} по Москве ({now:%d.%m.%Y}).")

    @dp.message(cmd="start")
    @dp.message(text=["/start", "начать", "start", "привет", "hello"])
    async def start_handler(ctx: Context) -> None:
        name = await _user_name(ctx)
        await ctx.reply(
            f"Привет, {name}! Я бот на vkbottle-free архитектуре: LongPoll или Callback API.\n\n"
            "Напиши /help, чтобы увидеть команды.",
            keyboard=main_keyboard(),
        )

    @dp.message(cmd="subscribe")
    async def subscribe_handler(ctx: Context) -> None:
        await ctx.reply("Готово: подписка оформлена (демо-кнопка).")

    @dp.fallback
    async def echo_handler(ctx: Context) -> None:
        text = ctx.update.text
        if not text:
            await ctx.reply("Я понимаю только текст. Напиши /help.")
            return
        if text.startswith("/"):
            await ctx.reply("Неизвестная команда. Список: /help")
            return
        await ctx.reply(f"Ты написал: {text[:3500]}")

    return dp


async def _user_name(ctx: Context) -> str:
    """Имя пользователя, с запасным вариантом без лишнего запроса."""
    try:
        users = await ctx.api.call(
            "users.get", user_ids=ctx.update.from_id, fields="first_name", name_case="nom"
        )
        if users:
            return str(users[0].get("first_name") or "друг")
    except Exception:
        log.debug("users.get не сработал, отвечаю без имени", exc_info=True)
    return "друг"
