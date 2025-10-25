import asyncio
import logging
import cloudscraper
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logger = logging.getLogger("BloombergParser")

async def fetch_bloomberg(top_n=5):
    url = "https://www.bloomberg.com/markets"
    articles = []

    # 1️⃣ cloudscraper first
    try:
        scraper = cloudscraper.create_scraper()
        html = scraper.get(url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select("a[data-type='article']")[:top_n]:
            title = tag.get_text(strip=True)
            link = tag.get("href")
            if link and not link.startswith("http"):
                link = "https://www.bloomberg.com" + link
            articles.append({"title": title, "link": link})
        if articles:
            logger.info(f"✅ Bloomberg parsed via cloudscraper ({len(articles)} items)")
            return articles
    except Exception as e:
        logger.warning(f"⚠️ Cloudscraper failed: {e}")

    # 2️⃣ fallback to Playwright
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page()
            await page.goto(url, timeout=20000)
            await asyncio.sleep(3)
            content = await page.content()
            await browser.close()

            soup = BeautifulSoup(content, "html.parser")
            for tag in soup.select("a[data-type='article']")[:top_n]:
                title = tag.get_text(strip=True)
                link = tag.get("href")
                if link and not link.startswith("http"):
                    link = "https://www.bloomberg.com" + link
                articles.append({"title": title, "link": link})

        logger.info(f"✅ Bloomberg parsed via Playwright ({len(articles)} items)")
        return articles

    except Exception as e:
        logger.error(f"❌ Playwright failed: {e}")
        return []