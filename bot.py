import os
import logging
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
CHUNK_LIMIT = 3500           # запас до 4096
PER_SECTION_LIMIT = 12       # не більше N пунктів на секцію
PER_SOURCE_LIMIT  = 60       # “стеля” на джерело (щоб точно не впертися в ліміт)

def _safe_str(v):
    return "" if v is None else str(v).strip()

def _sanitize_item(d: dict) -> dict:
    """Гарантовано повертає словник з потрібними ключами або {} якщо нема URL."""
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

def _format_block(header: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    return f"{header}\n{body}".strip()

async def _send_chunks(message: types.Message, text: str):
    """Розбиває довгі відповіді на безпечні шматки й шле по черзі."""
    if not text:
        return
    # розбивка по абзацах з запасом
    parts = text.split("\n\n")
    buf = ""
    for p in parts:
        add = (p + "\n\n")
        if len(buf) + len(add) > CHUNK_LIMIT:
            await message.answer(buf.rstrip(), disable_web_page_preview=True)
            buf = add
        else:
            buf += add
    if buf.strip():
        await message.answer(buf.rstrip(), disable_web_page_preview=True)

def _build_text(results: list[dict]) -> str:
    """
    Групуємо за source -> section, ріжемо за лімітами,
    формуємо один великий текст (далі його розіб’є _send_chunks).
    """
    groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for raw in results:
        item = _sanitize_item(raw if isinstance(raw, dict) else {})
        if not item:
            continue
        src = item["source"] or "epravda"
        sec = item["section"] or ""
        groups[src][sec].append(item)

    # формуємо тексти по джерелах
    out_blocks: list[str] = []
    for src in ("epravda", "minfin"):  # стабільний порядок
        if src not in groups:
            continue
        # плоский список для ліміту PER_SOURCE_LIMIT
        flat: list[dict] = []
        for sec, items in groups[src].items():
            flat.extend(items)
        if len(flat) > PER_SOURCE_LIMIT:
            # підріжемо найстарші хвости
            flat = flat[:PER_SOURCE_LIMIT]
            # перезберемо назад у секції по зрізаному списку
            sec_map: dict[str, list[dict]] = defaultdict(list)
            for it in flat:
                sec_map[it["section"]].append(it)
            groups[src] = sec_map

        total_found = sum(len(v) for v in groups[src].values())
        total_unique = total_found  # дублікати вже прибрано в run_all()

        header = f"✅ {src} — результат:\nУсього знайдено: {total_found} (з урахуванням дублів)\nУнікальних новин: {total_unique}"
        lines: list[str] = [header, ""]

        # секції у стабільному порядку
        for sec_name in sorted(groups[src].keys()):
            sec_items = groups[src][sec_name][:PER_SECTION_LIMIT]
            if not sec_items:
                continue
            sec_link = sec_items[0].get("section_url") or sec_name or "-"
            lines.append(f"Джерело: {sec_link} — {len(sec_items)} новин:")
            for i, n in enumerate(sec_items, 1):
                t = n["title"] or "—"
                d = n["date"] or "—"
                u = n["url"]
                lines.append(f"{i}. {t} ({d})\n   {u}")
            lines.append("")  # порожній рядок між секціями

        out_blocks.append("\n".join(lines).rstrip())

    return "\n\n".join(b for b in out_blocks if b).strip()

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
        text = _build_text(results)
        await _send_chunks(message, text)
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