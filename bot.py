import os
import logging
import asyncio
from collections import defaultdict
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groups.easy_sources import run_all

# --------- базові налаштування ---------
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

BOT_TOKEN   = os.getenv("BOT_TOKEN",   "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "6680030792"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# --------- хелпери форматування/відправки ---------
CHUNK_LIMIT = 3000           # запас проти 4096
PER_SECTION_LIMIT = 12       # максимум пунктів на секцію
PER_SOURCE_LIMIT  = 60       # максимум карток з одного джерела

def _safe_str(v):
    return "" if v is None else str(v).strip()

def _sanitize_item(d: dict) -> dict:
    """Гарантовано повертає словник з потрібними ключами або {} якщо нема URL."""
    if not isinstance(d, dict):
        return {}
    url = _safe_str(d.get("url"))
    if not url:
        return {}
    return {
        "title":  _safe_str(d.get("title") or "—"),
        "date":   _safe_str(d.get("date")  or "—"),
        "url":    url,
        "source": _safe_str(d.get("source") or "epravda").lower(),
        "section":_safe_str(d.get("section") or ""),
        "section_url": _safe_str(d.get("section_url") or ""),
    }

def _format_sources(results: list[dict]) -> str:
    """Групуємо за source -> section, ріжемо за лімітами та формуємо великий текст."""
    groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for raw in results:
        item = _sanitize_item(raw)
        if not item:
            continue
        groups[item["source"] or "epravda"][item["section"] or ""].append(item)

    blocks: list[str] = []
    for src in ("epravda", "minfin"):  # стабільний порядок
        if src not in groups:
            continue

        # плоский зріз PER_SOURCE_LIMIT
        flat: list[dict] = []
        for sec_items in groups[src].values():
            flat.extend(sec_items)
        if len(flat) > PER_SOURCE_LIMIT:
            flat = flat[:PER_SOURCE_LIMIT]
            sec_map: dict[str, list[dict]] = defaultdict(list)
            for it in flat:
                sec_map[it.get("section","")].append(it)
            groups[src] = sec_map

        total_found = sum(len(v) for v in groups[src].values())
        total_unique = total_found

        lines: list[str] = []
        lines.append(f"✅ {src} — результат:")
        lines.append(f"Усього знайдено: {total_found} (з урахуванням дублів)")
        lines.append(f"Унікальних новин: {total_unique}")
        lines.append("")

        for sec_name in sorted(groups[src].keys()):
            sec_items = groups[src][sec_name][:PER_SECTION_LIMIT]
            if not sec_items:
                continue
            sec_link = sec_items[0].get("section_url") or (sec_name or "-")
            lines.append(f"Джерело: {sec_link} — {len(sec_items)} новин:")
            for i, n in enumerate(sec_items, 1):
                t = n.get("title") or "—"
                d = n.get("date") or "—"
                u = n.get("url") or ""
                lines.append(f"{i}. {t} ({d})")
                lines.append(f"   {u}")
            lines.append("")  # порожній між секціями

        blocks.append("\n".join(lines).rstrip())

    return "\n\n".join([b for b in blocks if b]).strip()

def _hard_wrap(line: str, limit: int):
    """Жорстко ріже один наддовгий рядок на шматки ≤ limit."""
    if len(line) <= limit:
        return [line]
    out = []
    s = 0
    while s < len(line):
        out.append(line[s:s+limit])
        s += limit
    return out

def _chunk_iter(text: str, limit: int):
    """
    Надійний чанкiнг:
    1) по подвійних перенесеннях (абзаци),
    2) якщо абзац довгий — по рядках,
    3) якщо рядок довгий — жорстке обрізання.
    """
    if not text:
        return
    for para in text.split("\n\n"):
        if not para:
            continue
        if len(para) <= limit:
            yield para
            continue

        # розкладемо абзац на рядки
        current = ""
        for raw_line in para.split("\n"):
            # якщо один рядок довший за limit — поріжемо його
            for piece in _hard_wrap(raw_line, limit):
                add = (piece + "\n")
                if len(current) + len(add) > limit:
                    if current.strip():
                        yield current.rstrip()
                    current = add
                else:
                    current += add
        if current.strip():
            yield current.rstrip()

async def _send_long(message: types.Message, text: str):
    for chunk in _chunk_iter(text, CHUNK_LIMIT):
        await message.answer(chunk, disable_web_page_preview=True)
        await asyncio.sleep(0)

# --------- хендлери ---------
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
            await message.answer("⚠️ Новини не знайдено.")
            return
        text = _format_sources(results)
        await _send_long(message, text)
    except Exception as e:
        await message.answer(f"❌ Помилка під час збору новин: {e}")

# --------- AIOHTTP + Webhook ---------
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