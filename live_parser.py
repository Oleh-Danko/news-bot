import aiohttp
from bs4 import BeautifulSoup
import logging

log = logging.getLogger("news-bot")
EP_URL = "https://www.epravda.com.ua/finances/"

async def fetch_epravda_news():
    articles = []
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EP_URL, headers=headers, timeout=20) as resp:
                if resp.status != 200:
                    log.warning(f"Epravda fetch failed: {resp.status}")
                    return []
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                blocks = soup.find_all("article")
                for block in blocks:
                    a_tag = block.find("a", href=True)
                    if not a_tag:
                        continue
                    title = a_tag.get_text(strip=True)
                    link = a_tag["href"]
                    if not link.startswith("https://www.epravda.com.ua/finances/"):
                        if link.startswith("/finances/"):
                            link = "https://www.epravda.com.ua" + link
                        else:
                            continue
                    desc = block.find("p")
                    description = desc.get_text(strip=True) if desc else None
                    articles.append({
                        "title": title,
                        "link": link,
                        "description": description,
                        "source": "Epravda (Finances)"
                    })
        log.info(f"✅ Parsed {len(articles)} articles from Epravda.")
        return articles
    except Exception as e:
        log.error(f"Epravda error: {e}")
        return []