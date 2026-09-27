import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")


dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Привет! 👋\n\n"
        "Я бот для анализа документов.\n"
        "Отправь мне документ, и я смогу отвечать "
        "на вопросы по его содержанию."
    )


@dp.message()
async def message_handler(message: Message):
    await message.answer(
        "Я получил сообщение. Обработку документов "
        "подключим следующим этапом."
    )


async def main():
    bot = Bot(token=BOT_TOKEN)

    print("Бот запущен!")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())