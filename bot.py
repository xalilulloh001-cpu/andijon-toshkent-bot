import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from handlers import common, passenger, driver, admin

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Routerlarni ulash
    dp.include_router(common.router)
    dp.include_router(passenger.router)
    dp.include_router(driver.router)
    dp.include_router(admin.router)

    # Ma'lumotlar bazasini ishga tushirish
    await db.init_db()
    logger.info("✅ Database initialized")

    # Botni ishga tushirish
    logger.info("🚀 Bot started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
