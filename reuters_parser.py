import requests
import xml.etree.ElementTree as ET

RSS_URL = "https://news.google.com/rss/search?q=site:reuters.com/business&hl=en&gl=US&ceid=US:en"

def fetch_rss(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_rss(xml_text):
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")

    news_list = []
    for item in items:
        title = item.findtext("title")
        link = item.findtext("link")
        if title and link:
            news_list.append({"title": title.strip(), "link": link.strip()})
    return news_list

def main():
    print("🔍 Завантажую новини з Reuters (через Google News RSS)...")
    try:
        xml = fetch_rss(RSS_URL)
        news = parse_rss(xml)
        if not news:
            print("⚠️ Не знайдено жодної новини.")
        else:
            print(f"✅ Знайдено {len(news)} новин:\n")
            for n in news[:30]:
                print(f"• {n['title']}\n  {n['link']}\n")
    except Exception as e:
        print(f"❌ Помилка під час отримання або обробки RSS: {e}")

if __name__ == "__main__":
    main()