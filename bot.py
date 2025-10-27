import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groups.easy_sources import run_all

# === 🔐 Твій токен ===
BOT_TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"

# === Ініціалізація ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def format_news(results):
    """Форматування списку новин для Telegram."""
    if not results:
        return "⚠️ Новини за сьогодні та вчора не знайдено."

    grouped = {}
    for item in results:
        source = item.get("source", "невідоме джерело")
        grouped.setdefault(source, []).append(item)

    text = "✅ Результат:\n"
    for src, news_list in grouped.items():
        text += f"\n🔹 Джерело: {src}\n"
        for i, n in enumerate(news_list, 1):
            title = n.get("title", "—")
            date = n.get("date", "—")
            url = n.get("url", "")
            text += f"{i}. {title} ({date})\n   {url}\n"
    return text


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Вітаю! Я новинний бот.\n\n"
        "Доступні команди:\n"
        "• /news_easy — новини з легких джерел (Epravda, Minfin)\n"
        "• /news_medium — (поки в розробці)\n"
        "• /news_hard — (поки в розробці)"
    )


@dp.message(Command("news_easy"))
async def news_easy_cmd(message: types.Message):
    await message.answer("⏳ Збираю свіжі новини... Це може зайняти до 10 секунд.")
    try:
        results = run_all()
        text = format_news(results)

        if len(text) > 4000:
            parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.answer(part, disable_web_page_preview=True)
        else:
            await message.answer(text, disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка під час збору новин: {e}")


async def main():
    print("✅ Bot started successfully")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())