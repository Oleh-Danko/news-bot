# parsers/ain_parser.py
import re
import json
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

BASE = "https://ain.ua"
LIST_URL = "https://ain.ua/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
KYIV_TZ = ZoneInfo("Europe/Kyiv")

# Відсікаємо ці розділи
EXCLUDE_PREFIXES = ("/pop-science/", "/pop-science/music/", "/special/")

def _fetch(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def _is_excluded_url(url: str) -> bool:
    try:
        p = urlparse(url)
        path = p.path or ""
        return any(path.startswith(pref) for pref in EXCLUDE_PREFIXES)
    except Exception:
        return False

def _wrapper_has_excluded_tags(node: BeautifulSoup) -> bool:
    # Перевіряємо теги в шапці картки
    for a in node.select(".widget__header_tags a[href]"):
        href = (a.get("href") or "").strip()
        if any(href.startswith(p) for p in EXCLUDE_PREFIXES):
            return True
    return False

def _probable_article_link(href: str) -> bool:
    if not href:
        return False
    u = urlparse(href)
    if u.netloc and u.netloc not in ("", "ain.ua", "www.ain.ua"):
        return False
    path = u.path or ""
    # Типовий формат: /YYYY/MM/DD/slug/
    if re.search(r"/\d{4}/\d{2}/\d{2}/", path):
        return True
    # Деякі матеріали без дати в URL — допускаємо глибину
    return path.count("/") >= 3 and not path.endswith("/")

def _iso_to_local_date(iso_str: str) -> date | None:
    if not iso_str:
        return None
    try:
        s = iso_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KYIV_TZ).date()
    except Exception:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", iso_str)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                return None
        return None

def _extract_title_and_date(soup: BeautifulSoup) -> tuple[str | None, date | None]:
    # 1) JSON-LD (в т.ч. @graph)
    for sc in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(sc.string or "")
        except Exception:
            continue
        objs = []
        if isinstance(data, dict) and "@graph" in data and isinstance(data["@graph"], list):
            objs = data["@graph"]
        elif isinstance(data, list):
            objs = data
        elif isinstance(data, dict):
            objs = [data]

        for obj in objs:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type") or obj.get("type") or ""
            types = [t] if isinstance(t, str) else [x for x in t if isinstance(x, str)]
            types = [x.lower() for x in types]
            if any(x in ("newsarticle", "article", "blogposting") for x in types):
                title = (obj.get("headline") or obj.get("name") or "").strip() or None
                published = obj.get("datePublished") or obj.get("dateCreated") or obj.get("dateModified")
                d = _iso_to_local_date(published) if published else None
                if title or d:
                    return title, d

    # 2) meta / time
    meta = soup.find("meta", {"property": "article:published_time"}) \
        or soup.find("meta", {"name": "article:published_time"}) \
        or soup.find("meta", {"property": "og:article:published_time"}) \
        or soup.find("meta", {"itemprop": "datePublished"}) \
        or soup.find("time", {"datetime": True})
    d = None
    if meta:
        content = meta.get("content") or meta.get("datetime") or meta.get_text(strip=True)
        d = _iso_to_local_date(content)

    # 3) title fallback
    title = None
    og = soup.find("meta", {"property": "og:title"})
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    return title, d

def _collect_links(list_soup: BeautifulSoup, limit: int = 120) -> list[str]:
    links, seen = [], set()

    # A) Головні великі картки
    for wrap in list_soup.select(".widget__content-wrapper"):
        if _wrapper_has_excluded_tags(wrap):
            continue
        a = wrap.select_one("a.widget__content[href]")
        if not a:
            continue
        href = a.get("href", "").strip()
        url = urljoin(BASE, href) if href.startswith("/") else href
        if not _probable_article_link(url) or _is_excluded_url(url):
            continue
        if url not in seen:
            seen.add(url)
            links.append(url)
            if len(links) >= limit:
                return links

    # B) Спискові картки/інші блоки
    for a in list_soup.select("a.widget__content[href], .widget a[href], h2 a[href]"):
        href = a.get("href", "").strip()
        url = urljoin(BASE, href) if href.startswith("/") else href
        if not url or "ain.ua" not in url:
            continue
        if _is_excluded_url(url) or not _probable_article_link(url):
            continue
        if url in seen:
            continue
        # якщо є батьківський wrapper — також перевіримо теги
        wrapper = a.find_parent(class_="widget__content-wrapper")
        if wrapper and _wrapper_has_excluded_tags(wrapper):
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= limit:
            break

    return links

def parse_ain() -> list[dict]:
    print("🔹 Парсимо AIN.ua...")

    today = datetime.now(tz=KYIV_TZ).date()
    yesterday = today - timedelta(days=1)
    target_dates = {today, yesterday}

    soup = _fetch(LIST_URL)
    candidates = _collect_links(soup, limit=150)

    items = []
    for url in candidates:
        try:
            art = _fetch(url)
        except Exception:
            continue
        title, d = _extract_title_and_date(art)
        if not d or d not in target_dates:
            continue
        if not title:
            title = "Без назви"
        items.append({
            "title": title,
            "url": url,
            "date": d.strftime("%Y-%m-%d"),
            "source": LIST_URL,
            "section": "ain.ua",
        })

    # Дедуп за URL
    seen, unique = set(), []
    for n in items:
        if n["url"] in seen:
            continue
        seen.add(n["url"])
        unique.append(n)

    print("\n✅ ain - результат:")
    print(f"   Усього знайдено {len(items)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(unique)}\n")

    print(f"🟢Джерело: {LIST_URL} — {len(unique)} новин:")
    for i, n in enumerate(unique, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
    print()
    return unique

if __name__ == "__main__":
    try:
        parse_ain()
    except Exception as e:
        print(f"❌ Помилка ain_parser: {e}")