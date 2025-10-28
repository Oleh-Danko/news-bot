# groups/easy_sources.py
import asyncio
import logging
from typing import List, Dict
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin

log = logging.getLogger("easy_sources")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

EP_BASE = "https://epravda.com.ua"
MF_BASE = "https://minfin.com.ua"

EP_PAGES = [
    "/finances",
]
MF_PAGES = [
    "/ua/news",
    "/ua/news/money-management/",
    "/ua/news/commerce/",
]

MAX_PER_PAGE = 60  # жорстка «стеля», потім ще буде дедуп

def _norm(space: str) -> str:
    return " ".join(space.split()) if isinstance(space, str) else space

def _add(items: List[Dict], title: str, href: str, date: str, src: str, category: str):
    if not href or not title:
        return
    items.append({
        "title": _norm(title),
        "link": href.strip(),
        "published": _norm(date) if date else "",
        "src": src,
        "category": category.strip("/") or "news",
    })

async def _fetch(session: ClientSession, url: str) -> str:
    async with session.get(url, headers=HEADERS, timeout=20) as r:
        r.raise_for_status()
        return await r.text()

def _parse_epravda(html: str, path: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    # Типові картки списків: a.item__title / article.list-item
    for a in soup.select("a.item__title, article a.article__title, article a.list-item__title"):
        href = a.get("href") or ""
        if href.startswith("/"):
            href = urljoin(EP_BASE, href)
        title = a.get_text(strip=True)
        # дата поряд / в блоці (часто у списках відсутня — припускаємо пусто)
        date_el = a.find_parent(["article", "div"])
        date_text = ""
        if date_el:
            dt = date_el.select_one("time, .article__date, .list-item__date")
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
    # Посилання у стрічці новин
    for a in soup.select("a[href*='/2025/'], a[href*='/ua/2025/']"):
        href = a.get("href") or ""
        text = a.get_text(strip=True)
        # фільтр від сміття: потрібні повні новини з id
        if not text or "/news/" in href and href.count("/") < 5:
            continue
        if href.startswith("/"):
            href = urljoin(MF_BASE, href)
        # дата у блоці поруч
        date_text = ""
        row = a.find_parent(["li", "article", "div"])
        if row:
            dt = row.select_one("time, .time, .date")
            if dt:
                date_text = dt.get_text(" ", strip=True)
        # категорія з URL
        cat = "news"
        try:
            tail = href.split(MF_BASE)[-1]
            parts = [p for p in tail.split("/") if p]
            if len(parts) >= 2 and parts[0] in ("ua",):
                # ua/news/commerce/...
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
    items: List[Dict] = []
    async with ClientSession() as session:
        # Epravda
        ep_all: List[Dict] = []
        for p in EP_PAGES:
            try:
                html = await _fetch(session, urljoin(EP_BASE, p))
                ep_all.extend(_parse_epravda(html, p))
            except Exception as e:
                log.warning(f"epravda fetch fail {p}: {e}")
        # Minfin
        mf_all: List[Dict] = []
        for p in MF_PAGES:
            try:
                html = await _fetch(session, urljoin(MF_BASE, p))
                mf_all.extend(_parse_minfin(html, p))
            except Exception as e:
                log.warning(f"minfin fetch fail {p}: {e}")

    # Дедуп за URL, пріоритет — перша зустріч
    seen = set()
    for arr in (ep_all, mf_all):
        for it in arr:
            u = it.get("link")
            if u and u not in seen:
                seen.add(u)
                items.append(it)

    # Логи як у твоєму форматі
    def _summ(src: str):
        arr = [x for x in items if x["src"] == src]
        log.info(f"✅ {src} - результат:\n   Унікальних новин: {len(arr)}")
        # простий зріз по категоріях
        bycat = {}
        for x in arr:
            bycat.setdefault(x["category"], 0)
            bycat[x["category"]] += 1
        for c, n in sorted(bycat.items(), key=lambda kv: -kv[1])[:5]:
            log.info(f"   {src}:{c} — {n}")

    log.info("🔹 Парсимо Epravda/Minfin...")
    _summ("epravda")
    _summ("minfin")
    return items

def run_all() -> List[Dict]:
    """
    СИНХРОННА обгортка, яка ПОВЕРТАЄ список елементів:
    {
      'title': str,
      'link': str,
      'published': str,
      'src': 'epravda'|'minfin',
      'category': str
    }
    """
    return asyncio.run(_gather_all())