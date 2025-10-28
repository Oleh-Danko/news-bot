import os
import re
import asyncio
import logging
from typing import Any, Iterable
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

from groups.easy_sources import run_all  # синхронний збір парсерами

# ── Логування ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

# ── ENV / Константи ────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN",   "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "6680030792"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

TELEGRAM_HARD_LIMIT = 4096
CHUNK_LIMIT   = 3000           # запас від ліміту Telegram
MAX_PER_SRC   = 8              # максимум пунктів на джерело
MAX_SOURCES   = 2              # epravda + minfin
SEND_DELAY    = 0.35           # антифлуд
RETRY_LIMIT   = 4

running_tasks: dict[int, asyncio.Task] = {}

# ── Утиліти ────────────────────────────────────────────────────────────────────
def _safe(s: Any, default: str = "—") -> str:
    if not s:
        return default
    return str(s).strip()

def _domain_from_url(u: str) -> str:
    m = re.search(r"https?://([^/]+)/?", u or "", flags=re.I)
    return (m.group(1) if m else "").lower()

def _chunk_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    lines = text.splitlines(keepends=True)
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) > limit:
            if cur.strip():
                chunks.append(cur.rstrip())
            cur = ln
        else:
            cur += ln
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks or ["—"]

async def _send_with_retry(chat_id: int, text: str):
    tries = 0
    while True:
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=True)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.6)
        except TelegramAPIError as e:
            tries += 1
            if tries >= RETRY_LIMIT:
                raise
            await asyncio.sleep(1.2)

async def _send_chunks(chat_id: int, text: str):
    parts = _chunk_text(text, CHUNK_LIMIT)
    n = len(parts)
    for i, p in enumerate(parts, 1):
        prefix = f"Блок {i}/{n}\n" if n > 1 else ""
        await _send_with_retry(chat_id, prefix + p)
        await asyncio.sleep(SEND_DELAY)

# ── Нормалізація результатів парсерів ─────────────────────────────────────────
_KEY_ALIASES = {
    "title":   ("title", "name", "headline", "text"),
    "url":     ("url", "link", "href"),
    "date":    ("date", "published", "time", "dt"),
    "source":  ("source", "src", "site", "origin"),
    "section": ("section", "category", "sec", "tag", "path"),
}

def _get_first(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k]:
            return d[k]
    return None

def _normalize_item(it: Any) -> dict | None:
    """Повертає уніфікований елемент або None, якщо не вдалось."""
    if not isinstance(it, dict):
        return None

    title = _safe(_get_first(it, _KEY_ALIASES["title"]))
    url   = _safe(_get_first(it, _KEY_ALIASES["url"]))
    date  = _safe(_get_first(it, _KEY_ALIASES["date"]))
    src   = _safe(_get_first(it, _KEY_ALIASES["source"]))
    sec   = _safe(_get_first(it, _KEY_ALIASES["section"]))

    # Якщо source відсутній — визначимо за доменом
    if not src or src == "—":
        dom = _domain_from_url(url)
        if "epravda.com.ua" in dom:
            src = "epravda"
        elif "minfin.com.ua" in dom:
            src = "minfin"

    # Відсіюємо все, що не epravda/minfin або без URL/Title
    if not url or not title:
        return None
    if src not in ("epravda", "minfin"):
        dom = _domain_from_url(url)
        if "epravda.com.ua" in dom:
            src = "epravda"
        elif "minfin.com.ua" in dom:
            src = "minfin"
        else:
            return None

    if not sec or sec == "—":
        # Секцію беремо з шляху (news, finances, biznes, …)
        m = re.search(r"https?://[^/]+/([a-z\-]+)/", url, flags=re.I)
        sec = (m.group(1) if m else "news").lower()

    return {"title": title, "url": url, "date": date, "source": src, "section": sec}

def _flatten_results(results: Any) -> list[dict]:
    """
    Підтримує формати:
    - list[dict]
    - tuple(list[dict], any)
    - dict[str, list[dict]]   (map source/section → items)
    - будь-що інше → порожньо
    """
    try:
        # tuple/list з першим елементом як колекція
        if isinstance(results, tuple) and results:
            cand = results[0]
            results = cand

        if isinstance(results, dict):
            pool = []
            for _, v in results.items():
                if isinstance(v, list):
                    pool.extend(v)
            results = pool

        if isinstance(results, list):
            out = []
            for it in results:
                norm = _normalize_item(it)
                if norm:
                    out.append(norm)
            return out
    except Exception:
        log.exception("Normalize failed")

    return []

def _format_blocks(items: list[dict]) -> list[str]:
    if not items:
        return ["⚠️ Новини за сьогодні/вчора не знайдено."]

    # групуємо: source -> section -> items
    from collections import defaultdict
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for it in items:
        grouped[it["source"]][it["section"]].append(it)

    blocks = []
    for src in ["epravda", "minfin"][:MAX_SOURCES]:
        if src not in grouped:
            continue
        total_src = sum(len(v) for v in grouped[src].values())
        cap = min(total_src, MAX_PER_SRC)
        lines = [f"✅ {src} — показую {cap} з {total_src}\n"]
        shown = 0
        # найбільші секції — першими
        for section, arr in sorted(grouped[src].items(), key=lambda kv: -len(kv[1])):
            if shown >= cap:
                break
            take = arr[: max(0, cap - shown)]
            lines.append(f"Джерело: {src} | секція: {section} — {len(arr)} новин:")
            for i, n in enumerate(take, 1):
                lines.append(f"{i}. {n['title']} ({_safe(n['date'])})\n   {n['url']}")
                shown += 1
                if shown >= cap:
                    break
            lines.append("")
        blocks.append("\n".join(lines).strip())

    return blocks or ["⚠️ Порожньо."]

# ── Бізнес-логіка ──────────────────────────────────────────────────────────────
async def _do_news(chat_id: int):
    try:
        raw = await asyncio.to_thread(run_all)    # не блокуємо loop
        items = _flatten_results(raw)
        log.info(f"normalize: got {len(items)} items after flatten")
        blocks = _format_blocks(items)

        for b in blocks:
            await _send_chunks(chat_id, b)

        await _send_with_retry(chat_id, "✅ Готово.")
    except Exception as e:
        log.exception("news task failed")
        try:
            await _send_with_retry(chat_id, f"❌ Помилка: {e}")
        except Exception:
            pass

# ── Хендлери ──────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (унікальні, згруповані; без превʼю)"
    )

@dp.message(Command("news_easy"))
async def news_easy_cmd(message: types.Message):
    chat_id = message.chat.id
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10–20 cекунд.")

    old = running_tasks.get(chat_id)
    if old and not old.done():
        await message.answer("🟡 Запит уже виконується. Дочекайся завершення.")
        return

    task = asyncio.create_task(_do_news(chat_id))
    running_tasks[chat_id] = task
    task.add_done_callback(lambda _: running_tasks.pop(chat_id, None))

# ── AIOHTTP ────────────────────────────────────────────────────────────────────
async def handle_health(_: web.Request):
    return web.json_response({"status": "alive"})

async def handle_webhook(request: web.Request):
    data = await request.json()
    await dp.feed_webhook_update(bot, data)  # миттєво відповідаємо 200 OK
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