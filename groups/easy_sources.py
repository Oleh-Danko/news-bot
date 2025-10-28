import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groups.easy_sources import run_all

BOT_TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привіт! Надішли /news — отримаєш актуальні новини з Економічної Правди (розділ «Фінанси»)."
    )


@dp.message(Command("news"))
async def news_easy_cmd(message: types.Message):
    await message.answer("⏳ Збираю новини з Epravda /finances …")
    try:
        results = run_all()
        if not results:
            await message.answer("⚠️ Новини не знайдені.")
            return

        text = ""
        for i, n in enumerate(results, 1):
            text += f"{i}. {n['title']} ({n['date']})\n{n['url']}\n\n"

        # Ділимо на частини, щоб не перевищувати 4096 символів
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part, disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка під час збору новин: {e}")


async def main():
    print("✅ Bot started successfully")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())