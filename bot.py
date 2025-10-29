import os
import asyncio
import logging
import inspect
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()

assert BOT_TOKEN, "BOT_TOKEN is required"
assert WEBHOOK_URL, "WEBHOOK_URL is required"

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
MAX_CHARS_PER_MSG = 3800
PAUSE_BETWEEN_MSGS_SEC = 0.06

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("news-bot")

try:
    from groups.easy_sources import run_all as parse_all_sources
except Exception:
    log.exception("Не вдалося імпортувати groups.easy_sources.run_all()")
    raise

async def _safe_send_many(bot: Bot, chat_id: int, messages: List[str]):
    for m in messages:
        # Дрібна безпечна нарізка по 3800, щоб зберегти ТЕКСТ БЕЗ ЗМІН
        if len(m) <= 4096:
            await bot.send_message(chat_id, m)
            await asyncio.sleep(PAUSE_BETWEEN_MSGS_SEC)
            continue
        start = 0
        while start < len(m):
            chunk = m[start:start + MAX_CHARS_PER_MSG]
            await bot.send_message(chat_id, chunk)
            start += MAX_CHARS_PER_MSG
            await asyncio.sleep(PAUSE_BETWEEN_MSGS_SEC)

async def _maybe_await(x):
    return await x if inspect.isawaitable(x) else x

dp = Dispatcher()
bot = Bot(BOT_TOKEN, parse_mode=None)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (унікальні, згруповані; без превʼю)"
    )

@dp.message(Command("news_easy"))
async def cmd_news_easy(message: Message):
    chat_id = message.chat.id
    try:
        await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10–20 cекунд.")
    except Exception:
        pass

    try:
        raw = await _maybe_await(parse_all_sources())
        # Якщо парсери повертають готові текстові блоки — відправляємо «як є»
        if isinstance(raw, str):
            await _safe_send_many(bot, chat_id, [raw])
            await bot.send_message(chat_id, "✅ Готово.")
            return
        if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
            # ПО ЧЕРЗІ: спочатку epravda, потім minfin — нічого не змішуємо
            for block in raw:
                await _safe_send_many(bot, chat_id, [block])
            await bot.send_message(chat_id, "✅ Готово.")
            return

        # Якщо колись повернеться структура — запасний сценарій (не використовується зараз)
        await bot.send_message(chat_id, "⚠️ Порожній результат.")
        await bot.send_message(chat_id, "✅ Готово.")

    except Exception as e:
        log.exception("Помилка у /news_easy: %s", e)
        try:
            await bot.send_message(chat_id, "⚠️ Сталася помилка під час формування списку новин.")
        except Exception:
            pass

async def health(_):
    return web.json_response({"status": "alive"})

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app

app = build_app()

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))