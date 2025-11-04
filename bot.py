# bot.py
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
from aiogram.types import Message, LinkPreviewOptions
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

# ⬇️ імпортуємо обидві збірки: звичайну і «тільки сьогодні»
try:
    from groups.easy_sources import run_all, run_all_today
except Exception:
    log.exception("Не вдалося імпортувати groups.easy_sources.*")
    raise

async def _safe_send_many(bot: Bot, chat_id: int, messages: List[str]):
    for m in messages:
        if len(m) <= 4096:
            await bot.send_message(
                chat_id,
                m,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            await asyncio.sleep(PAUSE_BETWEEN_MSGS_SEC)
            continue
        start = 0
        while start < len(m):
            chunk = m[start:start + MAX_CHARS_PER_MSG]
            await bot.send_message(
                chat_id,
                chunk,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
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
        "• /news_easy — Epravda + Minfin + CoinDesk (сьогодні+вчора; без превʼю)\n"
        "• /news_today — тільки за сьогодні (без превʼю)",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )

@dp.message(Command("news_easy"))
async def cmd_news_easy(message: Message):
    chat_id = message.chat.id
    try:
        await message.answer(
            "⏳ Збираю свіжі новини... Це може зайняти до 10–20 cекунд.",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception:
        pass

    try:
        blocks = await _maybe_await(run_all(today_only=False))
        if isinstance(blocks, str):
            blocks = [blocks]
        if isinstance(blocks, list) and all(isinstance(x, str) for x in blocks):
            for block in blocks:
                await _safe_send_many(bot, chat_id, [block])
            await bot.send_message(
                chat_id, "✅ Готово.", link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            return

        await bot.send_message(
            chat_id, "⚠️ Порожній результат.", link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        await bot.send_message(
            chat_id, "✅ Готово.", link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    except Exception as e:
        log.exception("Помилка у /news_easy: %s", e)
        try:
            await bot.send_message(
                chat_id,
                "⚠️ Сталася помилка під час формування списку новин.",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Exception:
            pass

@dp.message(Command("news_today"))
async def cmd_news_today(message: Message):
    chat_id = message.chat.id
    try:
        await message.answer(
            "⏳ Збираю новини за сьогодні... Це може зайняти до 10–20 cекунд.",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception:
        pass

    try:
        blocks = await _maybe_await(run_all_today())
        if isinstance(blocks, str):
            blocks = [blocks]
        if isinstance(blocks, list) and all(isinstance(x, str) for x in blocks):
            for block in blocks:
                await _safe_send_many(bot, chat_id, [block])
            await bot.send_message(
                chat_id, "✅ Готово.", link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            return

        await bot.send_message(
            chat_id, "⚠️ Порожній результат.", link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        await bot.send_message(
            chat_id, "✅ Готово.", link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    except Exception as e:
        log.exception("Помилка у /news_today: %s", e)
        try:
            await bot.send_message(
                chat_id,
                "⚠️ Сталася помилка під час формування списку новин.",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
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