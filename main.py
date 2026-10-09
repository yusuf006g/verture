import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.handlers import router
from bot.database import init_db


async def main() -> None:
    if not settings.bot_token or settings.bot_token == "PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Не задан BOT_TOKEN. Скопируй .env.example в .env и вставь токен BotFather."
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    await init_db()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    logging.info("Trucking Loads Assistant запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
