import os
import asyncio
import logging
from collections import defaultdict
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from groups.easy_sources import run_all  # sync

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

BOT_TOKEN   = os.getenv("BOT_TOKEN",   "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "6680030792"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

TELEGRAM_HARD_LIMIT = 4096
CHUNK_LIMIT = 3000
MAX_PER_SOURCE = 8           # жорстка “кришка”
MAX_SOURCES = 2              # epravda + minfin
SEND_DELAY = 0.4
RETRY_LIMIT = 4

running_tasks: dict[int, asyncio.Task] = {}

def _safe(s): return s if s else "—"

def _chunk_text(text: str, limit: int = CHUNK_LIMIT):
    if len(text) <= limit:
        return [text]
    lines = text.splitlines(keepends=True)
    out, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) > limit:
            out.append(cur.rstrip())
            cur = ln
        else:
            cur += ln
    if cur.strip():
        out.append(cur.rstrip())
    return out or ["—"]

async def _send_with_retry(chat_id: int, text: str):
    tries = 0
    while True:
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except TelegramAPIError:
            tries += 1
            if tries >= RETRY_LIMIT:
                raise
            await asyncio.sleep(1.0)

async def _send_chunks(chat_id: int, text: str):
    chunks = _chunk_text(text, CHUNK_LIMIT)
    total = len(chunks)
    for i, ch in enumerate(chunks, 1):
        prefix = f"🧩 Блок {i}/{total}\n" if total > 1 else ""
        await _send_with_retry(chat_id, prefix + ch)
        await asyncio.sleep(SEND_DELAY)

def _format_blocks(results: list[dict]) -> list[str]:
    # нормалізація
    items = []
    for it in results or []:
        if not isinstance(it, dict):
            continue
        title = _safe(it.get("title"))
        url   = _safe(it.get("url"))
        date  = _safe(it.get("date"))
        src   = (it.get("source") or "").strip().lower()
        sec   = (it.get("section") or "").strip().lower()
        # дозволяємо лише ці джерела; якщо парсер не дав source — виведемо у “—”
        if src not in ("epravda", "minfin"):
            if "epravda.com.ua" in url:
                src = "epravda"
            elif "minfin.com.ua" in url:
                src = "minfin"
            else:
                continue
        items.append({"title": title, "url": url, "date": date, "source": src or "—", "section": sec or "—"})

    if not items:
        return ["⚠️ Новини за сьогодні/вчора не знайдено."]

    # групування: source -> section -> list
    from collections import defaultdict as dd
    by_src: dict[str, dict[str, list[dict]]] = dd(lambda: dd(list))
    for it in items:
        by_src[it["source"]][it["section"]].append(it)

    blocks = []
    for src in ["epravda", "minfin"][:MAX_SOURCES]:
        if src not in by_src:
            continue
        total_src = sum(len(v) for v in by_src[src].values())
        lines = [f"✅ {src} — показую {MAX_PER_SOURCE} з {total_src}\n"]
        # секції за спаданням розміру
        count = 0
        for section, arr in sorted(by_src[src].items(), key=lambda kv: -len(kv[1])):
            if count >= MAX_PER_SOURCE:
                break
            remain = MAX_PER_SOURCE - count
            take = arr[:remain]
            lines.append(f"Джерело: {src} | секція: {section} — {len(arr)} новин:")
            for i, n in enumerate(take, 1):
                lines.append(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
                count += 1
            lines.append("")
        txt = "\n".join(lines).strip()
        blocks.append(txt if txt else f"✅ {src}: нічого показати")

    return blocks or ["⚠️ Порожньо."]

async def _do_news(chat_id: int):
    try:
        results = await asyncio.to_thread(run_all)          # не блокуємо loop
        blocks = _format_blocks(results)                    # 1–2 компактні блоки
        for b in blocks:
            await _send_chunks(chat_id, b)
        await _send_with_retry(chat_id, "✅ Готово.")
    except Exception as e:
        log.exception("news task failed")
        try:
            await _send_with_retry(chat_id, f"❌ Помилка: {e}")
        except Exception:
            pass

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (згруповано, без превʼю, з лімітами)"
    )

@dp.message(Command("news_easy"))
async def news_easy_cmd(message: types.Message):
    chat_id = message.chat.id
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10–20 секунд.")

    old = running_tasks.get(chat_id)
    if old and not old.done():
        await message.answer("🟡 Запит уже виконується. Дочекайся завершення.")
        return

    task = asyncio.create_task(_do_news(chat_id))
    running_tasks[chat_id] = task
    def _cleanup(_):
        running_tasks.pop(chat_id, None)
    task.add_done_callback(_cleanup)

async def handle_health(_: web.Request):
    return web.json_response({"status": "alive"})

async def handle_webhook(request: web.Request):
    data = await request.json()
    await dp.feed_webhook_update(bot, data)  # швидко повертаємо OK
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