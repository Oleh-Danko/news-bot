import os
import asyncio
import logging
import json
from typing import Any, Dict, List, Tuple

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, Update
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

# === Конфіг ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else None
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()

# Безпечні межі Telegram
TG_MAX = 4096
SAFETY_MARGIN = 600
CHUNK_LIMIT = TG_MAX - SAFETY_MARGIN  # ~3500 симв.
PER_MESSAGE_DELAY = 0.05  # невелика пауза між повідомленнями, щоб не ловити флуд

# Ніяких лімітів на кількість новин — шлемо всі, шматуємо за розміром
SHOW_ALL = True

# Логи
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("news_bot")

# Aiogram v3
router = Router()
dp = Dispatcher()
dp.include_router(router)
bot = Bot(BOT_TOKEN, parse_mode=None)

# Імпорт наших парсерів
try:
    from groups.easy_sources import run_all as run_easy_sources  # обовʼязково існує за твоєю структурою
except Exception as e:
    log.exception("Помилка імпорту run_all(): %s", e)
    run_easy_sources = None


# ===================== Допоміжні =====================

async def send_text_with_retry(chat_id: int, text: str) -> None:
    """Надійна відправка з обробкою 429/BadRequest та короткою затримкою між повідомленнями."""
    while True:
        try:
            await bot.send_message(chat_id, text)
            await asyncio.sleep(PER_MESSAGE_DELAY)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.2)
        except TelegramBadRequest as e:
            # Якщо текст все одно завеликий — подрібнити ще жорсткіше на 2000
            if "message is too long" in str(e).lower():
                for chunk in chunk_long_text(text, limit=2000):
                    await send_text_with_retry(chat_id, chunk)
                return
            raise
        except Exception as e:
            log.exception("send_text_with_retry error: %s", e)
            # невеликий бекап-ретрай
            await asyncio.sleep(0.5)


