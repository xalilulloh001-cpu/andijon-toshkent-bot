import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from handlers import common, passenger, driver, admin

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=BOT_TOKEN)

    # Redis mavjud bo'lsa RedisStorage, bo'lmasa MemoryStorage
    if REDIS_URL:
        storage = RedisStorage.from_url(REDIS_URL)
        logger.info("✅ RedisStorage ishlatilmoqda")
    else:
        storage = MemoryStorage()
        logger.warning("⚠️  MemoryStorage ishlatilmoqda (production uchun REDIS_URL qo'shing)")

    dp = Dispatcher(storage=storage)

    dp.include_router(common.router)
    dp.include_router(passenger.router)
    dp.include_router(driver.router)
    dp.include_router(admin.router)

    await db.init_db()
    logger.info("✅ Database initialized")

    logger.info("🚀 Bot started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
