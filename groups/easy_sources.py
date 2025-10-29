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

EP_PAGES = ["/finances"]
MF_PAGES = ["/ua/news", "/ua/news/money-management/", "/ua/news/commerce/"]

MAX_PER_PAGE = 60

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
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
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

    # 1) основні відомі селектори
    selectors = [
        "a.item__title",
        "article a.article__title",
        "article a.list-item__title",
        "h2 a.article__title",
        "h3 a.article__title",
    ]
    for sel in selectors:
        for a in soup.select(sel):
            href = a.get("href") or ""
            if href.startswith("/"):
                href = urljoin(EP_BASE, href)
            if not href.startswith(EP_BASE):
                continue
            # беремо лише фінансові/новинні матеріали
            tail = href.replace(EP_BASE, "")
            if "/finances" not in tail and "/news" not in tail:
                continue

            title = a.get_text(strip=True)
            date_text = ""
            parent = a.find_parent(["article", "div", "li"])
            if parent:
                dt = parent.select_one("time[datetime], time, .article__date, .list-item__date")
                if dt:
                    date_text = dt.get_text(" ", strip=True)

            # 2) якщо дати зовсім немає у тизері — ставимо сьогодні (щоб не відсіклося)
            if not date_text:
                date_text = datetime.now(TZ).date().isoformat()

            # категорія з URL
            cat = "news"
            try:
                parts = [p for p in tail.split("/") if p]
                if parts:
                    cat = parts[0]
            except Exception:
                pass

            _add(out, title, href, date_text, "epravda", cat)
            if len(out) >= MAX_PER_PAGE:
                return out

    # 3) бекап: будь-які посилання з /finances або /news
    if not out:
        for a in soup.select("a[href*='/finances/'], a[href*='/news/']"):
            href = a.get("href") or ""
            if href.startswith("/"):
                href = urljoin(EP_BASE, href)
            if not href.startswith(EP_BASE):
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            date_text = datetime.now(TZ).date().isoformat()
            _add(out, title, href, date_text, "epravda", "finances")
            if len(out) >= MAX_PER_PAGE:
                break

    return out

def _parse_minfin(html: str, path: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    for a in soup.select("a[href*='/2025/'], a[href*='/ua/2025/']"):
        href = a.get("href") or ""
        text = a.get_text(strip=True)
        if not text:
            continue
        if href.startswith("/"):
            href = urljoin(MF_BASE, href)
        date_text = ""
        d = _extract_date_from_url(href)
        if d:
            date_text = d.isoformat()
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

    seen = set()
    items: List[Dict] = []
    for arr in (ep_all, mf_all):
        for it in arr:
            u = it["link"]
            if u not in seen:
                seen.add(u)
                items.append(it)

    total_before = len(items)
    log.info(f"🔹 Парсимо Epravda/Minfin... Всього (до фільтра): {total_before}")

    items = _only_today_yesterday(items)
    total_after = len(items)
    log.info(f"🔹 Після фільтра дати (сьогодні/вчора): {total_after}")
    log.info(f"✅ epravda — {len([x for x in items if x['src']=='epravda'])}")
    log.info(f"✅ minfin  — {len([x for x in items if x['src']=='minfin'])}")
    return items

def run_all():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_gather_all())
    else:
        return loop.create_task(_gather_all())