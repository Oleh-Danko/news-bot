import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groups.easy_sources import run_all

BOT_TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = "https://universal-bot-live.onrender.com" + WEBHOOK_PATH

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("👋 Привіт! Надішли /news — отримаєш актуальні новини з Економічної Правди (розділ «Фінанси»).")

@dp.message(Command("news"))
async def news_easy_cmd(message: types.Message):
    await message.answer("⏳ Збираю новини з Epravda /finances …")
    try:
        results = run_all()
        if not results:
            await message.answer("⚠️ Новини не знайдено.")
            return

        text = "Epravda (Finances)\n"
        for n in results[:20]:
            text += f"• {n['title']} ({n['url']})\n"
        await message.answer(text, disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

async def handle_webhook(request):
    update = await request.json()
    await dp.feed_webhook_update(bot, update)
    return web.Response()

def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, port=8080)

if __name__ == "__main__":
    main()