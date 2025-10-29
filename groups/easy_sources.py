# groups/easy_sources.py
import asyncio
import logging
import re
from typing import List, Dict, Optional
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import date
from zoneinfo import ZoneInfo

log = logging.getLogger("easy_sources")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

TZ = ZoneInfo("Europe/Kyiv")

EP_BASE = "https://epravda.com.ua"
MF_BASE = "https://minfin.com.ua"

EP_PAGES = [
    "/finances",
    "/columns",
]

MF_PAGES = [
    "/ua/news",
    "/ua/news/money-management/",
    "/ua/news/commerce/",
]

MAX_PER_PAGE = 120

# epravda посилання статей зазвичай закінчуються на "-<id>"
EP_ARTICLE_RE = re.compile(r"-\d{5,}/?$")

def _norm(s: str) -> str:
    return " ".join(s.split()) if isinstance(s, str) else s

def _mk_item(title: str, href: str, date_text: str, source: str, section: str) -> Optional[Dict]:
    title = _norm(title)
    href = (href or "").strip()
    if not title or not href:
        return None
    item = {
        # цільові ключі під bot.py
        "title": title,
        "url": href,
        "date": _norm(date_text) if date_text else "",   # допускаємо порожнє значення
        "source": source,
        "section": (section or "news").strip("/"),
        # сумісність (на випадок старих місць використання)
        "link": href,
        "published": _norm(date_text) if date_text else "",
        "src": source,
        "category": (section or "news").strip("/"),
    }
    return item

def _extract_ep_section(href_tail: str) -> str:
    parts = [p for p in href_tail.split("/") if p]
    return parts[0] if parts else "news"

def _extract_mf_section(href_tail: str) -> str:
    parts = [p for p in href_tail.split("/") if p]
    if parts and parts[0] == "ua":
        return parts[1] if len(parts) > 1 else "news"
    return parts[0] if parts else "news"

async def _fetch(session: ClientSession, url: str) -> str:
    async with session.get(url, headers=HEADERS, timeout=25) as r:
        r.raise_for_status()
        return await r.text()

def _parse_epravda(html: str, path: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []

    # суворіші селектори тільки під заголовки статей
    for a in soup.select("article a.article__title, article a.list-item__title, a.item__title"):
        href = a.get("href") or ""
        if href.startswith("/"):
            href = urljoin(EP_BASE, href)

        # відсікаємо навігаційні/службові лінки
        if not href.startswith(EP_BASE):
            continue
        tail = href.split(EP_BASE, 1)[-1]
        # дозволяємо ЛИШЕ /finances/ та /columns/ з ознакою статті "-<id>"
        if not (tail.startswith("/finances/") or tail.startswith("/columns/")):
            continue
        if not EP_ARTICLE_RE.search(tail):
            continue

        title = a.get_text(strip=True)

        # пробуємо дату поряд; якщо нема — лишаємо порожньо (це ок)
        date_text = ""
        parent = a.find_parent(["article", "div", "li"])
        if parent:
            dt = parent.select_one("time, .article__date, .list-item__date, time[itemprop='datePublished']")
            if dt:
                date_text = dt.get_text(" ", strip=True)

        section = _extract_ep_section(tail)
        item = _mk_item(title, href, date_text, "epravda", section)
        if item:
            out.append(item)
        if len(out) >= MAX_PER_PAGE:
            break

    return out

def _parse_minfin(html: str, path: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    # беремо тільки лінки з явною датою в URL /YYYY/MM/DD/
    for a in soup.select("a[href*='/20'][href*='/' ]"):
        href = a.get("href") or ""
        text = a.get_text(strip=True)
        if not text:
            continue
        if href.startswith("/"):
            href = urljoin(MF_BASE, href)
        if not href.startswith(MF_BASE):
            continue

        # груба перевірка патерну дати у шляху
        if not re.search(r"/20\d{2}/\d{2}/\d{2}/", href):
            continue

        tail = href.split(MF_BASE, 1)[-1]
        section = _extract_mf_section(tail)

        # дата з URL (на minfin це найнадійніше)
        m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", href)
        date_text = ""
        if m:
            date_text = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        item = _mk_item(text, href, date_text, "minfin", section)
        if item:
            out.append(item)
        if len(out) >= MAX_PER_PAGE:
            break

    return out

async def _gather_all() -> List[Dict]:
    async with ClientSession() as session:
        ep_all: List[Dict] = []
        for p in EP_PAGES:
            url = urljoin(EP_BASE, p)
            try:
                html = await _fetch(session, url)
                ep_all.extend(_parse_epravda(html, p))
            except Exception as e:
                log.warning(f"epravda fetch fail {p}: {e}")

        mf_all: List[Dict] = []
        for p in MF_PAGES:
            url = urljoin(MF_BASE, p)
            try:
                html = await _fetch(session, url)
                mf_all.extend(_parse_minfin(html, p))
            except Exception as e:
                log.warning(f"minfin fetch fail {p}: {e}")

    # дедуп за url
    seen = set()
    items: List[Dict] = []
    for arr in (ep_all, mf_all):
        for it in arr:
            u = it.get("url") or it.get("link") or ""
            if not u or u in seen:
                continue
            seen.add(u)
            items.append(it)

    log.info(f"🔹 Після парсингу: epravda={len([x for x in items if x['source']=='epravda'])}, minfin={len([x for x in items if x['source']=='minfin'])}")
    # ВАЖЛИВО: НЕ фільтруємо за датою — допускаємо порожню дату (як у твоєму еталоні)
    return items

# важливо: async — щоб не викликати asyncio.run() всередині діючого лупа
async def run_all() -> List[Dict]:
    return await _gather_all()