"""Конфигурация бота: читается из переменных окружения / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True, slots=True)
class Config:
    token: str
    group_id: int
    api_version: str = "5.199"
    transport: str = "longpoll"
    callback_host: str = "0.0.0.0"
    callback_port: int = 8080
    callback_path: str = "/vk/callback"
    confirmation_code: str = ""
    secret_key: str = ""

    @property
    def callback_url(self) -> str:
        return f"http://{self.callback_host}:{self.callback_port}{self.callback_path}"


class ConfigError(RuntimeError):
    """Не хватает обязательных настроек."""


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def load_config() -> Config:
    token = _env("VK_TOKEN")
    group_raw = _env("VK_GROUP_ID")
    if not token:
        raise ConfigError("Не задан VK_TOKEN (токен сообщества с правами на сообщения)")
    if not group_raw:
        raise ConfigError("Не задан VK_GROUP_ID (числовой id сообщества)")

    transport = _env("BOT_TRANSPORT", "longpoll").lower()
    if transport not in {"longpoll", "callback"}:
        raise ConfigError("BOT_TRANSPORT должен быть 'longpoll' или 'callback'")

    if transport == "callback" and not _env("VK_CONFIRMATION_CODE"):
        raise ConfigError("Для Callback API нужен VK_CONFIRMATION_CODE из настроек сообщества")

    return Config(
        token=token,
        group_id=int(group_raw),
        api_version=_env("VK_API_VERSION", "5.199"),
        transport=transport,
        callback_host=_env("CALLBACK_HOST", "0.0.0.0"),
        callback_port=int(_env("CALLBACK_PORT", "8080")),
        callback_path=_env("CALLBACK_PATH", "/vk/callback"),
        confirmation_code=_env("VK_CONFIRMATION_CODE"),
        secret_key=_env("VK_SECRET_KEY"),
    )
