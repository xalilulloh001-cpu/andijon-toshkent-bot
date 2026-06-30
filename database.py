"""
AndTaxi - PostgreSQL Database
Foydalanuvchilar, triplar, baholar saqlanadi
"""
import logging
import asyncpg
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")


class Database:
    def __init__(self):
        self.pool = None

    async def init(self):
        if not DATABASE_URL:
            logger.warning("DATABASE_URL yo'q — DB ishlamaydi")
            return
        try:
            self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
            await self._create_tables()
            logger.info("✅ Database ulandi")
        except Exception as e:
            logger.error(f"❌ DB ulanish xatosi: {e}")
            self.pool = None

    async def _create_tables(self):
        async with self.pool.acquire() as c:
            await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     BIGINT PRIMARY KEY,
                name        TEXT,
                phone       TEXT,
                role        TEXT,           -- 'driver' | 'passenger'
                seat_pref   TEXT,           -- passenger: 'front'|'back'
                seat_count  INT,            -- driver: 1-4
                car_model   TEXT,
                car_plate   TEXT,
                loc_lat     DOUBLE PRECISION,
                loc_lng     DOUBLE PRECISION,
                loc_addr    TEXT,
                registered  BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS trips (
                id          SERIAL PRIMARY KEY,
                passenger_id BIGINT REFERENCES users(user_id),
                driver_id   BIGINT REFERENCES users(user_id),
                status      TEXT DEFAULT 'searching',
                -- searching | matched | started | completed | cancelled
                p_lat       DOUBLE PRECISION,
                p_lng       DOUBLE PRECISION,
                p_addr      TEXT,
                rating      INT,            -- 1-5
                rating_comment TEXT,
                created_at  TIMESTAMP DEFAULT NOW(),
                matched_at  TIMESTAMP,
                started_at  TIMESTAMP,
                completed_at TIMESTAMP
            );
            """)
        logger.info("✅ Jadvallar tayyor")

    async def close(self):
        if self.pool:
            await self.pool.close()

    # ===== USERS =====

    async def get_user(self, user_id: int) -> Optional[dict]:
        if not self.pool:
            return None
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
            return dict(row) if row else None

    async def save_user(self, user_id: int, **kwargs) -> bool:
        if not self.pool:
            return False
        try:
            kwargs["updated_at"] = datetime.now()
            cols = ", ".join(kwargs.keys())
            vals = ", ".join(f"${i+2}" for i in range(len(kwargs)))
            upd  = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs.keys()))
            async with self.pool.acquire() as c:
                await c.execute(
                    f"""INSERT INTO users (user_id, {cols}) VALUES ($1, {vals})
                        ON CONFLICT (user_id) DO UPDATE SET {upd}""",
                    user_id, *kwargs.values()
                )
            return True
        except Exception as e:
            logger.error(f"save_user error: {e}")
            return False

    # ===== TRIPS =====

    async def create_trip(self, passenger_id: int, lat: float, lng: float, addr: str) -> Optional[int]:
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                tid = await c.fetchval(
                    """INSERT INTO trips (passenger_id, p_lat, p_lng, p_addr, status)
                       VALUES ($1,$2,$3,$4,'searching') RETURNING id""",
                    passenger_id, lat, lng, addr
                )
            return tid
        except Exception as e:
            logger.error(f"create_trip error: {e}")
            return None

    async def get_active_trip(self, user_id: int) -> Optional[dict]:
        """Foydalanuvchining aktiv tripi (haydovchi yoki yo'lovchi)"""
        if not self.pool:
            return None
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """SELECT * FROM trips
                   WHERE (passenger_id=$1 OR driver_id=$1)
                   AND status NOT IN ('completed','cancelled')
                   ORDER BY created_at DESC LIMIT 1""",
                user_id
            )
            return dict(row) if row else None

    async def update_trip(self, trip_id: int, **kwargs) -> bool:
        if not self.pool:
            return False
        try:
            upd = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs.keys()))
            async with self.pool.acquire() as c:
                await c.execute(
                    f"UPDATE trips SET {upd} WHERE id=$1",
                    trip_id, *kwargs.values()
                )
            return True
        except Exception as e:
            logger.error(f"update_trip error: {e}")
            return False

    async def get_trip(self, trip_id: int) -> Optional[dict]:
        if not self.pool:
            return None
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM trips WHERE id=$1", trip_id)
            return dict(row) if row else None

    async def get_searching_trips(self) -> list:
        """Haydovchi uchun: 'searching' holatdagi triplar"""
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT t.*, u.name, u.phone, u.seat_pref
                   FROM trips t JOIN users u ON t.passenger_id=u.user_id
                   WHERE t.status='searching'
                   ORDER BY t.created_at ASC"""
            )
            return [dict(r) for r in rows]

    async def get_available_drivers(self) -> list:
        """Yo'lovchi uchun: navbatdagi haydovchilar"""
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT u.* FROM users u
                   WHERE u.role='driver' AND u.registered=TRUE
                   AND NOT EXISTS (
                       SELECT 1 FROM trips t
                       WHERE t.driver_id=u.user_id
                       AND t.status NOT IN ('completed','cancelled')
                   )
                   ORDER BY u.updated_at DESC"""
            )
            return [dict(r) for r in rows]


db = Database()
