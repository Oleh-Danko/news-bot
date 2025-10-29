import os
import asyncio
import logging
import inspect
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ====== Конфіг ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()  # має вигляд: https://universal-bot-live.onrender.com

assert BOT_TOKEN, "BOT_TOKEN is required"
assert WEBHOOK_URL, "WEBHOOK_URL is required"

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
MAX_CHARS_PER_MSG = 3800           # безпечна межа <4096
PAUSE_BETWEEN_MSGS_SEC = 0.06      # антифлуд
SOURCE_ORDER = ["epravda", "minfin"]

# ====== Логи ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("news-bot")

# ====== Імпорт парсера ======
try:
    from groups.easy_sources import run_all as parse_all_sources
except Exception as e:
    log.exception("Не вдалося імпортувати groups.easy_sources.run_all()")
    raise

# ====== Утиліти форматування/надсилання ======
def _norm_date(s: Any) -> str:
    if not s:
        return ""
    if isinstance(s, datetime):
        return s.strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(s)

def _dedup_by_url(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        url = (it.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out

def _group_by_source(items_or_map: Any) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    if isinstance(items_or_map, dict):
        for src, payload in items_or_map.items():
            if isinstance(payload, dict) and "items" in payload:
                arr = payload.get("items") or []
            else:
                arr = payload or []
            if not isinstance(arr, list):
                continue
            for it in arr:
                if isinstance(it, dict):
                    it.setdefault("source", src)
                    grouped[src].append(it)
        return grouped

    if isinstance(items_or_map, list):
        for it in items_or_map:
            if not isinstance(it, dict):
                continue
            src = (it.get("source") or "").strip().lower() or "unknown"
            grouped[src].append(it)
        return grouped

    return {}

def _sort_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(it):
        d = _norm_date(it.get("date"))
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            dt = datetime.min
        return (-int(dt.timestamp()), (it.get("title") or "").lower())
    return sorted(items, key=key)

def _format_lines(items: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for idx, it in enumerate(items, 1):
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        d = _norm_date(it.get("date"))
        suffix = f" ({d})" if d else ""
        lines.append(f"{idx}. {title}{suffix}")
        lines.append(f"   {url}")
    return lines

def _chunk_and_build_messages(header: str, lines: List[str]) -> List[str]:
    messages = []
    cur = header.strip()
    for line in lines:
        piece = ("\n" + line)
        if len(cur) + len(piece) > MAX_CHARS_PER_MSG:
            messages.append(cur)
            cur = line
        else:
            cur += piece
    if cur:
        messages.append(cur)
    return messages

async def _safe_send_many(bot: Bot, chat_id: int, messages: List[str]):
    for m in messages:
        if len(m) > 4096:
            start = 0
            while start < len(m):
                await bot.send_message(chat_id, m[start:start+3800])
                start += 3800
                await asyncio.sleep(PAUSE_BETWEEN_MSGS_SEC)
        else:
            await bot.send_message(chat_id, m)
        await asyncio.sleep(PAUSE_BETWEEN_MSGS_SEC)

async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x

# ====== Бот/Диспетчер ======
dp = Dispatcher()
bot = Bot(BOT_TOKEN, parse_mode=None)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (унікальні, згруповані; без превʼю)"
    )
    await message.answer(text)

@dp.message(Command("news_easy"))
async def cmd_news_easy(message: Message):
    chat_id = message.chat.id
    waiting = "⏳ Збираю свіжі новини... Це може зайняти до 10–20 cекунд."
    try:
        await message.answer(waiting)
    except Exception:
        pass

    try:
        raw = await _maybe_await(parse_all_sources())

        # === NEW: якщо парсери повернули готові текстові блоки (як у консолі) — шлемо як є
        if isinstance(raw, str):
            await _safe_send_many(bot, chat_id, [raw])
            await bot.send_message(chat_id, "✅ Готово.")
            return
        if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
            await _safe_send_many(bot, chat_id, raw if raw else ["⚠️ Порожній результат."])
            await bot.send_message(chat_id, "✅ Готово.")
            return
        # === /NEW

        grouped = _group_by_source(raw)
        if not grouped:
            await bot.send_message(chat_id, "⚠️ Новини не знайдено.")
            await bot.send_message(chat_id, "✅ Готово.")
            return

        ordered_sources = [s for s in SOURCE_ORDER if s in grouped] + [s for s in grouped.keys() if s not in SOURCE_ORDER]

        for source in ordered_sources:
            items = grouped.get(source, [])
            for it in items:
                it["date"] = _norm_date(it.get("date"))
                it["section"] = (it.get("section") or "").strip().lower()

            items = _dedup_by_url(items)
            items = _sort_items(items)

            total = len(items)
            if total == 0:
                continue

            header = f"✅ {source} — показую {total} з {total}"
            lines = _format_lines(items)
            messages = _chunk_and_build_messages(header, lines)
            await _safe_send_many(bot, chat_id, messages)

        await bot.send_message(chat_id, "✅ Готово.")

    except Exception as e:
        log.exception("Помилка у /news_easy: %s", e)
        try:
            await bot.send_message(chat_id, "⚠️ Сталася помилка під час формування списку новин.")
        except Exception:
            pass

# ====== AIOHTTP APP (health + webhook) ======
async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "alive"})

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app

app = build_app()

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))