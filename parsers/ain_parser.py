# parsers/ain_parser.py
import re
import json
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://ain.ua"
LIST_URL = "https://ain.ua/"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}

# що відсікаємо
EXCLUDE_PREFIXES = ("/pop-science/", "/pop-science/music/", "/special/")

def _fetch_html(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

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
        m = re.search(r"\d{4}-\d{2}-\d{2}", iso_str or "")
        if m:
            try:
                return datetime.strptime(m.group(0), "%Y-%m-%d").date()
            except Exception:
                return None
        return None

def _date_from_url(path: str) -> date | None:
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", path)
    if not m:
        return None
    try:
        y, mm, dd = map(int, m.groups())
        return date(y, mm, dd)
    except Exception:
        return None

def _extract_date_and_title_from_article(soup: BeautifulSoup, url: str) -> tuple[str | None, date | None]:
    # 1) JSON-LD (+ Yoast @graph)
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        flat = []
        for obj in objs:
            if isinstance(obj, dict) and isinstance(obj.get("@graph"), list):
                flat.extend(obj["@graph"])
            else:
                flat.append(obj)
        for obj in flat:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type") or obj.get("type")
            types = [t] if isinstance(t, str) else (t or [])
            types = [str(x).lower() for x in types] if isinstance(types, list) else [str(types).lower()]
            if any(x in ("newsarticle", "article", "reportagenewsarticle") for x in types):
                title = obj.get("headline") or obj.get("name")
                published = obj.get("datePublished") or obj.get("dateCreated") or obj.get("dateModified")
                pub_date = _iso_to_local_date(published) if published else None
                if title or pub_date:
                    return (title.strip() if isinstance(title, str) else None), pub_date

    # 2) <meta> / <time>
    meta = (
        soup.find("meta", {"property": "article:published_time"})
        or soup.find("meta", {"name": "article:published_time"})
        or soup.find("meta", {"property": "og:article:published_time"})
        or soup.find("time", {"datetime": True})
    )
    d = _iso_to_local_date(meta.get("content") or meta.get("datetime") or "") if meta else None

    # 3) з URL
    if not d:
        d = _date_from_url(urlparse(url).path)

    # 4) <title>
    title = None
    if soup.title and soup.title.string:
        title = re.sub(r"\s+\|\s*AIN(\.ua)?\s*$", "", soup.title.string.strip(), flags=re.I)

    return title, d

def _href_path(href: str) -> str:
    """Нормалізуємо будь-який href (відносний або абсолютний) до path."""
    try:
        return urlparse(urljoin(BASE, href)).path or "/"
    except Exception:
        return href or "/"

def _is_excluded_container(container: BeautifulSoup) -> bool:
    # шукаємо теги саме в шапці картки
    for a in container.select(".widget__header_tags a[href]"):
        path = _href_path(a.get("href", ""))
        if any(path.startswith(p) for p in EXCLUDE_PREFIXES):
            return True
    return False

def _collect_article_links(list_soup: BeautifulSoup, limit: int = 150) -> list[str]:
    links, seen = [], set()

    # 1) основні картки
    for wrap in list_soup.select(".widget__content-wrapper"):
        # фільтр за тегами в шапці картки
        if _is_excluded_container(wrap):
            continue
        a = wrap.select_one("a.widget__content[href]") or wrap.select_one("a[href]")
        if not a:
            continue
        url = urljoin(BASE, a.get("href", "").strip())
        path = _href_path(url)
        # додаткова страховка: якщо сам URL належить до заборонених секцій — скіпаємо
        if any(path.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= limit:
            return links

    # 2) фолбек: будь-які посилання з датою в URL + перевірка на заборонені секції через найближчий контейнер
    for a in list_soup.find_all("a", href=True):
        href = a["href"].strip()
        url = urljoin(BASE, href)
        path = _href_path(url)
        if not re.search(r"/20\d{2}/\d{2}/\d{2}/", path):
            continue
        # знайти найближчий контейнер картки й повторно перевірити теги
        cont = a.find_parent(class_=re.compile(r"\bwidget__content-wrapper\b"))
        if cont and _is_excluded_container(cont):
            continue
        if any(path.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if url in seen:
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

    try:
        soup = _fetch_html(LIST_URL)
    except Exception as e:
        print(f"❌ Помилка ain_parser: {e}")
        return []

    candidates = _collect_article_links(soup, limit=150)

    items = []
    for url in candidates:
        try:
            art = _fetch_html(url)
        except Exception:
            continue
        title, pub_date = _extract_date_and_title_from_article(art, url)
        if not pub_date or pub_date not in target_dates:
            continue
        if not title:
            title = "Без назви"
        items.append(
            {
                "title": title.strip(),
                "url": url,
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": LIST_URL,
                "section": "ain.ua",
            }
        )

    # дедуп за URL
    seen = set()
    unique = []
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