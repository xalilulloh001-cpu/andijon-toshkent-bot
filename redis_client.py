"""
AndTaxi - Redis Client
SMS rate-limiting va PIN lockout uchun
"""
import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# redis kutubxonasidan foydalanish
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ redis kutubxonasi topilmadi — rate limiting ishlaydi xotirada")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Redis ulanmagan holda xotiradagi zaxira (fallback)
_memory_store: dict = {}


class RedisClient:
    def __init__(self):
        self.client = None

    async def init(self):
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis kutubxonasi yo'q — xotira rejimida ishlaydi")
            return
        try:
            self.client = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await self.client.ping()
            logger.info("✅ Redis ulandi")
        except Exception as e:
            logger.error(f"❌ Redis ulanish xatosi: {e} — xotira rejimida ishlaydi")
            self.client = None

    async def close(self):
        if self.client:
            await self.client.aclose()

    # =====================================================================
    # ===== SMS RATE LIMITING (FIX #8) =====
    # =====================================================================

    async def check_sms_rate_limit(self, phone: str,
                                   limit: int = 3,
                                   window_minutes: int = 60) -> Tuple[bool, Optional[str]]:
        """
        Bir soatda maksimal 3 ta SMS tekshiruvi.
        Qaytaradi: (ruxsat_berildi, xato_xabari)
        """
        key = f"sms_rate:{phone}"

        if self.client:
            try:
                count = await self.client.incr(key)
                if count == 1:
                    # Birinchi so'rov — TTL o'rnatamiz
                    await self.client.expire(key, window_minutes * 60)
                if count > limit:
                    ttl = await self.client.ttl(key)
                    mins = max(1, ttl // 60)
                    return False, f"SMS limiti oshdi. {mins} daqiqadan keyin urinib ko'ring."
                return True, None
            except Exception as e:
                logger.error(f"Redis SMS rate check xatosi: {e}")
                # Redis ishlamasa o'tkazib yuboramiz
                return True, None
        else:
            # Xotira rejimi (fallback)
            return self._memory_rate_limit(key, limit, window_minutes)

    def _memory_rate_limit(self, key: str, limit: int,
                           window_minutes: int) -> Tuple[bool, Optional[str]]:
        now = datetime.now()
        entry = _memory_store.get(key)
        if not entry or now > entry["expires_at"]:
            _memory_store[key] = {
                "count": 1,
                "expires_at": now + timedelta(minutes=window_minutes)
            }
            return True, None
        entry["count"] += 1
        if entry["count"] > limit:
            remaining = int((entry["expires_at"] - now).total_seconds() / 60) + 1
            return False, f"SMS limiti oshdi. {remaining} daqiqadan keyin urinib ko'ring."
        return True, None

    # =====================================================================
    # ===== PIN BRUTE-FORCE HIMOYA (FIX #1) =====
    # =====================================================================

    async def check_pin_attempts(self, user_id: int,
                                  max_attempts: int = 3,
                                  lock_minutes: int = 15) -> Tuple[bool, Optional[str]]:
        """
        PIN xato urinishlarini tekshirish.
        3 marta noto'g'ri → 15 daqiqa bloklash.
        Qaytaradi: (kirish_mumkin, xato_xabari)
        """
        lock_key = f"pin_lock:{user_id}"
        attempt_key = f"pin_attempts:{user_id}"

        if self.client:
            try:
                # Bloklanganmi?
                locked = await self.client.get(lock_key)
                if locked:
                    ttl = await self.client.ttl(lock_key)
                    mins = max(1, ttl // 60)
                    return False, f"⛔ {mins} daqiqa blokdasiz. Keyinroq urinib ko'ring."

                return True, None
            except Exception as e:
                logger.error(f"Redis PIN check xatosi: {e}")
                return True, None
        else:
            lock_key_mem = lock_key
            if lock_key_mem in _memory_store:
                entry = _memory_store[lock_key_mem]
                if datetime.now() < entry["expires_at"]:
                    remaining = int((entry["expires_at"] - datetime.now()).total_seconds() / 60) + 1
                    return False, f"⛔ {remaining} daqiqa blokdasiz."
                else:
                    del _memory_store[lock_key_mem]
            return True, None

    async def record_pin_failure(self, user_id: int,
                                  max_attempts: int = 3,
                                  lock_minutes: int = 15) -> int:
        """
        PIN xato urinishini qayd qilish.
        Qaytaradi: jami xato urinishlar soni
        """
        attempt_key = f"pin_attempts:{user_id}"
        lock_key = f"pin_lock:{user_id}"

        if self.client:
            try:
                count = await self.client.incr(attempt_key)
                if count == 1:
                    await self.client.expire(attempt_key, lock_minutes * 60)
                if count >= max_attempts:
                    await self.client.set(lock_key, "locked", ex=lock_minutes * 60)
                    await self.client.delete(attempt_key)
                    logger.warning(f"🔒 User {user_id} PIN xato — {lock_minutes} daqiqa blok")
                return count
            except Exception as e:
                logger.error(f"Redis PIN failure record xatosi: {e}")
                return 0
        else:
            attempt_key_mem = attempt_key
            now = datetime.now()
            entry = _memory_store.get(attempt_key_mem)
            if not entry or now > entry["expires_at"]:
                _memory_store[attempt_key_mem] = {
                    "count": 1,
                    "expires_at": now + timedelta(minutes=lock_minutes)
                }
                return 1
            entry["count"] += 1
            count = entry["count"]
            if count >= max_attempts:
                _memory_store[f"pin_lock:{user_id}"] = {
                    "expires_at": now + timedelta(minutes=lock_minutes)
                }
                del _memory_store[attempt_key_mem]
            return count

    async def reset_pin_attempts(self, user_id: int):
        """Muvaffaqiyatli PIN kiritilganda hisoblagichni nollashtirish"""
        if self.client:
            try:
                await self.client.delete(f"pin_attempts:{user_id}")
                await self.client.delete(f"pin_lock:{user_id}")
            except Exception as e:
                logger.error(f"Redis reset_pin_attempts xatosi: {e}")
        else:
            _memory_store.pop(f"pin_attempts:{user_id}", None)
            _memory_store.pop(f"pin_lock:{user_id}", None)

    # =====================================================================
    # ===== HAYDOVCHI ONLINE HOLATI =====
    # =====================================================================

    async def set_driver_online(self, driver_id: int, ttl_seconds: int = 360):
        """Redis-da haydovchini online deb belgilash (TTL bilan)"""
        key = f"driver_online:{driver_id}"
        if self.client:
            try:
                await self.client.set(key, "1", ex=ttl_seconds)
            except Exception as e:
                logger.error(f"Redis set_driver_online xatosi: {e}")

    async def is_driver_online(self, driver_id: int) -> bool:
        """Haydovchi online ekanligini tekshirish"""
        key = f"driver_online:{driver_id}"
        if self.client:
            try:
                return await self.client.exists(key) == 1
            except Exception as e:
                logger.error(f"Redis is_driver_online xatosi: {e}")
        return False


redis_client = RedisClient()
