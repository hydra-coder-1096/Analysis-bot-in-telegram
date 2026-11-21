from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_from_docx(path: Path) -> str:
    document = Document(path)

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return "\n".join(paragraphs)


def extract_from_pdf(path: Path) -> str:
    reader = PdfReader(path)

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text.strip())

    return "\n\n".join(pages)


def extract_from_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1251")


def extract_text(path: Path) -> str:
    extension = path.suffix.lower()

    if extension == ".docx":
        return extract_from_docx(path)

    if extension == ".pdf":
        return extract_from_pdf(path)

    if extension == ".txt":
        return extract_from_txt(path)

    raise ValueError(
        f"Неподдерживаемый формат файла: {extension}"
    )