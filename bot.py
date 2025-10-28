import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groups.easy_sources import run_all

BOT_TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"
WEBHOOK_URL = "https://universal-bot-live.onrender.com"
ADMIN_ID = 6680030792

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привіт! Надішли /news — отримаєш актуальні новини з ЕП."
    )


@dp.message(Command("news"))
async def news_cmd(message: types.Message):
    await message.answer("⏳ Збираю новини з Epravda /finances …")
    try:
        results = run_all()
        if not results:
            await message.answer("⚠️ Новини за сьогодні та вчора не знайдено.")
            return

        text = f"Epravda (Finances)\n"
        for i, n in enumerate(results, 1):
            text += f"• {n['title']} ({n['url']})\n"
        await message.answer(text[:4000], disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")


async def handle_health(request):
    return web.json_response({"status": "alive"})


async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")


async def webhook_handler(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="ok")


def main():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/webhook", webhook_handler)
    app.on_startup.append(on_startup)

    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()