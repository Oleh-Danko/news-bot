#ЗАГЛУШКА
def parse_epravda():
    print("ℹ️ Парсер Epravda поки не налаштований")
    return []


#КОД
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
from urllib.parse import urljoin

BASE = "https://www.epravda.com.ua"
SOURCES = [
    "https://www.epravda.com.ua/finances/",
    "https://www.epravda.com.ua/columns/",
]

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
    """
    Очікує рядки типу:
    - '27 жовтня, 12:30'
    - '26 жовтня, 18:00'
    Повертає date або None, якщо не вдалось розпарсити.
    """
    if not text:
        return None
    t = text.strip().lower()
    # прибираємо все після коми (час)
    if "," in t:
        t = t.split(",", 1)[0].strip()
    parts = t.split()
    if len(parts) < 2:
        return None
    try:
        day = int(parts[0])
        month_name = parts[1]
        month = UA_MONTHS.get(month_name)
        if not month:
            return None
        # рік на сторінці не вказаний — беремо поточний
        year = date.today().year
        return date(year, month, day)
    except Exception:
        return None

def _collect_finances(soup: BeautifulSoup) -> list[dict]:
    """
    З finances беремо ЛИШЕ сьогодні та вчора.
    Селектори: блоки .article_news (у них є .article_title a і .article_date)
    """
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

        # фільтр: тільки сьогодні та вчора
        if dt in (today, yesterday):
            items.append({
                "title": title,
                "url": url,
                "date": dt.strftime("%Y-%m-%d") if dt else "—",
                "source": "https://epravda.com.ua/finances",
                "section": "finances",
            })
    return items

def _collect_columns(soup: BeautifulSoup) -> list[dict]:
    """
    З columns беремо ВСЕ (дат немає).
    Типові елементи: .article.article_view_sm або просто .article_title a
    """
    items = []
    # Перший прохід: структуровані картки
    for card in soup.select(".article.article_view_sm"):
        a = card.select_one(".article_title a")
        if not a:
            continue
        title = a.get_text(strip=True)
        url = urljoin(BASE, a.get("href", "").strip())
        items.append({
            "title": title,
            "url": url,
            "date": "—",
            "source": "https://epravda.com.ua/columns",
            "section": "columns",
        })

    # Додатковий прохід: якщо раптом є заголовки поза .article_view_sm
    # (щоб не пропустити нічого)
    for a in soup.select(".article_title a"):
        title = a.get_text(strip=True)
        url = urljoin(BASE, a.get("href", "").strip())
        if not any(x["url"] == url for x in items):
            items.append({
                "title": title,
                "url": url,
                "date": "—",
                "source": "https://epravda.com.ua/columns",
                "section": "columns",
            })

    return items

def parse_epravda() -> list[dict]:
    """
    Повертає список новин (словники) з двох джерел:
    - finances — тільки сьогодні та вчора,
    - columns — усі.
    Також друкує результат у стилі Minfin.
    """
    all_found = []
    per_source_print = []

    print("🔹 Парсимо Epravda...")

    # --- FINANCES ---
    url_fin = SOURCES[0]
    soup_fin = _fetch(url_fin)
    fin_items = _collect_finances(soup_fin)
    per_source_print.append(("https://epravda.com.ua/finances", fin_items))

    # --- COLUMNS ---
    url_col = SOURCES[1]
    soup_col = _fetch(url_col)
    col_items = _collect_columns(soup_col)
    per_source_print.append(("https://epravda.com.ua/columns", col_items))

    # Загальний список (з урахуванням дублів)
    all_found = fin_items + col_items

    # Унікальність за URL
    seen = set()
    unique = []
    for n in all_found:
        if n["url"] not in seen:
            unique.append(n)
            seen.add(n["url"])

    # Вивід по кожному джерелу (як ти просив)
    total_with_dups = len(all_found)
    total_unique = len(unique)
    print(f"\n✅ epravda - результат:")
    print(f"   Усього знайдено {total_with_dups} (з урахуванням дублів)")
    print(f"   Унікальних новин: {total_unique}\n")

    global_index = 1
    for src_url, items in per_source_print:
        print(f"Джерело: {src_url} — {len(items)} новин:")
        for i, n in enumerate(items, 1):
            print(f"{global_index}. {n['title']} ({n['date']})\n   {n['url']}")
            global_index += 1
        print()  # порожній рядок між джерелами

    return unique

if __name__ == "__main__":
    try:
        parse_epravda()
    except Exception as e:
        print(f"❌ Помилка epravda_parser: {e}")