# groups/easy_sources.py
import asyncio
import logging
import re
from typing import List, Dict, Optional
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta, date
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
    "/finances",  # беремо лише фінанси; інші розділи можуть підтягуватись перехресними лінками
]
MF_PAGES = [
    "/ua/news",
    "/ua/news/money-management/",
    "/ua/news/commerce/",
]

MAX_PER_PAGE = 60  # захисна «стеля» зі сторінки

UA_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}

def _norm(s: str) -> str:
    return " ".join(s.split()) if isinstance(s, str) else s

def _add(items: List[Dict], title: str, href: str, date_text: str, src: str, category: str):
    if not href or not title:
        return
    items.append({
        "title": _norm(title),
        "link": href.strip(),
        "published": _norm(date_text) if date_text else "",
        "src": src,
        "category": category.strip("/") or "news",
    })

def _extract_date_from_url(url: str) -> Optional[date]:
    # minfin: /YYYY/MM/DD/
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None

def _extract_date_from_text(text: str) -> Optional[date]:
    if not text:
        return None
    # 2025-10-28
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    # «28 жовтня 2025»
    m = re.search(r"(\d{1,2})\s+([А-Яа-яІіЇїЄєҐґ]+)\s+(20\d{2})", text)
    if m:
        d = int(m.group(1))
        mon = UA_MONTHS.get(m.group(2).lower())
        y = int(m.group(3))
        if mon:
            try:
                return date(y, mon, d)
            except ValueError:
                return None
    return None

def _only_today_yesterday(items: List[Dict]) -> List[Dict]:
    today = datetime.now(TZ).date()
    yesterday = today - timedelta(days=1)
    out = []
    for it in items:
        d = _extract_date_from_url(it["link"]) or _extract_date_from_text(it.get("published", ""))
        if d and (d == today or d == yesterday):
            out.append(it)
    return out

async def _fetch(session: ClientSession, url: str) -> str:
    async with session.get(url, headers=HEADERS, timeout=20) as r:
        r.raise_for_status()
        return await r.text()

def _parse_epravda(html: str, path: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    # типові тайтл-лінки
    for a in soup.select("a.item__title, article a.article__title, article a.list-item__title"):
        href = a.get("href") or ""
        if href.startswith("/"):
            href = urljoin(EP_BASE, href)
        title = a.get_text(strip=True)
        # шукаємо time/date поряд, якщо є
        date_text = ""
        parent = a.find_parent(["article", "div", "li"])
        if parent:
            dt = parent.select_one("time, .article__date, .list-item__date")
            if dt:
                date_text = dt.get_text(" ", strip=True)
        # категорія з URL
        cat = "news"
        try:
            cat = href.split(EP_BASE)[-1].split("/")[1]
        except Exception:
            pass
        _add(out, title, href, date_text, "epravda", cat)
        if len(out) >= MAX_PER_PAGE:
            break
    return out

def _parse_minfin(html: str, path: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    # беремо тільки лінки з датою у URL
    for a in soup.select("a[href*='/2025/'], a[href*='/ua/2025/']"):
        href = a.get("href") or ""
        text = a.get_text(strip=True)
        if not text:
            continue
        if href.startswith("/"):
            href = urljoin(MF_BASE, href)
        # дата з URL (на minfin це надійніше, ніж текст)
        date_text = ""
        d = _extract_date_from_url(href)
        if d:
            date_text = d.isoformat()
        # категорія з URL
        cat = "news"
        try:
            tail = href.split(MF_BASE)[-1]
            parts = [p for p in tail.split("/") if p]
            if len(parts) >= 2 and parts[0] == "ua":
                cat = parts[2] if len(parts) > 2 else "news"
            elif len(parts) >= 1:
                cat = parts[0]
        except Exception:
            pass
        _add(out, text, href, date_text, "minfin", cat)
        if len(out) >= MAX_PER_PAGE:
            break
    return out

async def _gather_all() -> List[Dict]:
    async with ClientSession() as session:
        ep_all: List[Dict] = []
        for p in EP_PAGES:
            try:
                html = await _fetch(session, urljoin(EP_BASE, p))
                ep_all.extend(_parse_epravda(html, p))
            except Exception as e:
                log.warning(f"epravda fetch fail {p}: {e}")

        mf_all: List[Dict] = []
        for p in MF_PAGES:
            try:
                html = await _fetch(session, urljoin(MF_BASE, p))
                mf_all.extend(_parse_minfin(html, p))
            except Exception as e:
                log.warning(f"minfin fetch fail {p}: {e}")

    # дедуп за URL
    seen = set()
    items: List[Dict] = []
    for arr in (ep_all, mf_all):
        for it in arr:
            u = it["link"]
            if u not in seen:
                seen.add(u)
                items.append(it)

    # лог до фільтра
    total_before = len(items)
    log.info(f"🔹 Парсимо Epravda/Minfin... Всього (до фільтра): {total_before}")

    # фільтр тільки «сьогодні/вчора» + відсікаємо без дати
    items = _only_today_yesterday(items)
    total_after = len(items)
    log.info(f"🔹 Після фільтра дати (сьогодні/вчора): {total_after}")

    # короткий зріз по джерелах
    def _summ(src: str):
        arr = [x for x in items if x["src"] == src]
        log.info(f"✅ {src} — {len(arr)}")

    _summ("epravda")
    _summ("minfin")
    return items

def run_all() -> List[Dict]:
    """
    Повертає список елементів лише за «сьогодні/вчора».
    Елемент:
      title: str
      link: str
      published: YYYY-MM-DD або вихідний текст (якщо був)
      src: 'epravda' | 'minfin'
      category: str
    """
    return asyncio.run(_gather_all())