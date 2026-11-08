"""Конструкторы клавиатур ВКонтакте."""

from __future__ import annotations

import json
from typing import Any, Iterable

# Цвета кнопок в терминах VK API.
PRIMARY = "primary"
SECONDARY = "secondary"
POSITIVE = "positive"
NEGATIVE = "negative"


def button(
    label: str,
    *,
    payload: dict[str, Any] | None = None,
    color: str = SECONDARY,
    link: str | None = None,
) -> dict[str, Any]:
    if link:
        return {"action": {"type": "open_link", "label": label, "link": link}}
    return {
        "action": {
            "type": "text",
            "label": label,
            "payload": json.dumps(payload or {}, ensure_ascii=False),
        },
        "color": color,
    }


def inline_button(
    label: str,
    payload: dict[str, Any],
    *,
    color: str = SECONDARY,
) -> dict[str, Any]:
    return {
        "action": {
            "type": "callback",
            "label": label,
            "payload": json.dumps(payload, ensure_ascii=False),
        },
        "color": color,
    }


def keyboard(rows: Iterable[Iterable[dict[str, Any]]], *, inline: bool = False, one_time: bool = False) -> str:
    payload = {
        "inline": inline,
        "buttons": [list(row) for row in rows],
    }
    if not inline:
        payload["one_time"] = one_time
    return json.dumps(payload, ensure_ascii=False)


def main_keyboard() -> str:
    return keyboard(
        [
            [button("Помощь", payload={"cmd": "help"}, color=PRIMARY)],
            [button("Время", payload={"cmd": "time"})],
            [button("Подписка", payload={"cmd": "subscribe"})],
        ],
        one_time=False,
    )


def inline_menu() -> str:
    return keyboard(
        [
            [inline_button("Помощь", {"cmd": "help"}, color=PRIMARY)],
            [inline_button("Время", {"cmd": "time"})],
        ],
        inline=True,
    )
