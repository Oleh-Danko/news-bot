import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ==== ENV ====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # напр. https://universal-bot-live.onrender.com
PORT = int(os.environ.get("PORT", "8080"))

if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("BOT_TOKEN або WEBHOOK_URL не задані в env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ====== ІМПОРТ ПАРСЕРА ======
from groups.easy_sources import run_all  # твій існуючий парсер

def format_news(items):
    if not items:
        return "⚠️ Новини за сьогодні/вчора не знайдено."
    # Групуємо за source та category (як ти просив раніше)
    from collections import defaultdict
    buckets = defaultdict(list)
    for it in items:
        src = it.get("source", "unknown")
        cat = it.get("category", "")
        key = (src, cat)
        buckets[key].append(it)

    out = []
    for (src, cat), lst in buckets.items():
        cat_part = f" — {cat}" if cat else ""
        out.append(f"✅ {src}{cat_part}: {len(lst)} новин:")
        for i, n in enumerate(lst, 1):
            title = n.get("title","").strip()
            date = n.get("date","—")
            url = n.get("url","")
            out.append(f"{i}. {title} ({date})\n{url}")
        out.append("")  # порожній рядок між блоками
    return "\n".join(out).strip()

# ====== ХЕНДЛЕРИ ======
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привіт! Команда: /news — отримаєш новини з Epravda/Minfin у потрібному форматі.")

@dp.message(Command("news"))
async def cmd_news(message: types.Message):
    await message.answer("⏳ Збираю новини…")
    try:
        results = run_all()
        text = format_news(results)
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for p in parts:
                await message.answer(p, disable_web_page_preview=True)
        else:
            await message.answer(text, disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"❌ Помилка під час збору: {e}")

# ====== WEBHOOK АПКА ======
async def on_startup(app: web.Application):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()

async def healthz(request):
    return web.json_response({"status": "alive"})

def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", healthz)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, on_startup=[on_startup], on_shutdown=[on_shutdown])
    return app

if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=PORT)