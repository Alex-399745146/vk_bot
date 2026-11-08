"""Точка входа: python -m bot [--transport longpoll|callback]."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from dataclasses import replace

from .config import ConfigError, load_config
from .handlers import build_dispatcher
from .vk_api import VKAPI

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Чат-бот ВКонтакте")
    parser.add_argument("--transport", choices=("longpoll", "callback"), help="переопределить BOT_TRANSPORT")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # httpx логирует каждый a_check — по умолчанию глушим, но можно включить LOG_HTTP=1.
    logging.getLogger("httpx").setLevel(
        logging.INFO if os.getenv("LOG_HTTP", "").lower() in {"1", "true", "yes"} else logging.WARNING
    )

    try:
        config = load_config()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    if args.transport:
        config = replace(config, transport=args.transport)

    dispatcher = build_dispatcher(inline_buttons=config.transport == "callback")

    async with VKAPI(config.token, config.api_version, group_id=config.group_id) as api:
        stop = asyncio.Event()
        _install_signal_handlers(stop)

        if config.transport == "longpoll":
            from .transports import longpoll as transport
        else:
            from .transports import callback as transport

        runner = asyncio.create_task(transport.run(config, dispatcher, api))
        stopper = asyncio.create_task(stop.wait())
        done, pending = await asyncio.wait({runner, stopper}, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        if runner in done and not runner.cancelled():
            exc = runner.exception()
            if exc is not None:
                raise exc
        log.info("Остановлено")
    return 0


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            # Windows: add_signal_handler не поддерживает SIGTERM.
            pass


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        log.info("Прервано пользователем")
