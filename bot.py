import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groups.easy_sources import run_all

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

BOT_TOKEN   = os.getenv("BOT_TOKEN",   "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "6680030792"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (унікальні, без прев’ю)"
    )

@dp.message(Command("news_easy"))
async def news_easy_cmd(message: types.Message):
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10 секунд.")
    try:
        results = run_all()
        if not results:
            await message.answer("⚠️ Новини за сьогодні та вчора не знайдено.")
            return

        lines = ["✅ Результат:", f"Унікальних новин: {len(results)}", ""]
        for i, n in enumerate(results, 1):
            title = n.get("title", "—")
            date  = n.get("date", "—")
            url   = n.get("url", "")
            lines.append(f"{i}. {title} ({date})\n{url}\n")
        text = "\n".join(lines)

        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await message.answer(text[i:i+4000], disable_web_page_preview=True)
        else:
            await message.answer(text, disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка під час збору новин: {e}")

# ---------- AIOHTTP + Webhook ----------
async def handle_health(request: web.Request):
    return web.json_response({"status": "alive"})

async def handle_webhook(request: web.Request):
    data = await request.json()
    await dp.feed_webhook_update(bot, data)
    return web.Response(text="OK")

async def on_startup(app: web.Application):
    url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
    await bot.set_webhook(url, drop_pending_updates=True)
    log.info(f"Webhook встановлено: {url}")

async def on_shutdown(app: web.Application):
    log.info("🔻 Deleting webhook & closing session…")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    finally:
        await bot.session.close()
    log.info("✅ Shutdown complete")

def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post(f"/webhook/{BOT_TOKEN}", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("RENDER_PORT", "10000")))
    web.run_app(make_app(), host="0.0.0.0", port=port)
