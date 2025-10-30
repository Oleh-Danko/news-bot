# parsers/epravda_parser.py
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
from urllib.parse import urljoin

BASE = "https://www.epravda.com.ua"
FINANCES_URL = "https://www.epravda.com.ua/finances/"

UA_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}

def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def _parse_ua_date(text: str) -> date | None:
    if not text:
        return None
    t = text.strip().lower()
    if "," in t:
        t = t.split(",", 1)[0].strip()
    parts = t.split()
    if len(parts) < 2:
        return None
    try:
        day = int(parts[0])
        month = UA_MONTHS.get(parts[1])
        if not month:
            return None
        return date(date.today().year, month, day)
    except Exception:
        return None

def _collect_finances(soup: BeautifulSoup) -> list[dict]:
    today = date.today()
    yesterday = today - timedelta(days=1)
    items = []
    for news in soup.select(".article_news"):
        a = news.select_one(".article_title a")
        d = news.select_one(".article_date")
        if not a:
            continue
        title = a.get_text(strip=True)
        url = urljoin(BASE, a.get("href", "").strip())
        date_str = d.get_text(strip=True) if d else ""
        dt = _parse_ua_date(date_str)
        if dt in (today, yesterday):
            items.append({
                "title": title,
                "url": url,
                "date": dt.strftime("%Y-%m-%d"),
                "source": "https://epravda.com.ua/finances",
                "section": "finances",
            })
    return items

def parse_epravda() -> list[dict]:
    print("🔹 Парсимо Epravda...")

    soup_fin = _fetch(FINANCES_URL)
    fin_items = _collect_finances(soup_fin)

    all_found = fin_items
    seen = set()
    unique = []
    for n in all_found:
        if n["url"] not in seen:
            unique.append(n)
            seen.add(n["url"])

    print("\n✅ epravda - результат:")
    print(f"   Усього знайдено {len(all_found)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(unique)}\n")

    print(f"Джерело: https://epravda.com.ua/finances — {len(fin_items)} новин:")
    for i, n in enumerate(fin_items, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
    print()

    return unique

if __name__ == "__main__":
    try:
        parse_epravda()
    except Exception as e:
        print(f"❌ Помилка epravda_parser: {e}")