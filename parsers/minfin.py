#ЗАГЛУШКА
def parse_minfin():
    print("ℹ️ Парсер Minfin поки не налаштований")
    return []


#КОД
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def parse_minfin():
    base_url = "https://minfin.com.ua"
    sections = [
        "news",
        "ua/news/money-management/",
        "ua/news/commerce/",
        "ua/news/improvement/"
    ]

    all_news = []
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    target_dates = [today, yesterday]

    for section in sections:
        url = f"{base_url}/{section}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"⚠️ Не вдалося отримати {url}: {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("li.item")

        for item in items:
            date_tag = item.select_one("span.data")
            title_tag = item.select_one("a")
            if not date_tag or not title_tag:
                continue

            title = title_tag.text.strip()
            link = title_tag["href"]
            if not link.startswith("http"):
                link = base_url + link

            # Отримання дати з атрибуту content або тексту
            raw_date = (
                date_tag.get("content")
                or date_tag.text.strip().replace(" ", " ")
            )

            try:
                news_date = datetime.strptime(
                    raw_date.split()[0], "%Y-%m-%d"
                ).date()
            except Exception:
                # Якщо формат не ISO — спробуємо інший варіант
                try:
                    news_date = datetime.strptime(
                        raw_date.split()[0], "%d.%m.%Y"
                    ).date()
                except Exception:
                    continue

            if news_date not in target_dates:
                continue

            all_news.append({
                "title": title,
                "url": link,
                "date": str(news_date),
                "source": url
            })

    # Видалення дублів за URL
    unique_news = []
    seen = set()
    for news in all_news:
        if news["url"] not in seen:
            unique_news.append(news)
            seen.add(news["url"])

    print(f"\n✅ Результат:")
    print(f"   Усього знайдено {len(all_news)} (з урахуванням дублів)")
    print(f"   Унікальних новин: {len(unique_news)}\n")

    for i, n in enumerate(unique_news, 1):
        print(f"{i}. {n['title']} ({n['date']})\n   {n['url']}\n   Джерело: {n['source']}")

    return unique_news


if __name__ == "__main__":
    parse_minfin()