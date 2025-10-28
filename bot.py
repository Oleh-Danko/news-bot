cat > bot.py << 'PY'
import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ====== Налаштування ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE")
WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Імпорти парсерів (після створення dp!)
from groups.easy_sources import run_all, format_grouped

# ====== Хендлери ======
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привіт! Надішли /news — отримаєш актуальні новини "
        "з Економічної Правди (Фінанси) та Minfin."
    )

@dp.message(Command("news"))
@dp.message(Command("news_easy"))
async def cmd_news(message: types.Message):
    await message.answer("⏳ Збираю новини…")
    try:
        results = run_all()
        if not results:
            await message.answer("⚠️ Новини не знайдені.")
            return

        text = format_grouped(results)

        # Розбиваємо на частини, щоб не впертись у 4096 символів
        CHUNK = 3800
        parts = [text[i:i+CHUNK] for i in range(0, len(text), CHUNK)]
        for part in parts:
            await message.answer(part, disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

# ====== AIOHTTP вебсервер + вебхук ======
async def on_startup(app: web.Application):
    webhook_url = f"{WEBHOOK_BASE}/webhook/{BOT_TOKEN}"
    await bot.set_webhook(webhook_url)
    log.info(f"Webhook встановлено: {webhook_url}")

async def on_shutdown(app: web.Application):
    log.info("🔻 Deleting webhook & closing session…")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    finally:
        await bot.session.close()
    log.info("✅ Shutdown complete")

async def health(request):
    return web.json_response({"status": "alive"})

# Створення app і маршрути
app = web.Application()
app.router.add_get("/health", health)

SimpleRequestHandler(dp, bot).register(app, path=f"/webhook/{BOT_TOKEN}")
setup_application(app, on_startup, on_shutdown)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=PORT)
PY