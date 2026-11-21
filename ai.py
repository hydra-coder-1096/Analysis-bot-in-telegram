import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY не найден в .env")

client = genai.Client(api_key=API_KEY)


async def ask_ai(question: str, document_text: str) -> str:
    prompt = (
        "Ты помощник по работе с проектными документами. "
        "Отвечай на вопрос строго на основе текста документа. "
        "Если информации недостаточно, честно скажи об этом. "
        "Не выдумывай факты.\n\n"
        f"ТЕКСТ ДОКУМЕНТА:\n{document_text}\n\n"
        f"ВОПРОС:\n{question}"
    )

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError("Gemini вернул пустой ответ")

    return response.text
