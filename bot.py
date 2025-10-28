import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from live_parser import run_all, format_news  # імпортуй свою логіку парсера

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не знайдено в змінних середовища!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("👋 Привіт! Надішли /news — отримаєш актуальні новини з Економічної Правди (розділ «Фінанси»).")


@dp.message(Command("news"))
async def news_cmd(message: types.Message):
    await message.answer("⏳ Збираю новини з Epravda /finances …")
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


async def on_startup(app: web.Application):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook встановлено: {WEBHOOK_URL}")
    else:
        print("⚠️ WEBHOOK_URL не задано — бот працює в локальному режимі.")


async def on_shutdown(app: web.Application):
    await bot.session.close()


def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()