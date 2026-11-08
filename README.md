# VK Bot (LongPoll + Callback API)

Чат-бот ВКонтакте на Python 3.11+. Одна бизнес-логика, два транспорта:
LongPoll (для локального запуска) и Callback API (для продакшена).
Без тяжёлых фреймворков — только `httpx`, `aiohttp` и `python-dotenv`.

## Структура

```
bot/
  __main__.py          # CLI: python -m bot --transport longpoll|callback
  config.py            # настройки из .env
  models.py            # Update / ButtonEvent — события в одном формате
  dispatcher.py        # маршрутизация: текст, payload-команды, предикаты
  handlers.py          # вся бизнес-логика бота
  keyboards.py         # reply/inline клавиатуры
  vk_api.py            # единственный клиент API ВК
  transports/
    longpoll.py        # Bots LongPoll: groups.getLongPollServer + a_check
    callback.py        # aiohttp-сервер Callback API
tests/
  test_dispatcher.py   # тесты без токена и сети
```

Ключевая идея: транспорт только превращает событие ВК в `Update` и зовёт
`dispatcher.dispatch(...)`. Хендлеры ничего не знают про LongPoll/Callback.

## Быстрый старт

```bash
cd projects/vk-bot
python -m venv .venv
source .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # заполнить VK_TOKEN и VK_GROUP_ID
python -m bot                      # по умолчанию LongPoll
```

Тесты (без токена, без сети):

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Где взять настройки

1. Создайте сообщество ВК → **Управление** → **Работа с API**.
2. **Ключи доступа** → создайте ключ с правами «Управление сообществом» и
   «Сообщения сообщества». Это `VK_TOKEN`.
3. **ID сообщества** — числовой id (`VK_GROUP_ID`, без минуса).
4. **Сообщения сообщества** → включите сообщения.
5. LongPoll: **Работа с API → Long Poll API** → включите и отметьте событие
   `message_new`. Для кнопок добавьте `message_event` (только Callback API).

## LongPoll

```bash
python -m bot --transport longpoll
```

Ничего дополнительно настраивать не нужно: бот сам получает `server/key/ts`
и переподключается при `failed: 1/2/3`.

## Callback API

Нужен публичный HTTPS-адрес. Локально удобно через туннель:

```bash
ngrok http 8080
# или: cloudflared tunnel --url http://localhost:8080
```

В сообществе: **Работа с API → Callback API → Настройки сервера**:

- URL: `https://<ваш-домен>/vk/callback`
- Строка подтверждения — скопируйте её в `.env` как `VK_CONFIRMATION_CODE`
  (сервер ответит на событие `confirmation`)
- Секретный ключ — в `.env` как `VK_SECRET_KEY` (сравнивается с полем `secret`)
- Типы событий: `message_new`, `message_event`

```bash
python -m bot --transport callback
```

Сервер отвечает ВК `ok` сразу, а обработку делает в фоновой задаче. Повторные
доставки отсекаются по `event_id`. Проверка живости: `GET /health`.

## Логи

По умолчанию терминал тихий: видны только запуск и ошибки. Технические
строки `httpx` с кодами 200 скрыты, входящие сообщения не логируются.

Для отладки: `LOG_HTTP=1` в `.env` покажет HTTP-запросы, `LOG_LEVEL=DEBUG`
добавит выбранные обработчики.

## Кнопки: два типа

| Тип | Где работает | Как приходит |
| --- | --- | --- |
| `text` (reply-клавиатура, `keyboard=`) | LongPoll и Callback | `message_new`, payload в `message.payload` |
| `callback` (inline, `inline=True`) | только Callback API | событие `message_event` |

Поэтому `build_dispatcher(inline_buttons=...)` переключает вид меню:
в LongPoll `/help` отдаёт reply-клавиатуру, в Callback API — inline с
`type: "callback"`. Нажатие `message_event` прогоняется через тот же
диспетчер, поэтому хендлеры для кнопок и текста общие.

В LongPoll reply-клавиатура приходит вместе с ответом на `/start` и `/help`;
следующие сообщения бота уходят без неё, и ВК скрывает кнопки. Если нужно,
чтобы клавиатура висела постоянно, прикладывайте её в хендлере явно:
`await ctx.reply("...", keyboard=main_keyboard())`.

Если хотите inline-кнопки и в LongPoll — используйте `type: "text"` внутри
inline-клавиатуры: они приходят обычным сообщением, но payload ВК для них
не гарантирует, поэтому надёжнее reply-клавиатура.

## Как добавить команду

```python
@dp.message(text=["/ping", "пинг"])
async def ping(ctx: Context) -> None:
    await ctx.reply("pong")
```

Кнопка с payload:

```python
from .keyboards import button, keyboard

@dp.message(cmd="click")
async def on_click(ctx: Context) -> None:
    await ctx.reply("Кнопку нажали")

reply_markup = keyboard([[button("Нажми", payload={"cmd": "click"}, color="primary")]])
```

Хендлер получает `Context`: `ctx.update` (текст, `peer_id`, `from_id`,
`payload`) и `ctx.reply(text, keyboard=..., attachment=..., reply_to=True)`.
Если ни один маршрут не совпал, вызывается `@dp.fallback`.

## Важные детали ВК

- `random_id` обязателен и уникален, иначе сообщения схлопываются — он уже
  генерируется в `VKAPI.send_message`.
- Отвечайте на `peer_id`, а не на `from_id`: в беседах это разные значения.
- Лимиты: ~20 сообщений/сек на сообщество, ~20 запросов/сек к API.
- LongPoll держит соединение до 25 секунд — это нормально, не таймаутьте его.
- Токен — только в `.env`, файл в `.gitignore`.

## Агент OpenCode

В `~/.config/opencode/agents/vk-bot-dev.md` лежит агент `vk-bot-dev`:
он знает эту архитектуру и правила VK API (LongPoll `failed`-коды,
`random_id`, лимиты, Callback-подтверждение, дедупликация `event_id`).

Использование: попросите основного агента «используй vk-bot-dev, чтобы …»
или переключитесь на него как на основной (`/agents` в TUI).

## Деплой (кратко)

Callback API за reverse-proxy (nginx/caddy) с HTTPS, процесс под systemd или
в Docker. Пример unit-файла:

```ini
[Unit]
Description=VK bot
After=network-online.target

[Service]
WorkingDirectory=/opt/vk-bot
EnvironmentFile=/opt/vk-bot/.env
ExecStart=/opt/vk-bot/.venv/bin/python -m bot --transport callback
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
