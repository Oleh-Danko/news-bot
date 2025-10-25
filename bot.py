import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from live_parser import fetch_epravda_news

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("news-bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL обов’язкові!")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("👋 Привіт! Надішли /news щоб отримати останні новини з Epravda.")

@dp.message(Command("news"))
async def news(message: Message):
    await message.answer("⏳ Збираю актуальні новини прямо зараз…")
    items = await fetch_epravda_news()
    if not items:
        await message.answer("⚠️ Не вдалося отримати новини. Спробуй ще раз пізніше.")
        return
    text = "<b>Epravda (Finances)</b>\n"
    for n in items[:20]:
        desc = f" — {n['description']}" if n.get("description") else ""
        text += f"• <a href='{n['link']}'>{n['title']}</a>{desc}\n"
    await message.answer(text, disable_web_page_preview=False)

async def handle_health(request):
    return web.Response(text="OK", status=200)

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    log.info("Webhook set ✅")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.router.add_get("/", handle_health)
    app.router.add_get("/healthz", handle_health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    port = int(os.environ.get("PORT", 10000))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()