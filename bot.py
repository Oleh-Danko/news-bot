import os
import logging
import asyncio
from collections import defaultdict
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

BOT_TOKEN   = os.getenv("BOT_TOKEN",   "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "6680030792"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

CHUNK_LIMIT = 3000
PER_SECTION_LIMIT = 12
PER_SOURCE_LIMIT  = 60

def _safe_str(v): return "" if v is None else str(v).strip()

def _sanitize_item(d: dict) -> dict:
    if not isinstance(d, dict): return {}
    url = _safe_str(d.get("url"))
    if not url: return {}
    return {
        "title": _safe_str(d.get("title") or "—"),
        "date": _safe_str(d.get("date") or "—"),
        "url": url,
        "source": _safe_str(d.get("source") or "epravda").lower(),
        "section": _safe_str(d.get("section") or ""),
        "section_url": _safe_str(d.get("section_url") or ""),
    }

def _format_sources(results: list[dict]) -> str:
    groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for raw in results:
        it = _sanitize_item(raw)
        if it: groups[it["source"] or "epravda"][it["section"] or ""].append(it)

    blocks: list[str] = []
    for src in ("epravda", "minfin"):
        if src not in groups: continue

        flat = [it for sec in groups[src].values() for it in sec]
        if len(flat) > PER_SOURCE_LIMIT:
            flat = flat[:PER_SOURCE_LIMIT]
            sec_map: dict[str, list[dict]] = defaultdict(list)
            for it in flat: sec_map[it.get("section","")].append(it)
            groups[src] = sec_map

        total_found = sum(len(v) for v in groups[src].values())
        total_unique = total_found

        lines = [
            f"✅ {src} — результат:",
            f"Усього знайдено: {total_found} (з урахуванням дублів)",
            f"Унікальних новин: {total_unique}",
            ""
        ]
        for sec_name in sorted(groups[src].keys()):
            sec_items = groups[src][sec_name][:PER_SECTION_LIMIT]
            if not sec_items: continue
            sec_link = sec_items[0].get("section_url") or (sec_name or "-")
            lines.append(f"Джерело: {sec_link} — {len(sec_items)} новин:")
            for i, n in enumerate(sec_items, 1):
                t = n.get("title") or "—"
                d = n.get("date") or "—"
                u = n.get("url") or ""
                lines.append(f"{i}. {t} ({d})")
                lines.append(f"   {u}")
            lines.append("")
        blocks.append("\n".join(lines).rstrip())

    return "\n\n".join([b for b in blocks if b]).strip()

def _hard_wrap(s: str, limit: int):
    return [s[i:i+limit] for i in range(0, len(s), limit)] if len(s) > limit else [s]

def _chunk_iter(text: str, limit: int):
    if not text: return
    for para in text.split("\n\n"):
        if not para: continue
        if len(para) <= limit:
            yield para; continue
        current = ""
        for raw in para.split("\n"):
            for piece in _hard_wrap(raw, limit):
                add = piece + "\n"
                if len(current) + len(add) > limit:
                    if current.strip(): yield current.rstrip()
                    current = add
                else:
                    current += add
        if current.strip(): yield current.rstrip()

async def _send_long_chat(chat_id: int, text: str):
    for chunk in _chunk_iter(text, CHUNK_LIMIT):
        await bot.send_message(chat_id, chunk, disable_web_page_preview=True)
        await asyncio.sleep(0)

async def _run_parse(func, timeout_s: float, name: str):
    async def _wrapped(): return await asyncio.to_thread(func)
    try:
        return await asyncio.wait_for(_wrapped(), timeout=timeout_s)
    except asyncio.TimeoutError:
        log.warning(f"{name}: timeout {timeout_s}s"); return []
    except Exception as e:
        log.warning(f"{name}: failed: {e}"); return []

async def collect_news_concurrent() -> list[dict]:
    # Паралельно, з індивідуальними таймаутами
    e_task = asyncio.create_task(_run_parse(parse_epravda, 8, "epravda"))
    m_task = asyncio.create_task(_run_parse(parse_minfin,  8, "minfin"))
    epravda, minfin = await asyncio.gather(e_task, m_task, return_exceptions=False)

    seen, out = set(), []
    for it in (epravda or []) + (minfin or []):
        if not isinstance(it, dict): continue
        url = (it.get("url") or "").strip()
        if not url or url in seen: continue
        seen.add(url); out.append(it)
    return out

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("👋 Привіт! Доступні команди:\n• /news_easy — Epravda + Minfin (унікальні, без прев’ю)")

@dp.message(Command("news_easy"))
async def news_easy_cmd(message: types.Message):
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10 секунд.")
    chat_id = message.chat.id
    async def _job():
        try:
            results = await collect_news_concurrent()
            if not results:
                await bot.send_message(chat_id, "⚠️ Джерела не відповіли вчасно або новин нема.")
                return
            text = _format_sources(results)
            await _send_long_chat(chat_id, text)
        except Exception as e:
            await bot.send_message(chat_id, f"❌ Помилка під час збору новин: {e}")
    asyncio.create_task(_job())  # не блокуємо вебхук

async def handle_health(request: web.Request):
    return web.json_response({"status": "alive"})

async def handle_webhook(request: web.Request):
    data = await request.json()
    # миттєвий ACK вебхуку, обробку робимо у фоні
    asyncio.create_task(dp.feed_webhook_update(bot, data))
    return web.Response(text="OK")

async def on_startup(app: web.Application):
    url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
    await bot.set_webhook(url, drop_pending_updates=True)
    log.info(f"Webhook встановлено: {url}")

async def on_shutdown(app: web.Application):
    log.info("🔻 Deleting webhook & closing session…")
    try: await bot.delete_webhook(drop_pending_updates=True)
    finally: await bot.session.close()
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