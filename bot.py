# bot.py — повна версія для Render (webhook + health), aiogram 3.22

import os, sys, asyncio, logging, importlib.util
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

# ===== ENV =====
BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_ID    = os.getenv("ADMIN_ID", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # напр.: https://universal-bot-live.onrender.com
PORT        = int(os.getenv("PORT", "10000"))
HOST        = "0.0.0.0"

if not BOT_TOKEN or not WEBHOOK_URL:
    raise SystemExit("BOT_TOKEN та WEBHOOK_URL обовʼязкові (Render → Environment).")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

# ===== aiogram =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== імпорт run_all з groups/easy_sources.py БЕЗ пакетів =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EASY_SOURCES_PATH = os.path.join(BASE_DIR, "groups", "easy_sources.py")
if not os.path.exists(EASY_SOURCES_PATH):
    raise SystemExit("Не знайдено groups/easy_sources.py")

spec = importlib.util.spec_from_file_location("easy_sources", EASY_SOURCES_PATH)
easy_sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(easy_sources)
run_all = easy_sources.run_all  # функція, яку ти вже використовуєш

# ===== ХЕЛПЕР форматування (просто й без превʼю) =====
def format_simple(results: list[dict]) -> str:
    if not results:
        return "⚠️ Новини за сьогодні/вчора не знайдено."
    lines = [f"✅ Результат:\nУнікальних новин: {len(results)}", ""]
    for i, n in enumerate(results, 1):
        title = n.get("title", "").strip()
        date  = n.get("date", "").strip() or "—"
        url   = n.get("url", "").strip()
        lines.append(f"{i}. {title} ({date})\n{url}\n")
    return "\n".join(lines).strip()

# ===== HANDLERS =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Вітаю! Я новинний бот.\n\n"
        "Команди:\n"
        "• /news_easy — свіжі новини (Epravda, Minfin)\n"
    )

@dp.message(Command("news_easy"))
async def cmd_news_easy(message: types.Message):
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10 секунд.")
    try:
        results = run_all()
        text = format_simple(results)

        # Розбивка по 4000 символів і без превʼю (щоб не тягнуло картинки)
        chunk = 4000
        for i in range(0, len(text), chunk):
            await message.answer(text[i:i+chunk], disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка під час збору новин: {e}")

# ===== AIOHTTP APP (для Render) =====
async def on_startup(app: web.Application):
    await bot.set_webhook(url=f"{WEBHOOK_URL}{WEBHOOK_PATH}")
    logging.info("Webhook встановлено: %s", f"{WEBHOOK_URL}{WEBHOOK_PATH}")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook(drop_pending_updates=True)

app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# /health — щоб швидко перевіряти, що сервіс живий
async def health(request):
    return web.json_response({"status": "alive"})
app.router.add_get("/health", health)

# Реєструємо webhook-роут
SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    web.run_app(app, host=HOST, port=PORT)