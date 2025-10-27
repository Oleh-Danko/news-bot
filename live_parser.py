import requests
from bs4 import BeautifulSoup

def parse_finances():
    print("🔍 Завантажую розділ finances...")
    url = "https://www.epravda.com.ua/finances/"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.select("div.article_news, div.article.article_view_sm")

    results = []
    for article in articles:
        title_tag = article.select_one(".article_title a")
        if title_tag:
            title = title_tag.text.strip()
            link = title_tag["href"].strip()
            results.append({
                "title": title,
                "link": link,
                "section": "finances"
            })
    return results


def parse_columns():
    print("🔍 Завантажую розділ columns...")
    url = "https://www.epravda.com.ua/columns/"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.select("div.article.article_view_sm")

    results = []
    for article in articles:
        title_tag = article.select_one(".article_title a")
        author_tag = article.select_one(".article_name")
        if title_tag:
            title = title_tag.text.strip()
            link = title_tag["href"].strip()
            author = author_tag.text.strip() if author_tag else "Автор не вказаний"
            results.append({
                "title": title,
                "link": link,
                "author": author,
                "section": "columns"
            })
    return results


def main():
    print("🔍 Завантажую свіжі новини з epravda.com.ua...\n")

    finances_news = parse_finances()
    columns_news = parse_columns()

    print("\n✅ Результати парсингу:\n")

    # --- Finances ---
    print(f"📂 FINANCES — знайдено {len(finances_news)} статей:")
    for item in finances_news[:10]:
        print(f"• {item['title']}\n  {item['link']}\n")

    # --- Columns ---
    print(f"\n📂 COLUMNS — знайдено {len(columns_news)} статей:")
    for item in columns_news[:10]:
        author_info = f" — {item['author']}" if item.get("author") else ""
        print(f"• {item['title']}\n  {item['link']}{author_info}\n")


if __name__ == "__main__":
    main()