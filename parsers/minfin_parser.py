# parsers/minfin_parser.py
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}

BASE_URL = "https://minfin.com.ua"

SECTIONS = [       
    "ua/news/money-management/",    # ← головна UA-стрічка (замість /news/)
    "ua/news/commerce/",
    "ua/news/improvement/",
    "ua/news/",   
]


def _normalize_url(u: str) -> str:
    """Приводимо URL до канонічного вигляду для коректної унікалізації."""
    u = u.strip()
    if not u.startswith("http"):
        u = BASE_URL + u
    s = urlsplit(u)
    netloc = s.netloc.lower()
    path = s.path.rstrip("/")  # зрізаємо фінальний слеш
    # прибираємо query і fragment
    return urlunsplit((s.scheme, netloc, path, "", ""))


def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_minfin():
    all_news = []
    per_source_raw = []  # [(src_url, [items_raw]), ...]

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    target_dates = {today, yesterday}

    print("🔹 Парсимо Minfin...")

    # 1) Збирання по джерелах (RAW, без друку)
    for section in SECTIONS:
        src_url = f"{BASE_URL}/{section.strip('/')}/"
        items_raw = []

        try:
            soup = _fetch(src_url)
        except Exception as e:
            print(f"⚠️ Не вдалося отримати {src_url}: {e}")
            per_source_raw.append((src_url, items_raw))
            continue

        for item in soup.select("li.item"):
            date_tag = item.select_one("span.data")
            title_tag = item.select_one("a")
            if not date_tag or not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "").strip()
            raw_date = (date_tag.get("content") or date_tag.get_text(strip=True) or "").strip()

            # Парсимо дату у форматах YYYY-MM-DD або DD.MM.YYYY (беремо тільки дату без часу)
            news_date = None
            parts0 = raw_date.split()
            if parts0:
                token = parts0[0]
                try:
                    news_date = datetime.strptime(token, "%Y-%m-%d").date()
                except Exception:
                    try:
                        news_date = datetime.strptime(token, "%d.%m.%Y").date()
                    except Exception:
                        news_date = None
            if news_date not in target_dates:
                continue

            url_norm = _normalize_url(href)
            item_obj = {
                "title": title,
                "url": url_norm,
                "date": str(news_date),
                "source": src_url,
            }
            items_raw.append(item_obj)
            all_news.append(item_obj)

        per_source_raw.append((src_url, items_raw))

    # 2) Глобальна унікалізація по нормалізованому URL
    seen = set()
    unique_news = []
    for news in all_news:
        if news["url"] not in seen:
            unique_news.append(news)
            seen.add(news["url"])

    # 3) Друк результатів БЕЗ дублювання між джерелами
    total_with_dups = len(all_news)
    total_unique = len(unique_news)
    print(f"\n✅ minfin - результат:")
    print(f"   Усього знайдено {total_with_dups} (з урахуванням дублів)")
    print(f"   Унікальних новин: {total_unique}\n")

    printed_urls = set()
    for src_url, items_raw in per_source_raw:
        # залишаємо для друку тільки ті, яких ще не друкували
        to_print = []
        for it in items_raw:
            if it["url"] in printed_urls:
                continue
            to_print.append(it)
            printed_urls.add(it["url"])

        print(f"🟢Джерело: {src_url} — {len(to_print)} новин:")
        for i, n in enumerate(to_print, 1):
            print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
        print()

    return unique_news


if __name__ == "__main__":
    try:
        parse_minfin()
    except Exception as e:
        print(f"❌ Помилка minfin_parser: {e}")