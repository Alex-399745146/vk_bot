"""Нормализованное входящее сообщение, не зависящее от транспорта."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _parse_payload(raw: Any) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


@dataclass(slots=True)
class Update:
    """Сообщение из LongPoll или Callback API в одном формате."""

    peer_id: int
    from_id: int
    text: str
    message_id: int | None = None
    payload: dict[str, Any] | None = None
    conversation_message_id: int | None = None
    is_chat: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "Update":
        peer_id = int(message.get("peer_id") or message.get("from_id") or 0)
        from_id = int(message.get("from_id") or 0)
        return cls(
            peer_id=peer_id,
            from_id=from_id,
            text=str(message.get("text") or "").strip(),
            message_id=message.get("id"),
            payload=_parse_payload(message.get("payload")),
            conversation_message_id=message.get("conversation_message_id"),
            is_chat=peer_id >= 2_000_000_000,
            raw=message,
        )

    @property
    def command(self) -> str | None:
        """Команда из payload кнопки.

        Кнопка «Начать» в сообществе присылает {"command": "start"},
        обычные кнопки — {"cmd": "..."}, поэтому понимаем оба варианта.
        """
        if not self.payload:
            return None
        for key in ("cmd", "command"):
            value = self.payload.get(key)
            if isinstance(value, str):
                return value
        return None


@dataclass(slots=True)
class ButtonEvent:
    """Нажатие callback-кнопки (только Callback API)."""

    peer_id: int
    from_id: int
    event_id: str
    payload: dict[str, Any] | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "ButtonEvent":
        return cls(
            peer_id=int(event.get("peer_id") or 0),
            from_id=int(event.get("user_id") or 0),
            event_id=str(event.get("event_id") or ""),
            payload=_parse_payload(event.get("payload")),
            raw=event,
        )
