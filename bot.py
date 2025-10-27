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