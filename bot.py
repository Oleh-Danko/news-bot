# bot.py
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

# ---------- Форматування під затверджену стилістику ----------
MAX_TG = 4096
SPLIT_SAFE = 3800  # запас, щоб не врізати по середині номера/URL

def _format_source_block(source_name: str, data: dict) -> list[str]:
    """
    Повертає список текстових блоків (щоб не перевищити ліміти Telegram).
    Кожен блок починається з шапки:
      ✅ <source> — результат:
      Усього знайдено: N (з урахуванням дублів)
      Унікальних новин: M
    Далі підблоки по секціях:
      Джерело: <URL секції> — <K> новин:
        1. Назва (YYYY-MM-DD)
           URL
    """
    header = (
        f"✅ {source_name} — результат:\n"
        f"Усього знайдено: {data['raw_total']} (з урахуванням дублів)\n"
        f"Унікальних новин: {data['unique_total']}\n\n"
    )

    blocks = []
    cur = header
    for sec in data.get("sections", []):
        sec_head = f"Джерело: {sec['url']} — {len(sec['items'])} новин:\n"
        sec_body_lines = []
        for i, n in enumerate(sec["items"], 1):
            title = n.get("title", "—")
            date  = n.get("date", "—")
            url   = n.get("url", "")
            sec_body_lines.append(f"{i}. {title} ({date})\n   {url}\n")
        sec_text = sec_head + "\n".join(sec_body_lines) + "\n"

        # якщо секція не вміщується в поточний блок — закриваємо блок і починаємо новий з тією ж шапкою
        if len(cur) + len(sec_text) > SPLIT_SAFE:
            blocks.append(cur.rstrip())
            cur = header + sec_text
        else:
            cur += sec_text

    if cur.strip():
        blocks.append(cur.rstrip())
    return blocks

def format_grouped_payload(grouped: dict) -> list[str]:
    # Порядок виводу джерел фіксуємо: epravda → minfin
    order = ["epravda", "minfin"]
    out_blocks = []
    for key in order:
        if key in grouped and grouped[key]["unique_total"] > 0:
            out_blocks.extend(_format_source_block(key, grouped[key]))
    return out_blocks if out_blocks else ["⚠️ Новини не знайдено."]

# ---------- Хендлери ----------
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
        grouped = run_all()
        blocks = format_grouped_payload(grouped)
        for b in blocks:
            await message.answer(b, disable_web_page_preview=True)
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