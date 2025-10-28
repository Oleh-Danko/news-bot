import os
import logging
from urllib.parse import urlparse
from collections import defaultdict

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

# ----------------------- Форматування під вимогу -----------------------
SECTION_LIMIT = 10      # скільки пунктів показувати на одну «Джерело: …»
CHUNK_LIMIT   = 3900    # безпечний ліміт символів для повідомлення TG (max 4096)

def _origin(url: str) -> str:
    u = urlparse(url)
    host = u.netloc.replace("www.", "")
    return f"{u.scheme}://{host}"

def _section_url(url: str) -> str:
    """Дає кореневу URL секції для групування у стилі:
    'Джерело: https://epravda.com.ua/finances — N новин'
    """
    u = urlparse(url)
    host = u.netloc.replace("www.", "")
    parts = [p for p in u.path.split("/") if p]

    if "epravda.com.ua" in host:
        sec = parts[0] if parts else ""
        return f"{u.scheme}://{host}/{sec}" if sec else f"{u.scheme}://{host}"

    if "minfin.com.ua" in host:
        # Вони мають як статті за датою (/ua/2025/10/28/...), так і рубрики (/ua/news/improvement/)
        if parts and parts[0] == "ua":
            if len(parts) >= 3 and parts[1].isalpha() and parts[2].isalpha():
                sec = "/".join(parts[:3])          # ua/news/improvement
            elif len(parts) >= 2 and parts[1].isalpha():
                sec = "/".join(parts[:2])          # ua/news
            else:
                sec = "ua"                          # просто корінь /ua
        else:
            sec = parts[0] if parts else ""
        return f"{u.scheme}://{host}/{sec}".rstrip("/")

    # дефолт
    return f"{u.scheme}://{host}"

def _group(items: list[dict]) -> dict:
    grouped = defaultdict(lambda: defaultdict(list))  # source -> section_url -> [items]
    for n in items:
        url = n.get("url") or ""
        if not url:
            continue
        src = urlparse(url).netloc.replace("www.", "")
        sec = _section_url(url)
        grouped[src][sec].append(n)
    return grouped

def _build_source_text(src: str, sections: dict[str, list[dict]]) -> str:
    total_unique = sum(len(v) for v in sections.values())
    lines = [
        f"✅ {src.split('.')[0]} — результат:",
        f"Усього знайдено: {total_unique} (з урахуванням дублів)",
        f"Унікальних новин: {total_unique}",
        ""
    ]
    for sec_url, items in sections.items():
        show = items[:SECTION_LIMIT]
        lines.append(f"Джерело: {sec_url} — {len(show)} новин:")
        for i, n in enumerate(show, 1):
            title = n.get("title", "—")
            date  = n.get("date", "—")
            url   = n.get("url", "")
            lines.append(f"{i}. {title} ({date})\n   {url}")
        lines.append("")
    return "\n".join(lines).strip()

def _split_chunks(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    # спочатку ділимо «абзацами»
    parts = text.split("\n\n")
    chunks, buf = [], ""
    for p in parts:
        add = (p if buf == "" else "\n\n" + p)
        if len(buf) + len(add) <= limit:
            buf += add
        else:
            if buf:
                chunks.append(buf)
            # якщо один абзац > ліміту, ріжемо його грубо
            while len(p) > limit:
                chunks.append(p[:limit])
                p = p[limit:]
            buf = p
    if buf:
        chunks.append(buf)
    return chunks

async def _send_long(message: types.Message, text: str):
    for part in _split_chunks(text):
        await message.answer(part, disable_web_page_preview=True)

# ---------------------------- Хендлери ---------------------------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (групування за секціями, без прев’ю)"
    )

@dp.message(Command("news_easy"))
async def news_easy_cmd(message: types.Message):
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10 секунд.")
    try:
        results = run_all()
        if not results:
            await message.answer("⚠️ Немає новин.")
            return

        grouped = _group(results)
        # надсилаємо окремим блоком по кожному джерелу
        for src in ("epravda.com.ua", "minfin.com.ua"):
            if src in grouped:
                text = _build_source_text(src, grouped[src])
                await _send_long(message, text)

    except Exception as e:
        await message.answer(f"❌ Помилка під час збору новин: {e}")

# -------------------------- AIOHTTP + Webhook --------------------------
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