# parsers/ain_parser.py
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse

BASE = "https://ain.ua/"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.google.com/",
}

# Теґи/розділи, які треба ігнорувати
BLOCKED_TAG_PREFIXES = ("/pop-science/", "/pop-science/music/", "/special/")

def _fetch_html(url: str) -> BeautifulSoup:
    """
    1) пробуємо напряму;
    2) якщо 403/429/503 — fallback через r.jina.ai (статичний проксі).
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code in (403, 429, 503):
            raise requests.HTTPError(f"{r.status_code} on direct fetch", response=r)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except requests.HTTPError as e:
        # fallback тільки для головної та статей з домену ain.ua
        u = urlparse(url)
        if u.netloc and "ain.ua" in u.netloc:
            fallback = f"https://r.jina.ai/http://{u.netloc}{u.path or ''}"
            rf = requests.get(fallback, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=25)
            rf.raise_for_status()
            return BeautifulSoup(rf.text, "html.parser")
        raise

def _date_from_url(href: str) -> date | None:
    # /2025/11/01/slug/
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", href)
    if not m:
        return None
    try:
        y, mo, d = map(int, m.groups())
        return date(y, mo, d)
    except Exception:
        return None

def _is_blocked_by_tags(wrapper: BeautifulSoup) -> bool:
    # шукаємо список тегів у хедері картки
    for a in wrapper.select(".widget__header_tags a[href]"):
        href = a.get("href", "").strip()
        if any(href.startswith(pref) for pref in BLOCKED_TAG_PREFIXES):
            return True
    return False

def _collect_from_home(soup: BeautifulSoup) -> list[dict]:
    items = []
    # Кожна новина в блоці .widget__content-wrapper
    for wrap in soup.select(".widget__content-wrapper"):
        if _is_blocked_by_tags(wrap):
            continue

        a = wrap.select_one("a.widget__content[href]")
        if not a:
            # запасний варіант — будь-який <a> з датою у шляху
            for a2 in wrap.select("a[href]"):
                if _date_from_url(a2.get("href", "")):
                    a = a2
                    break
        if not a:
            continue

        href = a.get("href", "").strip()
        if href.startswith("/"):
            url = urljoin(BASE, href)
        elif href.startswith("http"):
            url = href
        else:
            continue

        d = _date_from_url(url)
        # заголовок
        title_el = a.select_one("p.h2.strong") or a.select_one("h2") or a
        title = title_el.get_text(strip=True) if title_el else ""

        items.append(
            {
                "title": title,
                "url": url,
                "date": d,  # може бути None — доб'ємо з HTML статті нижче
            }
        )
    return items

def _ensure_date(item: dict) -> dict:
    if item.get("date"):
        return item
    # якщо на головній не знайшли дату — підвантажимо сторінку статті
    try:
        art = _fetch_html(item["url"])
    except Exception:
        return item
    # Пошук дати у <time datetime="..."> або meta
    t = art.find("time", attrs={"datetime": True})
    dt = None
    if t and t.get("datetime"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", t["datetime"])
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                dt = None
    if not dt:
        for sel in [
            ('meta[property="article:published_time"]', "content"),
            ('meta[name="article:published_time"]', "content"),
            ('meta[itemprop="datePublished"]', "content"),
        ]:
            el = art.select_one(sel[0])
            val = el.get(sel[1]) if el else None
            if val:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", val)
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                    except Exception:
                        dt = None
                if dt:
                    break
    if dt:
        item["date"] = dt
    return item

def parse_ain() -> list[dict]:
    print("\n🔹 Парсимо AIN.ua...")
    today = datetime.now(tz=KYIV_TZ).date()
    yesterday = today - timedelta(days=1)
    target_dates = {today, yesterday}

    soup = _fetch_html(BASE)
    raw = _collect_from_home(soup)

    # добиваємо дати, де не вдалось зчитати з URL
    filled = [_ensure_date(it) for it in raw]

    # фільтр по датах (сьогодні/вчора)
    filtered = []
    for it in filled:
        if isinstance(it.get("date"), date) and it["date"] in target_dates:
            filtered.append(it)

    # дедуп за URL
    seen = set()
    unique = []
    for it in filtered:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        unique.append(
            {
                "title": it["title"],
                "url": it["url"],
                "date": it["date"].strftime("%Y-%m-%d"),
                "source": BASE,
                "section": "ain.ua",
            }
        )

    print("\n✅ ain - результат:")
    print(f"   Усього знайдено {len(filtered)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(unique)}\n")

    print(f"🟢Джерело: {BASE} — {len(unique)} новин:")
    for i, n in enumerate(unique, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
    print()

    return unique

if __name__ == "__main__":
    try:
        parse_ain()
    except Exception as e:
        print(f"❌ Помилка ain_parser: {e}")