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

# ---------- Хелпери форматування ----------
def _group_by_source_section(items):
    grouped = {}
    for n in items:
        src = n.get("source", "unknown")
        sec = n.get("section", "root")
        key = (src, sec)
        grouped.setdefault(key, {"section_url": n.get("section_url",""), "items": []})
        grouped[key]["items"].append(n)
    return grouped

def _make_header_for_source(source: str, stats: dict) -> str:
    s = stats.get(source, {"raw": 0, "unique": 0})
    return (
        f"✅ {source} — результат:\n"
        f"Усього знайдено: {s['raw']} (з урахуванням дублів)\n"
        f"Унікальних новин: {s['unique']}\n\n"
    )

def _format_groups(grouped_for_source: dict) -> str:
    lines = []
    for (src, sec), payload in grouped_for_source.items():
        section_url = payload.get("section_url") or ""
        items = payload["items"]
        lines.append(f"Джерело: {section_url} — {len(items)} новин:")
        for i, n in enumerate(items, 1):
            title = n.get("title","—")
            date  = n.get("date","—")
            url   = n.get("url","")
            lines.append(f"{i}. {title} ({date})\n   {url}")
        lines.append("")  # порожній рядок між групами
    return "\n".join(lines).rstrip()

def _build_messages(data: dict, max_items_per_group: int | None = None) -> list[str]:
    # Групуємо
    items = data["items"]
    stats = data["stats"]
    grouped = _group_by_source_section(items)

    # Порядок виводу джерел
    sources_order = ["epravda", "minfin"]
    messages = []

    for src in sources_order:
        # Витягуємо групи цього джерела
        g_src = {k:v for k,v in grouped.items() if k[0] == src}
        if not g_src:
            continue

        # Зафіксуємо ліміт на групу (якщо треба)
        trimmed = {}
        for key, payload in g_src.items():
            lst = payload["items"]
            if max_items_per_group and len(lst) > max_items_per_group:
                lst = lst[:max_items_per_group]
            trimmed[key] = {"section_url": payload["section_url"], "items": lst}

        # Тіло
        header = _make_header_for_source(src, stats)
        body   = _format_groups(trimmed)
        full   = (header + body).strip()

        # Чанкуємо за 3800 символів по абзацах
        messages.extend(_chunk_text(full, limit=3800))
    return messages

def _chunk_text(text: str, limit: int = 3800) -> list[str]:
    parts = []
    current = []
    length = 0
    for para in text.split("\n\n"):
        add = (para + "\n\n")
        if length + len(add) > limit and current:
            parts.append("".join(current).rstrip())
            current, length = [], 0
        current.append(add)
        length += len(add)
    if current:
        parts.append("".join(current).rstrip())
    # Гарантія хоч чогось
    return parts or [text[:limit]]

# ---------- Команди ----------
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
        data = run_all()  # {"items": [...], "stats": {...}}
        msgs = _build_messages(data, max_items_per_group=None)  # повний вивід
        for m in msgs:
            await message.answer(m, disable_web_page_preview=True)
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