def chunk_long_text(text: str, limit: int = CHUNK_LIMIT) -> List[str]:
    """Розбити довгий текст на шматки без розриву рядків/логіки."""
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    buf: List[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        ln = len(line)
        if size + ln > limit and buf:
            parts.append("".join(buf).rstrip())
            buf = [line]
            size = ln
        else:
            buf.append(line)
            size += ln
    if buf:
        parts.append("".join(buf).rstrip())
    return parts


def render_section_header(src: str, section: str, count: int) -> str:
    sec = f" | секція: {section}" if section else ""
    return f"Джерело: {src}{sec} — {count} новин:\n"


def render_item_line(idx: int, title: str, date_str: str, url: str) -> str:
    date_part = f" ({date_str})" if date_str else " (—)"
    return f"{idx}. {title}{date_part}\n   {url}\n"


def normalize_results(results: Any) -> List[Tuple[str, str, List[Dict[str, str]]]]:
    """
    Приводимо будь-яку структуру від run_all() до уніфікованої:
    List[(source, section, items)], де item = {title, url, date?}
    Це «мʼякий» нормалізатор: намагається підхопити різні варіанти.
    """
    out: List[Tuple[str, str, List[Dict[str, str]]]] = []

    # Випадок: вже список секцій
    if isinstance(results, list):
        for sec in results:
            src = sec.get("source") or sec.get("src") or sec.get("origin") or ""
            section = sec.get("section") or sec.get("name") or ""
            items = sec.get("items") or sec.get("list") or []
            norm_items = []
            for it in items:
                title = (it.get("title") or it.get("name") or it.get("t") or "").strip()
                url = (it.get("url") or it.get("link") or "").strip()
                date_str = (it.get("date") or it.get("date_str") or it.get("d") or "").strip()
                if title and url:
                    norm_items.append({"title": title, "url": url, "date": date_str})
            if norm_items:
                out.append((src, section, norm_items))
        return out

    # Випадок: dict з ключами-джерелами
    if isinstance(results, dict):
        for src, sec_val in results.items():
            if isinstance(sec_val, dict):
                for section, items in sec_val.items():
                    norm_items = []
                    for it in items if isinstance(items, list) else []:
                        title = (it.get("title") or it.get("name") or it.get("t") or "").strip()
                        url = (it.get("url") or it.get("link") or "").strip()
                        date_str = (it.get("date") or it.get("date_str") or it.get("d") or "").strip()
                        if title and url:
                            norm_items.append({"title": title, "url": url, "date": date_str})
                    if norm_items:
                        out.append((str(src), str(section), norm_items))
            elif isinstance(sec_val, list):
                norm_items = []
                for it in sec_val:
                    title = (it.get("title") or it.get("name") or it.get("t") or "").strip()
                    url = (it.get("url") or it.get("link") or "").strip()
                    date_str = (it.get("date") or it.get("date_str") or it.get("d") or "").strip()
                    if title and url:
                        norm_items.append({"title": title, "url": url, "date": date_str})
                if norm_items:
                    out.append((str(src), "", norm_items))
        return out

    # Якщо зовсім інше — спробуємо парою рядків
    text = str(results).strip()
    if text:
        out.append(("результат", "", [{"title": "Вивід парсера", "url": "", "date": ""},]))
    return out


def build_all_messages(results: Any) -> List[str]:
    """
    Побудувати повні тексти для розсилки, без лімітів по кількості новин.
    Потім вони додатково ріжуться по CHUNK_LIMIT.
    """
    norm = normalize_results(results)
    if not norm:
        return ["⚠️ Нічого не знайдено."]

    messages: List[str] = []
    for src, section, items in norm:
        header = render_section_header(src or "джерело", section, len(items))
        buf_lines: List[str] = [header]
        counter = 1
        for it in items:
            line = render_item_line(counter, it["title"], it.get("date", ""), it["url"])
            buf_lines.append(line)
            counter += 1
        full_text = "".join(buf_lines).rstrip()
        messages.extend(chunk_long_text(full_text, CHUNK_LIMIT))
    return messages


async def process_news_easy(chat_id: int, progress_msg: Message | None) -> None:
    """Фонова обробка: парсинг та відправка всіх новин шматками."""
    try:
        if run_easy_sources is None:
            raise RuntimeError("run_all() недоступний")

        # Виклик нашого парсера. Ніяких зрізів — беремо все.
        results = await maybe_await(run_easy_sources)

        all_msgs = build_all_messages(results)
        # Якщо дуже багато шматків — попередження про кількість
        if len(all_msgs) > 1:
            first_line = f"✅ Знайдено багато новин. Відправляю {len(all_msgs)} повідомлення(нь)."
            await send_text_with_retry(chat_id, first_line)

        for m in all_msgs:
            if m.strip():
                await send_text_with_retry(chat_id, m)

        if progress_msg:
            try:
                await progress_msg.edit_text("✅ Готово.")
            except Exception:
                pass

    except Exception as e:
        log.exception("process_news_easy error: %s", e)
        if progress_msg:
            try:
                await progress_msg.edit_text("❌ Помилка під час збору новин.")
            except Exception:
                pass
        if ADMIN_ID:
            try:
                await send_text_with_retry(ADMIN_ID, f"❌ Помилка /news_easy: {e}")
            except Exception:
                pass


async def maybe_await(x):
    if asyncio.iscoroutinefunction(x):
        return await x()
    if asyncio.iscoroutine(x):
        return await x
    return x  # синхронний результат


# ===================== Хендлери =====================

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    text = (
        "👋 Привіт! Доступні команди:\n"
        "• /news_easy — Epravda + Minfin (всі новини; без превʼю)"
    )
    await message.answer(text)


@router.message(F.text == "/news_easy")
async def cmd_news_easy(message: Message):
    # Миттєва відповідь, далі — фоном
    progress = await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10–20 cекунд.")
    asyncio.create_task(process_news_easy(message.chat.id, progress))


# ===================== AIOHTTP: webhook & health =====================

async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return web.Response(text="Bad Request", status=400)
    try:
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
    except Exception as e:
        log.exception("feed_update error: %s", e)
    return web.Response(text="OK")

async def handle_health(request: web.Request):
    return web.json_response({"status": "alive"})

async def handle_parse(request: web.Request):
    """Сервісний ендпойнт для швидкої перевірки парсера (JSON-результат)."""
    try:
        if run_easy_sources is None:
            raise RuntimeError("run_all() недоступний")
        results = await maybe_await(run_easy_sources)
        return web.json_response({"ok": True, "results": results}, dumps=lambda o: json.dumps(o, ensure_ascii=False))
    except Exception as e:
        log.exception("/parse error: %s", e)
        return web.json_response({"ok": False, "error": str(e)})

def make_app() -> web.Application:
    app = web.Application()
    # Вебхук строго на /webhook/<BOT_TOKEN>
    app.router.add_post(f"/webhook/{BOT_TOKEN}", handle_webhook)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/parse", handle_parse)
    return app


if __name__ == "__main__":
    if not BOT_TOKEN or not WEBHOOK_URL:
        raise SystemExit("BOT_TOKEN/WEBHOOK_URL не задані в env.")

    app = make_app()
    port = int(os.getenv("PORT", "10000"))
    log.info("======== Running on http://0.0.0.0:%d ========", port)
    web.run_app(app, port=port)