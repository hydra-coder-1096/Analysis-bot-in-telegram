import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

from document_processor import extract_text
from ai import ask_ai


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")


dp = Dispatcher()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".txt"}

# Основной документ исследовательского проекта
PROJECT_FILE = DATA_DIR / "2142163440" / "Бондаренко проект 15.09.26.txt"
DEFAULT_DOCUMENT = PROJECT_FILE.read_text(encoding="utf-8").strip()

if not DEFAULT_DOCUMENT:
    raise RuntimeError("Текст основного проекта пуст")

    # Документы пользователей
    user_documents: dict[int, str] = {}


@dp.message(CommandStart())
async def start_handler(message: Message):
    user_id = message.from_user.id
    user_documents[user_id] = DEFAULT_DOCUMENT

    await message.answer(
        "Привет! 👋\\n\\n"
        "Я помощник по твоему исследовательскому проекту "
        "о философии Марка Цицерона и поколении Z.\\n\\n"
        "Я уже загрузил текст проекта. Можешь сразу задавать "
        "вопросы о целях, методах, результатах опроса и выводах."
    )


@dp.message()
async def message_handler(message: Message):
    user_id = message.from_user.id

    # Если пользователь отправил документ
    if message.document:
        filename = message.document.file_name or "document"
        extension = Path(filename).suffix.lower()

        if extension not in SUPPORTED_EXTENSIONS:
            await message.answer(
                "Я пока поддерживаю только:\n"
                "• .docx\n"
                "• .pdf\n"
                "• .txt"
            )
            return

        user_dir = DATA_DIR / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        file_path = user_dir / filename

        await message.answer("📄 Получил документ. Извлекаю текст...")

        try:
            await message.bot.download(
                message.document,
                destination=file_path
            )

            text = extract_text(file_path)

            if not text.strip():
                await message.answer(
                    "Я получил файл, но не смог найти в нём текст."
                )
                return

            text_path = file_path.with_suffix(".txt")
            text_path.write_text(text, encoding="utf-8")

            user_documents[user_id] = text

            await message.answer(
                f"✅ Документ обработан.\n\n"
                f"Файл: {filename}\n"
                f"Извлечено символов: {len(text):,}\n\n"
                f"Теперь задавай вопросы по документу."
            )

        except Exception as error:
            print(f"Ошибка обработки {filename}: {error}")

            await message.answer(
                "❌ Не удалось обработать документ.\n"
                "Проверь, что файл не повреждён."
            )

        return

    # Если пользователь задал вопрос
    if message.text:
        document_text = user_documents.get(user_id)

        if not document_text:
            await message.answer(
                "Сначала отправь мне документ .docx, .pdf или .txt."
            )
            return

        await message.answer("🤖 Анализирую документ...")

        try:
            answer = await ask_ai(
                question=message.text,
                document_text=document_text
            )

            await message.answer(answer)

        except Exception as error:
            print(f"Ошибка OpenAI: {error}")

            await message.answer(
                "❌ Не удалось получить ответ от AI."
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
