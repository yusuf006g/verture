import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from pypdf import PdfReader
from PIL import Image
import pytesseract

from bot.config import settings
from bot.parser import parse_load, format_load
from bot.database import save_load, latest_loads, search_loads
from bot.translate import translate_text
from bot.exporter import export_excel

router = Router()
logger = logging.getLogger(__name__)
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

HELP = (
    "<b>Команды Trucking Loads Assistant</b>\n"
    "/start — начать\n"
    "/help — помощь\n"
    "/loads — последние сохранённые рейсы\n"
    "/search 2327 — поиск по Trip # или Ref #\n"
    "/export — выгрузить базу в Excel\n\n"
    "Отправь текст, перешли сообщение QM NOTIFIER, фотографию или PDF."
)

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я разбираю trucking loads из QM NOTIFIER, сохраняю оригинал и поля, "
        "перевожу текст и конвертирую мили в километры.\n\n" + HELP
    )

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP)

async def process_text(message: Message, text: str):
    if not text or not text.strip():
        await message.answer("Не удалось получить текст. Отправь текстовое сообщение, изображение или PDF.")
        return
    load = parse_load(text)
    record_id = await save_load(message.from_user.id if message.from_user else 0, load)
    card = format_load(load)
    await message.answer(card)
    await message.answer(
        f"💾 Сохранено в базе. ID записи: <code>{record_id}</code>\n"
        "Оригинал сообщения сохранён. Используй /export для Excel."
    )
    # The concise load card is already in Russian; avoid sending a second, lengthy translation.

@router.message(F.photo)
async def photo_handler(message: Message, bot):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    if file_info.file_size and file_info.file_size > MAX_DOWNLOAD_BYTES:
        await message.answer("Файл слишком большой для MVP (лимит 20 МБ).")
        return
    path = Path("data") / f"photo_{photo.file_unique_id}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await bot.download_file(file_info.file_path, destination=path)
        try:
            extracted = pytesseract.image_to_string(Image.open(path), lang="eng")
        except Exception as exc:
            logger.warning("OCR error: %s", exc)
            await message.answer(
                "Не удалось выполнить OCR. Установи Tesseract командой `brew install tesseract`, "
                "а затем отправь фото ещё раз.", parse_mode=None
            )
            return
        if not extracted.strip():
            await message.answer("OCR не нашёл текст на изображении. Попробуй отправить более чёткий скриншот.")
            return
        await process_text(message, extracted)
    finally:
        path.unlink(missing_ok=True)

@router.message(F.document)
async def document_handler(message: Message, bot):
    doc = message.document
    name = (doc.file_name or "").lower()
    if doc.file_size and doc.file_size > MAX_DOWNLOAD_BYTES:
        await message.answer("Файл слишком большой для MVP (лимит 20 МБ).")
        return
    if not (name.endswith(".pdf") or name.endswith(".txt")):
        await message.answer("Пока поддерживаются PDF, TXT и изображения. Другие форматы пока не поддерживаются.")
        return
    file_info = await bot.get_file(doc.file_id)
    path = Path("data") / f"upload_{doc.file_unique_id}_{Path(name).name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await bot.download_file(file_info.file_path, destination=path)
        if name.endswith(".txt"):
            extracted = path.read_text(encoding="utf-8", errors="replace")
        else:
            reader = PdfReader(str(path))
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not extracted.strip():
            await message.answer("В PDF не найден выделяемый текст. Сканированный PDF пока нужно преобразовать в изображение и отправить отдельно.")
            return
        await process_text(message, extracted)
    except Exception:
        logger.exception("Не удалось обработать файл")
        await message.answer("Не удалось обработать файл. Проверь, что PDF/TXT не повреждён.")
    finally:
        path.unlink(missing_ok=True)

@router.message(F.text & ~F.text.startswith("/"))
async def text_handler(message: Message):
    await process_text(message, message.text)

@router.message(Command("loads"))
async def loads_cmd(message: Message):
    loads = await latest_loads(10)
    if not loads:
        await message.answer("Пока нет сохранённых рейсов.")
        return
    lines = ["<b>Последние рейсы:</b>"]
    for load in loads:
        lines.append(
            f"• ID {load.get('_id')} — Trip #{load.get('trip_number') or 'Не указано'}; "
            f"Ref #{load.get('reference_number') or 'Не указано'}; "
            f"{load.get('commodity') or 'Груз не указан'}"
        )
    await message.answer("\n".join(lines))

@router.message(Command("search"))
async def search_cmd(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /search 2327")
        return
    results = await search_loads(parts[1])
    if not results:
        await message.answer("Ничего не найдено.")
        return
    for load in results[:5]:
        await message.answer(format_load(load))

@router.message(Command("export"))
async def export_cmd(message: Message):
    try:
        path = await export_excel()
        await message.answer_document(FSInputFile(path, filename="trucking_loads.xlsx"), caption="Экспорт сохранённых рейсов в Excel")
    except Exception:
        logger.exception("Excel export failed")
        await message.answer("Не удалось создать Excel-файл.")
