"""
AndTaxi - PostgreSQL Database
Foydalanuvchilar, triplar, baholar saqlanadi
"""
import logging
import asyncpg
import os
import math
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")


class Database:
    def __init__(self):
        self.pool = None

    @staticmethod
    def normalize_phone(phone: str) -> Optional[str]:
        """
        FIX: Telefon raqamini tekshiradi va standart shaklga keltiradi.
        Noto'g'ri raqam bo'lsa None qaytaradi (ro'yxatdan o'tkazilmaydi).
        O'zbekiston raqami: +998 XX XXX XX XX (9 ta raqam, 998 dan keyin)
        """
        if not phone:
            return None
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("998") and len(digits) == 12:
            return "+" + digits
        if len(digits) == 9:
            return "+998" + digits
        if digits.startswith("8") and len(digits) == 10:
            return "+998" + digits[1:]
        return None


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

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id             BIGINT PRIMARY KEY REFERENCES users(user_id),
                false_cancel_count  INT DEFAULT 0,
                sos_count           INT DEFAULT 0,
                updated_at          TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS sos_incidents (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT REFERENCES users(user_id),
                location_lat    DOUBLE PRECISION,
                location_lng    DOUBLE PRECISION,
                incident_type   TEXT DEFAULT 'emergency_call',
                resolved        BOOLEAN DEFAULT FALSE,
                resolved_at     TIMESTAMP,
                created_at      TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS groups (
                id                      SERIAL PRIMARY KEY,
                driver_id               BIGINT REFERENCES users(user_id),
                region                  TEXT,
                total_seats             INT,
                available_seats         INT,
                front_seat_available    BOOLEAN DEFAULT TRUE,
                status                  TEXT DEFAULT 'active',
                created_at              TIMESTAMP DEFAULT NOW()
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_group_per_driver
                ON groups (driver_id) WHERE status = 'active';

            CREATE TABLE IF NOT EXISTS group_members (
                id              SERIAL PRIMARY KEY,
                group_id        INT REFERENCES groups(id),
                passenger_id    BIGINT REFERENCES users(user_id),
                seat_position   TEXT,
                status          TEXT DEFAULT 'confirmed',
                added_at        TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS driver_offers (
                id                  SERIAL PRIMARY KEY,
                driver_id           BIGINT REFERENCES users(user_id),
                passenger_id        BIGINT REFERENCES users(user_id),
                group_id            INT REFERENCES groups(id),
                response_status     TEXT DEFAULT 'pending',
                offer_expires_at    TIMESTAMP,
                created_at          TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS passenger_queue (
                passenger_id        BIGINT PRIMARY KEY REFERENCES users(user_id),
                is_seat_important   BOOLEAN DEFAULT FALSE,
                created_at          TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS user_bans (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT REFERENCES users(user_id),
                ban_type    TEXT,
                reason      TEXT,
                ban_until   TIMESTAMP,
                active      BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMP DEFAULT NOW()
            );

            ALTER TABLE users ADD COLUMN IF NOT EXISTS is_online BOOLEAN DEFAULT FALSE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMP;
            ALTER TABLE groups ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
            ALTER TABLE groups ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;
            ALTER TABLE trips ADD COLUMN IF NOT EXISTS group_id INT REFERENCES groups(id);
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

    async def accept_trip_atomic(self, trip_id: int, driver_id: int) -> bool:
        """
        FIX: Bitta so'rovda tekshiradi VA yozadi (atomic).
        Ikkita haydovchi bir vaqtda 'qabul qilish' bossa ham,
        faqat BITTASI muvaffaqiyatli bo'ladi.
        """
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                row = await c.fetchrow(
                    """UPDATE trips SET driver_id=$2, status='matched', matched_at=NOW()
                       WHERE id=$1 AND status='searching'
                       RETURNING id""",
                    trip_id, driver_id
                )
            return row is not None
        except Exception as e:
            logger.error(f"accept_trip_atomic error: {e}")
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

    @staticmethod
    def _haversine_km(lat1, lng1, lat2, lng2) -> float:
        """Ikki nuqta orasidagi masofa (km)"""
        if None in (lat1, lng1, lat2, lng2):
            return 999999.0
        R = 6371
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlng/2)**2
        return R * 2 * math.asin(math.sqrt(a))

    async def get_nearby_drivers(self, lat: float, lng: float, limit: int = 5, max_km: float = 60) -> list:
        """
        FIX: Tasodifiy 5 ta emas, YO'LOVCHIGA ENG YAQIN haydovchilarni qaytaradi.
        max_km dan uzoqdagilar chetlab o'tiladi.
        """
        drivers = await self.get_available_drivers()
        with_dist = []
        for d in drivers:
            dist = self._haversine_km(lat, lng, d.get("loc_lat"), d.get("loc_lng"))
            if dist <= max_km:
                d["_distance_km"] = round(dist, 1)
                with_dist.append(d)
        with_dist.sort(key=lambda d: d["_distance_km"])
        return with_dist[:limit]

    # ===== BAN SYSTEM =====

    async def check_if_banned(self, user_id: int):
        """(is_banned: bool, ban_info: dict|None) qaytaradi"""
        if not self.pool:
            return False, None
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """SELECT * FROM user_bans
                   WHERE user_id=$1 AND active=TRUE
                   AND (ban_until IS NULL OR ban_until > NOW())
                   ORDER BY created_at DESC LIMIT 1""",
                user_id
            )
            if row:
                return True, dict(row)
            return False, None

    async def ban_user(self, user_id: int, ban_type: str, reason: str, ban_until) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO user_bans (user_id, ban_type, reason, ban_until, active)
                       VALUES ($1,$2,$3,$4,TRUE)""",
                    user_id, ban_type, reason, ban_until
                )
            return True
        except Exception as e:
            logger.error(f"ban_user error: {e}")
            return False

    async def unban_user(self, user_id: int) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    "UPDATE user_bans SET active=FALSE WHERE user_id=$1 AND active=TRUE",
                    user_id
                )
            return True
        except Exception as e:
            logger.error(f"unban_user error: {e}")
            return False

    async def get_false_cancel_count(self, user_id: int) -> int:
        if not self.pool:
            return 0
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT false_cancel_count FROM user_stats WHERE user_id=$1", user_id
            )
            return row["false_cancel_count"] if row else 0

    async def increment_false_cancels(self, user_id: int) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO user_stats (user_id, false_cancel_count, updated_at)
                       VALUES ($1, 1, NOW())
                       ON CONFLICT (user_id) DO UPDATE
                       SET false_cancel_count = user_stats.false_cancel_count + 1,
                           updated_at = NOW()""",
                    user_id
                )
            return True
        except Exception as e:
            logger.error(f"increment_false_cancels error: {e}")
            return False

    async def increment_sos_count(self, user_id: int) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO user_stats (user_id, sos_count, updated_at)
                       VALUES ($1, 1, NOW())
                       ON CONFLICT (user_id) DO UPDATE
                       SET sos_count = user_stats.sos_count + 1,
                           updated_at = NOW()""",
                    user_id
                )
                await c.execute(
                    """INSERT INTO sos_incidents (user_id, incident_type)
                       VALUES ($1, 'emergency_call')""",
                    user_id
                )
            return True
        except Exception as e:
            logger.error(f"increment_sos_count error: {e}")
            return False

    async def get_user_rating(self, user_id: int):
        """(avg_rating: float, count: int) qaytaradi"""
        if not self.pool:
            return 5.0, 0
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """SELECT AVG(rating)::FLOAT as avg, COUNT(rating) as cnt
                   FROM trips WHERE driver_id=$1 AND rating IS NOT NULL""",
                user_id
            )
            if row and row["cnt"]:
                return round(row["avg"], 2), row["cnt"]
            return 5.0, 0

    async def cancel_trip(self, trip_id: int, user_id: int, cancelled_by: str, reason: str = None):
        """(success: bool, error: str|None) qaytaradi"""
        if not self.pool:
            return False, "DB ulanmagan"
        try:
            async with self.pool.acquire() as c:
                trip = await c.fetchrow("SELECT * FROM trips WHERE id=$1", trip_id)
                if not trip:
                    return False, "Trip topilmadi"
                if trip["status"] in ("completed", "cancelled"):
                    return False, "Trip allaqachon yakunlangan"
                await c.execute(
                    """UPDATE trips SET status='cancelled', completed_at=NOW()
                       WHERE id=$1""",
                    trip_id
                )
            return True, None
        except Exception as e:
            logger.error(f"cancel_trip error: {e}")
            return False, str(e)

    # ===== ROUTE / GROUPS / MATCHING =====

    async def validate_trip_route(self, from_lat: float, from_lng: float,
                                   to_lat: float, to_lng: float):
        """(is_valid: bool, error: str|None) qaytaradi — Andijon <-> Toshkent chegarasi"""
        import math
        ANDIJON = {"lat": 40.7281, "lng": 72.3391, "radius": 50}
        TASHKENT = {"lat": 41.2995, "lng": 69.2401, "radius": 50}

        def in_region(lat, lng, region):
            R = 6371
            lat1, lat2 = math.radians(lat), math.radians(region["lat"])
            dlat = math.radians(region["lat"] - lat)
            dlng = math.radians(region["lng"] - lng)
            a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
            dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return dist <= region["radius"]

        from_ok = in_region(from_lat, from_lng, ANDIJON) or in_region(from_lat, from_lng, TASHKENT)
        to_ok = in_region(to_lat, to_lng, ANDIJON) or in_region(to_lat, to_lng, TASHKENT)

        if not from_ok or not to_ok:
            return False, "Marshrut faqat Andijon <-> Toshkent yo'nalishida ishlaydi"
        return True, None

    async def get_active_passengers_in_region(self, region: str) -> list:
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT t.*, t.p_lat AS location_lat, t.p_lng AS location_lng,
                          u.seat_pref, pq.is_seat_important
                   FROM trips t
                   JOIN users u ON t.passenger_id = u.user_id
                   LEFT JOIN passenger_queue pq ON pq.passenger_id = t.passenger_id
                   WHERE t.status = 'searching'
                   ORDER BY t.created_at ASC"""
            )
            return [dict(r) for r in rows]

    async def create_group(self, driver_id: int, region: str, total_seats: int):
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                existing = await c.fetchrow(
                    "SELECT id FROM groups WHERE driver_id=$1 AND status='active'",
                    driver_id
                )
                if existing:
                    return None
                gid = await c.fetchval(
                    """INSERT INTO groups (driver_id, region, total_seats, available_seats)
                       VALUES ($1,$2,$3,$3) RETURNING id""",
                    driver_id, region, total_seats
                )
            return gid
        except Exception as e:
            logger.error(f"create_group error: {e}")
            return None

    async def create_offer(self, driver_id: int, passenger_id: int, group_id: int) -> bool:
        if not self.pool:
            return False
        try:
            from datetime import timedelta
            expires = datetime.now() + timedelta(minutes=5)
            async with self.pool.acquire() as c:
                await c.execute(
                    """INSERT INTO driver_offers
                       (driver_id, passenger_id, group_id, response_status, offer_expires_at)
                       VALUES ($1,$2,$3,'pending',$4)""",
                    driver_id, passenger_id, group_id, expires
                )
            return True
        except Exception as e:
            logger.error(f"create_offer error: {e}")
            return False

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
                """SELECT gm.*, u.name, u.phone, u.loc_lat, u.loc_lng, u.loc_addr
                   FROM group_members gm
                   JOIN users u ON gm.passenger_id = u.user_id
                   WHERE gm.group_id=$1 AND gm.status='confirmed'""",
                group_id
            )
            return [dict(r) for r in rows]

    # ===== HAYDOVCHI NAVBATI (QUEUE) =====

    async def join_queue(self, driver_id: int, lat: float, lng: float) -> Optional[dict]:
        """
        FIX/YANGI: Haydovchi 'Navbatga qo'shilish' tugmasini bosganda
        chaqiriladi. Agar u allaqachon faol guruhga ega bo'lsa (masalan
        ilovani yopib qayta ochgan bo'lsa), o'sha guruhning joylashuvini
        yangilaydi. Aks holda YANGI guruh ochadi — sig'imi haydovchining
        ro'yxatdan o'tishda ko'rsatgan o'rindiq soniga teng.
        """
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                driver = await c.fetchrow("SELECT seat_count FROM users WHERE user_id=$1", driver_id)
                seats = (driver["seat_count"] if driver and driver["seat_count"] else 4)

                existing = await c.fetchrow(
                    "SELECT id FROM groups WHERE driver_id=$1 AND status='active'", driver_id
                )
                if existing:
                    await c.execute("UPDATE groups SET lat=$2, lng=$3 WHERE id=$1", existing["id"], lat, lng)
                    gid = existing["id"]
                else:
                    gid = await c.fetchval(
                        """INSERT INTO groups (driver_id, region, total_seats, available_seats, lat, lng, status)
                           VALUES ($1,'umumiy',$2,$2,$3,$4,'active') RETURNING id""",
                        driver_id, seats, lat, lng
                    )
                await c.execute(
                    "UPDATE users SET is_online=TRUE, loc_lat=$2, loc_lng=$3 WHERE user_id=$1",
                    driver_id, lat, lng
                )
            return await self.get_group(gid)
        except Exception as e:
            logger.error(f"join_queue error: {e}")
            return None

    async def get_driver_active_group(self, driver_id: int) -> Optional[dict]:
        if not self.pool:
            return None
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM groups WHERE driver_id=$1 AND status IN ('active','started') "
                "ORDER BY created_at DESC LIMIT 1",
                driver_id
            )
            return dict(row) if row else None

    async def find_nearest_group_with_space(self, lat: float, lng: float, max_km: float = 60) -> Optional[dict]:
        """Yo'lovchiga eng yaqin, bo'sh o'rindig'i bor FAOL guruhni topadi."""
        if not self.pool:
            return None
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT g.*, u.name AS driver_name, u.phone AS driver_phone,
                          u.car_model, u.car_plate
                   FROM groups g JOIN users u ON g.driver_id = u.user_id
                   WHERE g.status='active' AND g.available_seats > 0"""
            )
        best, best_dist = None, max_km + 1
        for r in rows:
            d = dict(r)
            dist = self._haversine_km(lat, lng, d.get("lat"), d.get("lng"))
            if dist < best_dist:
                best, best_dist = d, dist
        if best:
            best["_distance_km"] = round(best_dist, 1)
        return best

    async def join_group_atomic(self, group_id: int, passenger_id: int, p_lat, p_lng, p_addr) -> Optional[dict]:
        """
        FIX: Atomic — bo'sh o'rindiq faqat BITTA marta band qilinadi,
        ikkita yo'lovchi bir vaqtda oxirgi o'rindiqni "urib ketolmaydi".
        Muvaffaqiyatli bo'lsa yangi trip yaratadi va guruhga bog'laydi.
        """
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                async with c.transaction():
                    row = await c.fetchrow(
                        """UPDATE groups SET available_seats = available_seats - 1
                           WHERE id=$1 AND status='active' AND available_seats > 0
                           RETURNING id, driver_id, total_seats, available_seats""",
                        group_id
                    )
                    if not row:
                        return None
                    await c.execute(
                        """INSERT INTO group_members (group_id, passenger_id, status)
                           VALUES ($1,$2,'confirmed')""",
                        group_id, passenger_id
                    )
                    trip_id = await c.fetchval(
                        """INSERT INTO trips (passenger_id, driver_id, group_id, p_lat, p_lng, p_addr, status, matched_at)
                           VALUES ($1,$2,$3,$4,$5,$6,'matched',NOW()) RETURNING id""",
                        passenger_id, row["driver_id"], group_id, p_lat, p_lng, p_addr
                    )
            return {
                "trip_id": trip_id, "driver_id": row["driver_id"],
                "total_seats": row["total_seats"], "available_seats": row["available_seats"]
            }
        except Exception as e:
            logger.error(f"join_group_atomic error: {e}")
            return None

    async def start_group(self, driver_id: int) -> Optional[dict]:
        """Haydovchi 'Yo'lga chiqamiz!' bosganda — guruhdagi barcha triplar boshlanadi."""
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                group = await c.fetchrow(
                    "SELECT id FROM groups WHERE driver_id=$1 AND status='active'", driver_id
                )
                if not group:
                    return None
                await c.execute("UPDATE groups SET status='started' WHERE id=$1", group["id"])
                await c.execute(
                    "UPDATE trips SET status='started', started_at=NOW() "
                    "WHERE group_id=$1 AND status NOT IN ('completed','cancelled')",
                    group["id"]
                )
            return await self.get_group(group["id"])
        except Exception as e:
            logger.error(f"start_group error: {e}")
            return None

    async def finish_group(self, driver_id: int) -> Optional[dict]:
        """
        FIX: Trip tugagach haydovchi AVTOMATIK navbatdan chiqariladi.
        Qayta yo'lovchi olish uchun yana 'Navbatga qo'shilish' bosishi kerak.
        """
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as c:
                group = await c.fetchrow(
                    "SELECT id FROM groups WHERE driver_id=$1 AND status IN ('active','started') "
                    "ORDER BY created_at DESC LIMIT 1",
                    driver_id
                )
                if not group:
                    return None
                await c.execute("UPDATE groups SET status='completed' WHERE id=$1", group["id"])
                await c.execute(
                    "UPDATE trips SET status='completed', completed_at=NOW() "
                    "WHERE group_id=$1 AND status NOT IN ('completed','cancelled')",
                    group["id"]
                )
                await c.execute("UPDATE users SET is_online=FALSE WHERE user_id=$1", driver_id)
            return await self.get_group(group["id"])
        except Exception as e:
            logger.error(f"finish_group error: {e}")
            return None

    # ===== WEBSOCKET / DRIVER ONLINE STATUS =====

    async def update_driver_heartbeat(self, driver_id: int, lat: float, lng: float) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE users SET loc_lat=$2, loc_lng=$3,
                       last_heartbeat=NOW(), is_online=TRUE
                       WHERE user_id=$1""",
                    driver_id, lat, lng
                )
            return True
        except Exception as e:
            logger.error(f"update_driver_heartbeat error: {e}")
            return False

    async def mark_driver_online(self, driver_id: int) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    "UPDATE users SET is_online=TRUE, last_heartbeat=NOW() WHERE user_id=$1",
                    driver_id
                )
            return True
        except Exception as e:
            logger.error(f"mark_driver_online error: {e}")
            return False

    async def mark_driver_offline(self, driver_id: int, reason: str = "") -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    "UPDATE users SET is_online=FALSE WHERE user_id=$1",
                    driver_id
                )
            logger.info(f"Driver {driver_id} offline: {reason}")
            return True
        except Exception as e:
            logger.error(f"mark_driver_offline error: {e}")
            return False

    async def check_offline_drivers(self, timeout_seconds: int = 300) -> list:
        """5 daqiqadan ortiq heartbeat yubormagan haydovchilar"""
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT user_id FROM users
                   WHERE role='driver' AND is_online=TRUE
                   AND (last_heartbeat IS NULL
                        OR last_heartbeat < NOW() - ($1 || ' seconds')::INTERVAL)""",
                str(timeout_seconds)
            )
            return [dict(r) for r in rows]

    # ===== RATING MODERATION =====

    async def flag_rating_for_review(self, trip_id: int, reason: str) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                row = await c.fetchrow("SELECT * FROM trips WHERE id=$1", trip_id)
                if not row:
                    return False
                await c.execute(
                    """UPDATE trips SET rating_comment = COALESCE(rating_comment,'') || $2
                       WHERE id=$1""",
                    trip_id, f" [FLAGGED: {reason}]"
                )
            return True
        except Exception as e:
            logger.error(f"flag_rating_for_review error: {e}")
            return False

    async def get_flagged_ratings(self) -> list:
        if not self.pool:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM trips WHERE rating_comment LIKE '%[FLAGGED:%'"
            )
            return [dict(r) for r in rows]

    async def resolve_rating_flag(self, trip_id: int) -> bool:
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as c:
                await c.execute(
                    """UPDATE trips SET rating_comment =
                       regexp_replace(rating_comment, '\\s*\\[FLAGGED:[^\\]]*\\]', '', 'g')
                       WHERE id=$1""",
                    trip_id
                )
            return True
        except Exception as e:
            logger.error(f"resolve_rating_flag error: {e}")
            return False


db = Database()
