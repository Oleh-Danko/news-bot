# parsers/ain_parser.py
import re
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone, date
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, text/xml;q=0.9, */*;q=0.8",
}
KYIV_TZ = ZoneInfo("Europe/Kyiv")

FEED_URL = "https://ain.ua/feed/"
SOURCE_PAGE = "https://ain.ua/"

# 🔎 Заборонені теги/категорії (українською + можливі слуги)
BANNED_TEXT = {
    "попнаука", "музика", "спецпроєкти", "спецпроекти",
    "pop-science", "music", "special",
}
# 🔎 Заборонені префікси шляхів посилань на сторінці
BANNED_PREFIXES = ("/pop-science/", "/pop-science/music/", "/special/")

def _fetch_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    return resp.text

def _to_kyiv_date(pubdate_text: str) -> date | None:
    if not pubdate_text:
        return None
    try:
        dt = parsedate_to_datetime(pubdate_text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KYIV_TZ).date()
    except Exception:
        m = re.search(r"\d{4}-\d{2}-\d{2}", pubdate_text)
        if m:
            try:
                return datetime.strptime(m.group(0), "%Y-%m-%d").date()
            except Exception:
                return None
        return None

def _has_banned_category_text(categories: list[str]) -> bool:
    for c in categories:
        lc = (c or "").strip().lower()
        if not lc:
            continue
        # якщо категорія містить будь-який із заборонених ключів
        if any(bt in lc for bt in BANNED_TEXT):
            return True
    return False

def _page_has_banned_tag(url: str) -> bool:
    """Перевіряємо тег-меню статті (.widget__header_tags)."""
    try:
        html = _fetch_text(url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select(".widget__header_tags a[href]"):
            href = (a.get("href") or "").strip()
            text = (a.get_text(strip=True) or "").lower()
            if any(href.startswith(p) for p in BANNED_PREFIXES):
                return True
            if any(bt in text for bt in BANNED_TEXT):
                return True
    except Exception:
        # Якщо сторінку не вдалося завантажити — не блокуємо помилково
        return False
    return False

def parse_ain() -> list[dict]:
    print("🔹 Парсимо AIN.ua...")

    today = datetime.now(tz=KYIV_TZ).date()
    yesterday = today - timedelta(days=1)
    target_dates = {today, yesterday}

    xml_text = _fetch_text(FEED_URL)
    root = ET.fromstring(xml_text)

    items_raw = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        cats_el = item.findall("category")

        title = (title_el.text or "").strip() if title_el is not None else ""
        url = (link_el.text or "").strip() if link_el is not None else ""
        pubdate = (pub_el.text or "").strip() if pub_el is not None else ""
        categories = [(c.text or "").strip() for c in cats_el if c is not None]

        d = _to_kyiv_date(pubdate)
        if not d or d not in target_dates:
            continue

        # 1) Фільтр по RSS-категоріям
        if _has_banned_category_text(categories):
            continue

        # 2) Додаткова перевірка самої сторінки на заборонені теги
        if _page_has_banned_tag(url):
            continue

        items_raw.append(
            {
                "title": title,
                "url": url,
                "date": d.strftime("%Y-%m-%d"),
                "source": SOURCE_PAGE,
                "section": "ain.ua",
            }
        )

    # Дедуп за URL
    seen = set()
    unique = []
    for n in items_raw:
        if n["url"] in seen:
            continue
        seen.add(n["url"])
        unique.append(n)

    print("\n✅ ain.ua - результат:")
    print(f"   Усього знайдено {len(items_raw)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(unique)}\n")

    print(f"🟢Джерело: {SOURCE_PAGE} — {len(unique)} новин:")
    for i, n in enumerate(unique, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
    print()

    return unique

if __name__ == "__main__":
    try:
        parse_ain()
    except Exception as e:
        print(f"❌ Помилка ain_parser: {e}")