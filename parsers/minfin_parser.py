# parsers/minfin_parser.py
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def parse_minfin():
    base_url = "https://minfin.com.ua"
    sections = [
        "ua/news/",                  # було: "news"
        "ua/news/money-management/",
        "ua/news/commerce/",
        "ua/news/improvement/"
    ]

    all_news = []
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    target_dates = [today, yesterday]

    per_source = []

    print("🔹 Парсимо Minfin...")

    for section in sections:
        url = f"{base_url}/{section}"
        section_news = []
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            print(f"⚠️ Не вдалося отримати {url}: {e}")
            continue

        items = soup.select("li.item")

        for item in items:
            date_tag = item.select_one("span.data")
            title_tag = item.select_one("a")
            if not date_tag or not title_tag:
                continue

            title = title_tag.text.strip()
            link = title_tag.get("href", "")
            if not link.startswith("http"):
                link = base_url + link

            raw_date = (
                date_tag.get("content")
                or date_tag.text.strip().replace(" ", " ")
            )

            try:
                news_date = datetime.strptime(raw_date.split()[0], "%Y-%m-%d").date()
            except Exception:
                try:
                    news_date = datetime.strptime(raw_date.split()[0], "%d.%m.%Y").date()
                except Exception:
                    continue

            if news_date not in target_dates:
                continue

            news_item = {
                "title": title,
                "url": link,
                "date": str(news_date),
                "source": url
            }

            section_news.append(news_item)
            all_news.append(news_item)

        per_source.append((url, section_news))

    # Унікалізація за URL
    seen = set()
    unique_news = []
    for news in all_news:
        if news["url"] not in seen:
            unique_news.append(news)
            seen.add(news["url"])

    # Вивід у форматі epravda/minfin
    total_with_dups = len(all_news)
    total_unique = len(unique_news)
    print(f"\n✅ minfin - результат:")
    print(f"   Усього знайдено {total_with_dups} (з урахуванням дублів)")
    print(f"   Унікальних новин: {total_unique}\n")

    for src_url, news_list in per_source:
        print(f"Джерело: {src_url} — {len(news_list)} новин:")
        for i, n in enumerate(news_list, 1):
            print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}")
        print()

    return unique_news


if __name__ == "__main__":
    try:
        parse_minfin()
    except Exception as e:
        print(f"❌ Помилка minfin_parser: {e}")