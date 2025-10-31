# parsers/coindesk_parser.py
import json
import re
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.coindesk.com"
LIST_URL = "https://www.coindesk.com/latest-crypto-news"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

KYIV_TZ = ZoneInfo("Europe/Kyiv")


def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


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
        # Спроба вирізати дату з початку рядка: 2025-10-30
        m = re.match(r"(\d{4}-\d{2}-\d{2})", iso_str)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                return None
        return None


def _extract_published_date_from_meta(soup: BeautifulSoup) -> date | None:
    # Пошук у meta-тегах
    meta_names = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"itemprop": "datePublished"}),
        ("time", {"datetime": True}),
    ]
    for tag, attrs in meta_names:
        el = soup.find(tag, attrs=attrs) if attrs else soup.find(tag)
        if not el:
            continue
        content = el.get("content") or el.get("datetime") or el.get_text(strip=True)
        d = _iso_to_local_date(content)
        if d:
            return d
    return None


def _extract_from_json_ld(soup: BeautifulSoup) -> tuple[str | None, date | None]:
    # CoinDesk зазвичай вкладає JSON-LD з типом NewsArticle/Article
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue

        # Дані можуть бути словником або списком
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type") or obj.get("type") or ""
            if isinstance(t, list):
                types = [x.lower() for x in t if isinstance(x, str)]
            else:
                types = [str(t).lower()]

            if any(x in ("newsarticle", "article", "reportagenewsarticle", "liveblogposting") for x in types):
                title = obj.get("headline") or obj.get("name") or None
                published = obj.get("datePublished") or obj.get("dateCreated") or obj.get("dateModified")
                pub_date = _iso_to_local_date(published) if published else None
                if title or pub_date:
                    return title, pub_date
    return None, None


def _is_probable_article_link(url: str) -> bool:
    # Відсікаємо зовнішні та службові посилання
    try:
        u = urlparse(url)
        if u.netloc and u.netloc not in ("", "www.coindesk.com", "coindesk.com"):
            return False
        path = u.path or ""
        # Залишаємо типові розділи матеріалів і рік/місяць
        # Напр.: /markets/2025/10/30/slug/
        if re.search(r"/(markets|policy|tech|business|focus|news)/", path) and re.search(r"/20\d{2}/\d{2}/\d{2}/", path):
            return True
        # Деякі матеріали можуть не містити дати в URL — залишимо запасний варіант:
        return path.count("/") >= 3 and not path.endswith(("/", "/latest-crypto-news"))
    except Exception:
        return False


def _collect_article_links(list_soup: BeautifulSoup, limit: int = 80) -> list[str]:
    links = []
    seen = set()
    for a in list_soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/"):
            url = urljoin(BASE, href)
        elif href.startswith("http"):
            if "coindesk.com" not in href:
                continue
            url = href
        else:
            continue

        if url in seen:
            continue
        if _is_probable_article_link(url):
            seen.add(url)
            links.append(url)
        if len(links) >= limit:
            break
    return links


def parse_coindesk() -> list[dict]:
    print("🔹 Парсимо CoinDesk...")

    today = datetime.now(tz=KYIV_TZ).date()
    yesterday = today - timedelta(days=1)
    target_dates = {today, yesterday}

    list_soup = _fetch(LIST_URL)
    candidates = _collect_article_links(list_soup, limit=100)

    items = []
    for url in candidates:
        try:
            art_soup = _fetch(url)
        except Exception:
            continue

        title, pub_date = _extract_from_json_ld(art_soup)

        if not pub_date:
            pub_date = _extract_published_date_from_meta(art_soup)

        if not title:
            # Фолбек: заголовок із <title>, обрізаємо « | CoinDesk»
            t = (art_soup.title.string or "").strip() if art_soup.title else ""
            title = re.sub(r"\s*\|\s*CoinDesk\s*$", "", t) or "Без назви"

        if not pub_date or pub_date not in target_dates:
            continue

        items.append(
            {
                "title": title.strip(),
                "url": url,
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": LIST_URL,
                "section": "coindesk",
            }
        )

    # Дедуп за URL
    seen = set()
    unique = []
    for n in items:
        if n["url"] in seen:
            continue
        seen.add(n["url"])
        unique.append(n)

    print("\n✅ coindesk - результат:")
    print(f"   Усього знайдено {len(items)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(unique)}\n")

    print(f"Джерело: {LIST_URL} — {len(unique)} новин:")
    for i, n in enumerate(unique, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
    print()

    return unique


if __name__ == "__main__":
    try:
        parse_coindesk()
    except Exception as e:
        print(f"❌ Помилка coindesk_parser: {e}")