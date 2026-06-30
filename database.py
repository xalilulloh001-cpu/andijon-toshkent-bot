"""
AndTaxi - PostgreSQL Database
Foydalanuvchilar, triplar, guruhlar, ban tizimi va boshqalar
"""
import logging
import asyncpg
import os
import math
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Geographic bounds (FIX #10)
ANDIJON = {"lat": 40.7281, "lng": 72.3391, "radius": 50}
TASHKENT = {"lat": 41.2995, "lng": 69.2401, "radius": 50}


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Ikki nuqta orasidagi masofani km da hisoblash"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
            -- ===== ASOSIY JADVALLAR =====

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
                is_active   BOOLEAN DEFAULT TRUE,
                last_heartbeat TIMESTAMP,
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS trips (
                id           SERIAL PRIMARY KEY,
                passenger_id BIGINT REFERENCES users(user_id),
                driver_id    BIGINT REFERENCES users(user_id),
                status       TEXT DEFAULT 'searching',
                -- searching | matched | started | completed | cancelled
                p_lat        DOUBLE PRECISION,
                p_lng        DOUBLE PRECISION,
                p_addr       TEXT,
                rating       INT,           -- 1-5
                rating_comment TEXT,
                created_at   TIMESTAMP DEFAULT NOW(),
                matched_at   TIMESTAMP,
                started_at   TIMESTAMP,
                completed_at TIMESTAMP
            );

            -- ===== GURUH TIZIMI =====

            CREATE TABLE IF NOT EXISTS groups (
                id                   SERIAL PRIMARY KEY,
                driver_id            BIGINT REFERENCES users(user_id),
                region               TEXT,      -- 'andijon' | 'tashkent'
                total_seats          INT DEFAULT 4,
                available_seats      INT DEFAULT 4,
                front_seat_available BOOLEAN DEFAULT TRUE,
                status               TEXT DEFAULT 'active',
                -- active | completed | cancelled
                created_at           TIMESTAMP DEFAULT NOW()
            );

            -- FIX #6: Haydovchiga faqat bitta aktiv guruh
            CREATE UNIQUE INDEX IF NOT EXISTS unique_active_driver_group
                ON groups(driver_id)
                WHERE status IN ('active');

            CREATE TABLE IF NOT EXISTS group_members (
                id            SERIAL PRIMARY KEY,
                group_id      INT REFERENCES groups(id) ON DELETE CASCADE,
                passenger_id  BIGINT REFERENCES users(user_id),
                seat_position TEXT DEFAULT 'back',  -- 'front' | 'back'
                status        TEXT DEFAULT 'confirmed',
                -- confirmed | cancelled
                added_at      TIMESTAMP DEFAULT NOW()
            );

            -- ===== TAKLIF TIZIMI =====

            CREATE TABLE IF NOT EXISTS driver_offers (
                id              SERIAL PRIMARY KEY,
                driver_id       BIGINT REFERENCES users(user_id),
                passenger_id    BIGINT REFERENCES users(user_id),
                group_id        INT REFERENCES groups(id),
                response_status TEXT DEFAULT 'pending',
                -- pending | accepted | rejected | expired
                offer_expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '5 minutes'),
                created_at      TIMESTAMP DEFAULT NOW()
            );

            -- ===== YO'LOVCHI NAVBAT =====

            CREATE TABLE IF NOT EXISTS passenger_queue (
                passenger_id     BIGINT PRIMARY KEY REFERENCES users(user_id),
                region           TEXT,
                is_seat_important BOOLEAN DEFAULT FALSE,
                seat_count       INT DEFAULT 1,
                created_at       TIMESTAMP DEFAULT NOW()
            );

            -- ===== BAN TIZIMI =====

            CREATE TABLE IF NOT EXISTS user_bans (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT REFERENCES users(user_id),
                ban_type   TEXT,
                -- false_cancel | sos_abuse | low_rating | manual
                reason     TEXT,
                ban_until  TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id            BIGINT PRIMARY KEY REFERENCES users(user_id),
                false_cancel_count INT DEFAULT 0,
                sos_count          INT DEFAULT 0,
                updated_at         TIMESTAMP DEFAULT NOW()
            );

            -- ===== SOS TIZIMI =====

            CREATE TABLE IF NOT EXISTS sos_incidents (
                id            SERIAL PRIMARY KEY,
                user_id       BIGINT REFERENCES users(user_id),
                location_lat  DOUBLE PRECISION,
                location_lng  DOUBLE PRECISION,
                incident_type TEXT DEFAULT 'emergency_call',
                resolved      BOOLEAN DEFAULT FALSE,
                resolved_at   TIMESTAMP,
                created_at    TIMESTAMP DEFAULT NOW()
            );

            -- ===== REYTING MODERATSIYA =====

            CREATE TABLE IF NOT EXISTS rating_moderation (
                id            SERIAL PRIMARY KEY,
                trip_id       INT REFERENCES trips(id),
                user_id       BIGINT REFERENCES users(user_id),
                flag_status   TEXT DEFAULT 'pending',
                -- pending | approved | deleted | warning_to_rater
                admin_id      BIGINT,
                reason        TEXT,
                created_at    TIMESTAMP DEFAULT NOW()
            );

            -- ===== TRIP BEKOR QILISH JURNALI =====

            CREATE TABLE IF NOT EXISTS trip_cancellations (
                id              SERIAL PRIMARY KEY,
                trip_id         INT REFERENCES trips(id),
                user_id         BIGINT REFERENCES users(user_id),
                cancelled_by    TEXT,  -- 'driver' | 'passenger'
                reason          TEXT,
                penalty_applied BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMP DEFAULT NOW()
            );
            """)
        logger.info("✅ Barcha jadvallar tayyor")

    async def close(self):
        if self.pool:
            await self.pool.close()

    # =====================================================================
    # ===== USERS =====
    # =====================================================================

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
            # user_stats satrini ham yaratamiz (birinchi marta)
            await self._ensure_user_stats(user_id)
            return True
        except Exception as e:
            logger.error(f"save_user error: {e}")
            return False

    async def _ensure_user_stats(self, user_id: int):
        """user_stats jadvalida satr bo'lmasa yaratish"""
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO user_stats (user_id) VALUES ($1)
                       ON CONFLICT (user_id) DO NOTHING""",
                    user_id
                )
        except Exception as e:
            logger.error(f"_ensure_user_stats error: {e}")

    # =====================================================================
    # ===== TRIPS =====
    # =====================================================================

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
        """Foydalanuvchining aktiv tripi"""
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
                   WHERE u.role='driver' AND u.registered=TRUE AND u.is_active=TRUE
                   AND NOT EXISTS (
                       SELECT 1 FROM trips t
                       WHERE t.driver_id=u.user_id
                       AND t.status NOT IN ('completed','cancelled')
                   )
                   ORDER BY u.updated_at DESC"""
            )
            return [dict(r) for r in rows]

    async def cancel_trip(self, trip_id: int, user_id: int,
                          cancelled_by: str, reason: str = None) -> Tuple[bool, Optional[str]]:
        """Trip bekor qilish + jurnal yozish + false_cancel_count oshirish"""
        if not self.pool:
            return False, "DB ishlamaydi"
        try:
            async with self.pool.acquire() as c:
                async with c.transaction():
                    trip = await c.fetchrow("SELECT * FROM trips WHERE id=$1", trip_id)
                    if not trip:
                        return False, "Trip topilmadi"
                    if trip["status"] in ("completed", "cancelled"):
                        return False, "Trip allaqachon tugagan"

                    await c.execute(
                        "UPDATE trips SET status='cancelled' WHERE id=$1", trip_id
                    )
                    await c.execute(
                        """INSERT INTO trip_cancellations
                           (trip_id, user_id, cancelled_by, reason, penalty_applied)
                           VALUES ($1, $2, $3, $4, $5)""",
                        trip_id, user_id, cancelled_by, reason, cancelled_by == "passenger"
                    )
                    # Yo'lovchi bekor qilsa false_cancel_count oshadi
                    if cancelled_by == "passenger":
                        await c.execute(
                            """INSERT INTO user_stats (user_id, false_cancel_count)
                               VALUES ($1, 1)
                               ON CONFLICT (user_id) DO UPDATE
                               SET false_cancel_count = user_stats.false_cancel_count + 1,
                                   updated_at = NOW()""",
                            user_id
                        )
            logger.info(f"✅ Trip {trip_id} bekor qilindi ({cancelled_by})")
            return True, None
        except Exception as e:
            logger.error(f"cancel_trip error: {e}")
            return False, str(e)

    # =====================================================================
    # ===== GURUH TIZIMI =====
    # =====================================================================

    async def create_group(self, driver_id: int, region: str, total_seats: int) -> Optional[int]:
        """FIX #6: UNIQUE constraint orqali bir haydovchi – bir guruh"""
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                gid = await c.fetchval(
                    """INSERT INTO groups (driver_id, region, total_seats, available_seats)
                       VALUES ($1, $2, $3, $3) RETURNING id""",
                    driver_id, region, total_seats
                )
            return gid
        except asyncpg.UniqueViolationError:
            logger.warning(f"⚠️ Driver {driver_id} allaqachon aktiv guruhga ega")
            return None
        except Exception as e:
            logger.error(f"create_group error: {e}")
            return None

    async def get_group(self, group_id: int) -> Optional[dict]:
        if not self.pool:
            return None
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM groups WHERE id=$1", group_id)
            return dict(row) if row else None

    async def get_group_members(self, group_id: int) -> list:
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT gm.*, u.name, u.phone, u.loc_lat AS location_lat,
                          u.loc_lng AS location_lng
                   FROM group_members gm
                   JOIN users u ON gm.passenger_id = u.user_id
                   WHERE gm.group_id = $1 AND gm.status = 'confirmed'""",
                group_id
            )
            return [dict(r) for r in rows]

    async def create_offer(self, driver_id: int, passenger_id: int,
                           group_id: int) -> bool:
        """Haydovchidan yo'lovchiga taklif yuborish"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO driver_offers
                       (driver_id, passenger_id, group_id, offer_expires_at)
                       VALUES ($1, $2, $3, NOW() + INTERVAL '5 minutes')""",
                    driver_id, passenger_id, group_id
                )
            return True
        except Exception as e:
            logger.error(f"create_offer error: {e}")
            return False

    async def get_active_passengers_in_region(self, region: str) -> list:
        """Navbatdagi yo'lovchilarni region bo'yicha olish"""
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT pq.*, u.name, u.phone, u.loc_lat AS location_lat,
                          u.loc_lng AS location_lng
                   FROM passenger_queue pq
                   JOIN users u ON pq.passenger_id = u.user_id
                   WHERE pq.region = $1
                   AND NOT EXISTS (
                       SELECT 1 FROM group_members gm
                       WHERE gm.passenger_id = pq.passenger_id
                       AND gm.status = 'confirmed'
                   )
                   ORDER BY pq.created_at ASC""",
                region
            )
            return [dict(r) for r in rows]

    # =====================================================================
    # ===== BAN TIZIMI =====
    # =====================================================================

    async def check_if_banned(self, user_id: int) -> Tuple[bool, Optional[dict]]:
        """Foydalanuvchi ban ostidami?"""
        if not self.pool:
            return False, None
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """SELECT * FROM user_bans
                   WHERE user_id = $1 AND ban_until > NOW()
                   ORDER BY created_at DESC LIMIT 1""",
                user_id
            )
            if row:
                return True, dict(row)
            return False, None

    async def ban_user(self, user_id: int, ban_type: str,
                       reason: str, ban_until: datetime) -> bool:
        """Foydalanuvchini bloklash"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO user_bans (user_id, ban_type, reason, ban_until)
                       VALUES ($1, $2, $3, $4)""",
                    user_id, ban_type, reason, ban_until
                )
            logger.warning(f"🚫 User {user_id} ban qilindi: {ban_type} → {ban_until}")
            return True
        except Exception as e:
            logger.error(f"ban_user error: {e}")
            return False

    async def unban_user(self, user_id: int) -> bool:
        """Foydalanuvchi banning muddatini tugattirish"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    "UPDATE user_bans SET ban_until=NOW() WHERE user_id=$1 AND ban_until>NOW()",
                    user_id
                )
            logger.info(f"✅ User {user_id} bandan chiqarildi")
            return True
        except Exception as e:
            logger.error(f"unban_user error: {e}")
            return False

    async def get_false_cancel_count(self, user_id: int) -> int:
        """Yolg'on bekor qilishlar soni"""
        if not self.pool:
            return 0
        async with self.pool.acquire() as c:
            val = await c.fetchval(
                "SELECT false_cancel_count FROM user_stats WHERE user_id=$1",
                user_id
            )
            return val or 0

    async def increment_false_cancels(self, user_id: int) -> bool:
        """Yolg'on bekor qilish hisoblagichini oshirish"""
        if not self.pool:
            return False
        try:
            await self._ensure_user_stats(user_id)
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE user_stats
                       SET false_cancel_count = false_cancel_count + 1, updated_at = NOW()
                       WHERE user_id = $1""",
                    user_id
                )
            return True
        except Exception as e:
            logger.error(f"increment_false_cancels error: {e}")
            return False

    async def increment_sos_count(self, user_id: int) -> bool:
        """SOS hisoblagichini oshirish"""
        if not self.pool:
            return False
        try:
            await self._ensure_user_stats(user_id)
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE user_stats
                       SET sos_count = sos_count + 1, updated_at = NOW()
                       WHERE user_id = $1""",
                    user_id
                )
            return True
        except Exception as e:
            logger.error(f"increment_sos_count error: {e}")
            return False

    async def get_user_rating(self, user_id: int) -> Tuple[float, int]:
        """Haydovchining o'rtacha reytingi va baholashlar soni"""
        if not self.pool:
            return 0.0, 0
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """SELECT AVG(rating)::FLOAT AS avg_r, COUNT(*) AS cnt
                   FROM trips
                   WHERE driver_id=$1 AND rating IS NOT NULL""",
                user_id
            )
            if row and row["cnt"] > 0:
                return round(row["avg_r"], 2), row["cnt"]
            return 0.0, 0

    # =====================================================================
    # ===== HAYDOVCHI ONLINE/OFFLINE =====
    # =====================================================================

    async def mark_driver_online(self, driver_id: int) -> bool:
        """Haydovchini online deb belgilash"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE users
                       SET is_active=TRUE, last_heartbeat=NOW(), updated_at=NOW()
                       WHERE user_id=$1""",
                    driver_id
                )
            return True
        except Exception as e:
            logger.error(f"mark_driver_online error: {e}")
            return False

    async def mark_driver_offline(self, driver_id: int, reason: str = "") -> bool:
        """FIX #5: Haydovchini offline deb belgilash"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE users
                       SET is_active=FALSE, updated_at=NOW()
                       WHERE user_id=$1""",
                    driver_id
                )
                # Aktiv guruhni ham to'xtatamiz
                await c.execute(
                    "UPDATE groups SET status='cancelled' WHERE driver_id=$1 AND status='active'",
                    driver_id
                )
            logger.info(f"🔴 Driver {driver_id} offline: {reason}")
            return True
        except Exception as e:
            logger.error(f"mark_driver_offline error: {e}")
            return False

    async def update_driver_heartbeat(self, driver_id: int,
                                      lat: float, lng: float) -> bool:
        """FIX #5: Heartbeat va lokatsiyani yangilash"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE users
                       SET last_heartbeat=NOW(), is_active=TRUE,
                           loc_lat=$2, loc_lng=$3, updated_at=NOW()
                       WHERE user_id=$1""",
                    driver_id, lat, lng
                )
            return True
        except Exception as e:
            logger.error(f"update_driver_heartbeat error: {e}")
            return False

    async def check_offline_drivers(self) -> List[int]:
        """FIX #5: 5 daqiqadan ko'p heartbeat jo'natmagan haydovchilar"""
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT user_id FROM users
                   WHERE role='driver' AND is_active=TRUE
                   AND (
                       last_heartbeat IS NULL OR
                       last_heartbeat < NOW() - INTERVAL '5 minutes'
                   )"""
            )
            return [r["user_id"] for r in rows]

    # =====================================================================
    # ===== MARSHRUT TEKSHIRUVI =====
    # =====================================================================

    async def validate_trip_route(self, from_lat: float, from_lng: float,
                                  to_lat: float, to_lng: float) -> Tuple[bool, Optional[str]]:
        """FIX #10: Marshrut Andijon yoki Toshkent hududida ekanligini tekshirish"""
        # Bosh nuqta Andijon yaqinidami?
        dist_from_andijan = _haversine(from_lat, from_lng,
                                        ANDIJON["lat"], ANDIJON["lng"])
        # Bosh nuqta Toshkent yaqinidami?
        dist_from_tashkent = _haversine(from_lat, from_lng,
                                         TASHKENT["lat"], TASHKENT["lng"])

        if (dist_from_andijan > ANDIJON["radius"] and
                dist_from_tashkent > TASHKENT["radius"]):
            return False, (
                f"Bosh nuqta Andijon yoki Toshkentdan juda uzoq "
                f"(Andijon: {dist_from_andijan:.0f} km, "
                f"Toshkent: {dist_from_tashkent:.0f} km)"
            )

        # Oxirgi nuqta tekshiruvi
        dist_to_andijan = _haversine(to_lat, to_lng,
                                      ANDIJON["lat"], ANDIJON["lng"])
        dist_to_tashkent = _haversine(to_lat, to_lng,
                                       TASHKENT["lat"], TASHKENT["lng"])

        if (dist_to_andijan > ANDIJON["radius"] and
                dist_to_tashkent > TASHKENT["radius"]):
            return False, (
                f"Manzil Andijon yoki Toshkentdan juda uzoq "
                f"(Andijon: {dist_to_andijan:.0f} km, "
                f"Toshkent: {dist_to_tashkent:.0f} km)"
            )

        return True, None

    # =====================================================================
    # ===== REYTING MODERATSIYA =====
    # =====================================================================

    async def flag_rating_for_review(self, trip_id: int, reason: str) -> bool:
        """FIX #9: Reyting admin tekshiruviga yuborish"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                trip = await c.fetchrow("SELECT * FROM trips WHERE id=$1", trip_id)
                if not trip:
                    return False
                await c.execute(
                    """INSERT INTO rating_moderation (trip_id, user_id, reason)
                       VALUES ($1, $2, $3)
                       ON CONFLICT DO NOTHING""",
                    trip_id, trip["driver_id"], reason
                )
            return True
        except Exception as e:
            logger.error(f"flag_rating_for_review error: {e}")
            return False

    async def get_flagged_ratings(self) -> list:
        """Admin uchun: moderatsiya kutayotgan reytinglar"""
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT rm.*, t.rating, t.rating_comment,
                          u.name AS driver_name
                   FROM rating_moderation rm
                   JOIN trips t ON rm.trip_id = t.id
                   JOIN users u ON t.driver_id = u.user_id
                   WHERE rm.flag_status = 'pending'
                   ORDER BY rm.created_at DESC"""
            )
            return [dict(r) for r in rows]

    async def resolve_rating_flag(self, flag_id: int, admin_id: int,
                                  decision: str) -> bool:
        """Admin tomonidan moderatsiya qarorini yozish"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE rating_moderation
                       SET flag_status=$2, admin_id=$3
                       WHERE id=$1""",
                    flag_id, decision, admin_id
                )
                # Agar o'chirish qarori bo'lsa, reyting nollanadi
                if decision == "deleted":
                    row = await c.fetchrow(
                        "SELECT trip_id FROM rating_moderation WHERE id=$1", flag_id
                    )
                    if row:
                        await c.execute(
                            "UPDATE trips SET rating=NULL, rating_comment=NULL WHERE id=$1",
                            row["trip_id"]
                        )
            return True
        except Exception as e:
            logger.error(f"resolve_rating_flag error: {e}")
            return False


db = Database()
