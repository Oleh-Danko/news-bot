# parsers/coindesk_parser.py
import os
import re
from datetime import date, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.coindesk.com"
SOURCE_URL = "https://www.coindesk.com/uk/latest-crypto-news"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}

ONLY_TODAY = os.environ.get("ONLY_TODAY") == "1"

def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def _abs(url: str) -> str:
    if url.startswith("http"):
        return url
    return urljoin(BASE, url)

def _extract_date_from_url(u: str) -> date | None:
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", u)
    if not m:
        return None
    try:
        y, mth, d = map(int, m.groups())
        return date(y, mth, d)
    except Exception:
        return None

def _best_title(a_tag) -> str:
    t = (a_tag.get_text(strip=True) or "").strip()
    if t:
        return t
    for parent in (a_tag, a_tag.parent, getattr(a_tag, "parent", None).parent if a_tag and a_tag.parent else None):
        if not parent:
            continue
        h = parent.find(["h2", "h3", "h4"])
        if h:
            tt = h.get_text(strip=True)
            if tt:
                return tt
    return ""

def parse_coindesk() -> list[dict]:
    print("🔹 Парсимо CoinDesk...")

    soup = _fetch(SOURCE_URL)
    today = date.today()
    yesterday = today - timedelta(days=1)
    target = {today} if ONLY_TODAY else {today, yesterday}

    seen_urls = set()
    items: list[dict] = []

    for a in soup.select('a[href]'):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = _abs(href)

        if "/uk/" not in url:
            continue
        if SOURCE_URL.rstrip("/") == url.rstrip("/"):
            continue

        dt = _extract_date_from_url(url)
        if not dt or dt not in target:
            continue

        title = _best_title(a)
        if not title:
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        items.append({
            "title": title,
            "url": url,
            "date": dt.strftime("%Y-%m-%d"),
            "source": SOURCE_URL,
            "section": "coindesk-uk",
        })

    items.sort(key=lambda x: (x["date"], x["title"]), reverse=True)

    print("\n✅ coindesk - результат:")
    print(f"   Усього знайдено {len(items)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(items)}\n")

    print(f"🟢Джерело: {SOURCE_URL} — {len(items)} новин:")
    for i, n in enumerate(items, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
    print()

    return items

if __name__ == "__main__":
    try:
        parse_coindesk()
    except Exception as e:
        print(f"❌ Помилка coindesk_parser: {e}")