import asyncpg
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
pool = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            lang TEXT DEFAULT 'uz',
            role TEXT DEFAULT 'passenger',
            rating FLOAT DEFAULT 5.0,
            rating_count INT DEFAULT 0,
            is_blocked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS drivers (
            user_id BIGINT PRIMARY KEY REFERENCES users(id),
            car_model TEXT,
            car_number TEXT,
            car_color TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id SERIAL PRIMARY KEY,
            from_user BIGINT REFERENCES users(id),
            to_user BIGINT REFERENCES users(id),
            group_id INT,
            stars INT CHECK(stars BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Haydovchi navbati
        CREATE TABLE IF NOT EXISTS driver_queue (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            direction TEXT NOT NULL,
            seats INT NOT NULL,
            status TEXT DEFAULT 'waiting',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Yo'lovchi navbati
        CREATE TABLE IF NOT EXISTS passenger_queue (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id),
            direction TEXT NOT NULL,
            seat_position TEXT NOT NULL DEFAULT 'back',
            seat_count INT NOT NULL DEFAULT 1,
            lat FLOAT,
            lng FLOAT,
            location_name TEXT,
            region TEXT,
            location_confirmed BOOLEAN DEFAULT FALSE,
            status TEXT DEFAULT 'waiting',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Match guruhlari
        CREATE TABLE IF NOT EXISTS match_groups (
            id SERIAL PRIMARY KEY,
            driver_queue_id INT REFERENCES driver_queue(id),
            direction TEXT NOT NULL,
            status TEXT DEFAULT 'calling',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Guruh a'zolari (yo'lovchilar)
        CREATE TABLE IF NOT EXISTS match_members (
            id SERIAL PRIMARY KEY,
            group_id INT REFERENCES match_groups(id),
            passenger_queue_id INT REFERENCES passenger_queue(id),
            call_status TEXT DEFAULT 'pending',
            call_deadline TIMESTAMPTZ,
            confirmed_at TIMESTAMPTZ,
            sort_order INT DEFAULT 0
        );
        """)
    return pool


# ─── USERS ────────────────────────────────────────────────
async def get_user(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)

async def create_user(user_id, full_name, phone, lang='uz'):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users(id,full_name,phone,lang) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            user_id, full_name, phone, lang
        )

async def set_user_role(user_id, role):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET role=$1 WHERE id=$2", role, user_id)

async def set_user_lang(user_id, lang):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET lang=$1 WHERE id=$2", lang, user_id)

async def block_user(user_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked=TRUE WHERE id=$1", user_id)

async def unblock_user(user_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked=FALSE WHERE id=$1", user_id)

async def get_all_users_count():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")

async def get_all_drivers_count():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM drivers")

async def get_all_trips_count():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM match_groups WHERE status='completed'")

async def get_all_user_ids():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users WHERE is_blocked=FALSE")
        return [r['id'] for r in rows]

# ─── DRIVERS ──────────────────────────────────────────────
async def register_driver(user_id, car_model, car_number, car_color):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO drivers(user_id,car_model,car_number,car_color)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(user_id) DO UPDATE SET car_model=$2,car_number=$3,car_color=$4
        """, user_id, car_model, car_number, car_color)
        await conn.execute("UPDATE users SET role='driver' WHERE id=$1", user_id)

async def get_driver_info(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT d.*,u.full_name,u.phone,u.rating,u.rating_count
            FROM drivers d JOIN users u ON u.id=d.user_id WHERE d.user_id=$1
        """, user_id)

async def update_driver_car(user_id, car_model, car_number, car_color):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE drivers SET car_model=$1,car_number=$2,car_color=$3 WHERE user_id=$4",
            car_model, car_number, car_color, user_id
        )

# ─── DRIVER QUEUE ─────────────────────────────────────────
async def add_driver_to_queue(user_id, direction, seats) -> int:
    async with pool.acquire() as conn:
        # Oldingi kutayotganini bekor qilish
        await conn.execute(
            "UPDATE driver_queue SET status='cancelled' WHERE user_id=$1 AND status='waiting'",
            user_id
        )
        row = await conn.fetchrow(
            "INSERT INTO driver_queue(user_id,direction,seats) VALUES($1,$2,$3) RETURNING id",
            user_id, direction, seats
        )
        return row['id']

async def get_driver_queue_entry(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM driver_queue WHERE user_id=$1 AND status='waiting' ORDER BY created_at DESC LIMIT 1",
            user_id
        )

async def cancel_driver_queue(user_id):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE driver_queue SET status='cancelled' WHERE user_id=$1 AND status='waiting'",
            user_id
        )

async def get_waiting_drivers(direction):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM driver_queue WHERE direction=$1 AND status='waiting' ORDER BY created_at",
            direction
        )

async def set_driver_queue_status(dq_id, status):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE driver_queue SET status=$1 WHERE id=$2", status, dq_id)

# ─── PASSENGER QUEUE ──────────────────────────────────────
async def add_passenger_to_queue(user_id, direction, seat_position, seat_count) -> int:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE passenger_queue SET status='cancelled' WHERE user_id=$1 AND status='waiting'",
            user_id
        )
        row = await conn.fetchrow("""
            INSERT INTO passenger_queue(user_id,direction,seat_position,seat_count)
            VALUES($1,$2,$3,$4) RETURNING id
        """, user_id, direction, seat_position, seat_count)
        return row['id']

async def get_passenger_queue_entry(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM passenger_queue WHERE user_id=$1 AND status IN ('waiting','location_pending') ORDER BY created_at DESC LIMIT 1",
            user_id
        )

async def update_passenger_location(pq_id, lat, lng, location_name, region, confirmed):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE passenger_queue
            SET lat=$1, lng=$2, location_name=$3, region=$4,
                location_confirmed=$5, status='waiting'
            WHERE id=$6
        """, lat, lng, location_name, region, confirmed, pq_id)

async def set_passenger_location_text(pq_id, location_name, region):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE passenger_queue
            SET location_name=$1, region=$2, location_confirmed=TRUE, status='waiting'
            WHERE id=$3
        """, location_name, region, pq_id)

async def cancel_passenger_queue(user_id):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE passenger_queue SET status='cancelled' WHERE user_id=$1 AND status IN ('waiting','location_pending')",
            user_id
        )

async def set_passenger_queue_status(pq_id, status):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE passenger_queue SET status=$1 WHERE id=$2", status, pq_id)

async def get_waiting_passengers(direction):
    """Lokatsiyasi tasdiqlangan kutayotgan yo'lovchilar"""
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT pq.*, u.full_name, u.phone, u.rating
            FROM passenger_queue pq
            JOIN users u ON u.id=pq.user_id
            WHERE pq.direction=$1
              AND pq.status='waiting'
              AND pq.location_confirmed=TRUE
            ORDER BY pq.created_at
        """, direction)

# ─── MATCH GROUPS ─────────────────────────────────────────
async def create_match_group(dq_id, direction) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO match_groups(driver_queue_id,direction) VALUES($1,$2) RETURNING id",
            dq_id, direction
        )
        return row['id']

async def get_match_group(group_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM match_groups WHERE id=$1", group_id)

async def set_group_status(group_id, status):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE match_groups SET status=$1 WHERE id=$2", status, group_id)

async def add_match_members(group_id, passenger_queue_ids: list):
    """Yo'lovchilarni guruhga qo'shish, sort_order masofaga qarab"""
    async with pool.acquire() as conn:
        for i, pq_id in enumerate(passenger_queue_ids):
            await conn.execute("""
                INSERT INTO match_members(group_id,passenger_queue_id,sort_order)
                VALUES($1,$2,$3)
                ON CONFLICT DO NOTHING
            """, group_id, pq_id, i)
            await conn.execute(
                "UPDATE passenger_queue SET status='matched' WHERE id=$1", pq_id
            )

async def get_group_members(group_id):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT mm.*, pq.user_id, pq.lat, pq.lng, pq.location_name,
                   pq.region, pq.seat_position, pq.seat_count, pq.direction,
                   u.full_name, u.phone, u.rating
            FROM match_members mm
            JOIN passenger_queue pq ON pq.id=mm.passenger_queue_id
            JOIN users u ON u.id=pq.user_id
            WHERE mm.group_id=$1
            ORDER BY mm.sort_order
        """, group_id)

async def get_next_pending_member(group_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT mm.*, pq.user_id, pq.lat, pq.lng, pq.location_name,
                   pq.seat_position, pq.seat_count, u.full_name, u.phone, u.rating
            FROM match_members mm
            JOIN passenger_queue pq ON pq.id=mm.passenger_queue_id
            JOIN users u ON u.id=pq.user_id
            WHERE mm.group_id=$1 AND mm.call_status='pending'
            ORDER BY mm.sort_order LIMIT 1
        """, group_id)

async def set_member_calling(member_id, deadline: datetime):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE match_members SET call_status='calling', call_deadline=$1 WHERE id=$2
        """, deadline, member_id)

async def confirm_member(member_id):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE match_members SET call_status='confirmed', confirmed_at=NOW() WHERE id=$1
        """, member_id)

async def reject_member(member_id):
    """Rad etilgan yo'lovchini 30 daqiqa kutishga qaytarish"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT passenger_queue_id FROM match_members WHERE id=$1", member_id
        )
        await conn.execute(
            "UPDATE match_members SET call_status='rejected' WHERE id=$1", member_id
        )
        if row:
            # 30 daqiqa kutishga qaytarish
            await conn.execute("""
                UPDATE passenger_queue
                SET status='waiting', created_at=NOW() + INTERVAL '30 minutes'
                WHERE id=$1
            """, row['passenger_queue_id'])

async def timeout_member(member_id):
    """5 daqiqa o'tsa — avtomatik rad"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT passenger_queue_id FROM match_members WHERE id=$1", member_id
        )
        await conn.execute(
            "UPDATE match_members SET call_status='timeout' WHERE id=$1", member_id
        )
        if row:
            await conn.execute("""
                UPDATE passenger_queue SET status='waiting', created_at=NOW()
                WHERE id=$1
            """, row['passenger_queue_id'])

async def get_confirmed_members(group_id):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT mm.*, pq.user_id, pq.lat, pq.lng, pq.location_name,
                   pq.seat_position, pq.seat_count, u.full_name, u.phone
            FROM match_members mm
            JOIN passenger_queue pq ON pq.id=mm.passenger_queue_id
            JOIN users u ON u.id=pq.user_id
            WHERE mm.group_id=$1 AND mm.call_status='confirmed'
            ORDER BY mm.sort_order
        """, group_id)

async def count_confirmed(group_id) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM match_members WHERE group_id=$1 AND call_status='confirmed'",
            group_id
        )

async def count_pending(group_id) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM match_members WHERE group_id=$1 AND call_status='pending'",
            group_id
        )

async def get_driver_active_group(user_id):
    """Haydovchining faol match guruhini qaytaradi"""
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT mg.* FROM match_groups mg
            JOIN driver_queue dq ON dq.id=mg.driver_queue_id
            WHERE dq.user_id=$1 AND mg.status IN ('calling','confirmed')
            ORDER BY mg.created_at DESC LIMIT 1
        """, user_id)

async def get_passenger_active_group(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT mm.*, mg.id as group_id, mg.status as group_status,
                   dq.user_id as driver_user_id, dq.seats
            FROM match_members mm
            JOIN match_groups mg ON mg.id=mm.group_id
            JOIN driver_queue dq ON dq.id=mg.driver_queue_id
            JOIN passenger_queue pq ON pq.id=mm.passenger_queue_id
            WHERE pq.user_id=$1 AND mm.call_status IN ('pending','calling','confirmed')
            ORDER BY mm.id DESC LIMIT 1
        """, user_id)

# ─── RATING ───────────────────────────────────────────────
async def save_rating(from_user, to_user, group_id, stars, comment=None):
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM ratings WHERE from_user=$1 AND group_id=$2", from_user, group_id
        )
        if existing:
            return False
        await conn.execute(
            "INSERT INTO ratings(from_user,to_user,group_id,stars,comment) VALUES($1,$2,$3,$4,$5)",
            from_user, to_user, group_id, stars, comment
        )
        await conn.execute("""
            UPDATE users SET
              rating=(SELECT AVG(stars) FROM ratings WHERE to_user=$1),
              rating_count=(SELECT COUNT(*) FROM ratings WHERE to_user=$1)
            WHERE id=$1
        """, to_user)
        return True


# ─── O'RINDIQ TEKSHIRUVI (YANGI) ─────────────────────────

async def add_match_members(group_id: int, passenger_queue_ids: list, seat_overrides: dict = None):
    """
    Yo'lovchilarni guruhga qo'shadi.
    seat_overrides: {pq_id: 'front'|'back'} — matching tomonidan belgilangan haqiqiy o'rindiq
    """
    if seat_overrides is None:
        seat_overrides = {}
    async with pool.acquire() as conn:
        for i, pq_id in enumerate(passenger_queue_ids):
            await conn.execute("""
                INSERT INTO match_members(group_id, passenger_queue_id, sort_order)
                VALUES($1, $2, $3)
                ON CONFLICT DO NOTHING
            """, group_id, pq_id, i)
            await conn.execute(
                "UPDATE passenger_queue SET status='matched' WHERE id=$1", pq_id
            )
            # Agar seat_override bo'lsa — passenger_queue dagi seat_position ni yangilaymiz
            if pq_id in seat_overrides and seat_overrides[pq_id]:
                await conn.execute(
                    "UPDATE passenger_queue SET seat_position=$1 WHERE id=$2",
                    seat_overrides[pq_id], pq_id
                )


async def check_back_seat_available(group_id: int) -> tuple:
    """
    Guruhda orqa o'rindiq bo'sh ekanligini atomik tekshiradi.
    Qaytaradi: (bool, sabab)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Driver seats olish
            dq = await conn.fetchrow("""
                SELECT dq.seats FROM driver_queue dq
                JOIN match_groups mg ON mg.driver_queue_id = dq.id
                WHERE mg.id = $1
            """, group_id)
            if not dq:
                return False, "Guruh topilmadi"

            total_seats = dq['seats']
            back_cap = max(1, total_seats - 1)

            # Hozirgi orqa o'rindiq bandligi
            back_used = await conn.fetchval("""
                SELECT COALESCE(SUM(pq.seat_count), 0)
                FROM match_members mm
                JOIN passenger_queue pq ON pq.id = mm.passenger_queue_id
                WHERE mm.group_id = $1
                  AND pq.seat_position = 'back'
                  AND mm.call_status NOT IN ('rejected', 'timeout')
            """, group_id)

            if back_used >= back_cap:
                return False, f"Orqa o'rindiq to'liq band ({back_cap}/{back_cap})"
            return True, f"Bo'sh joy: {back_cap - back_used} ta"


async def get_seat_summary(group_id: int) -> dict:
    """Guruhning o'rindiq holatini qaytaradi"""
    async with pool.acquire() as conn:
        dq = await conn.fetchrow("""
            SELECT dq.seats FROM driver_queue dq
            JOIN match_groups mg ON mg.driver_queue_id = dq.id
            WHERE mg.id = $1
        """, group_id)
        total = dq['seats'] if dq else 4

        rows = await conn.fetch("""
            SELECT pq.seat_position, COALESCE(SUM(pq.seat_count), 0) as cnt
            FROM match_members mm
            JOIN passenger_queue pq ON pq.id = mm.passenger_queue_id
            WHERE mm.group_id = $1
              AND mm.call_status NOT IN ('rejected', 'timeout')
            GROUP BY pq.seat_position
        """, group_id)

        front_used = next((r['cnt'] for r in rows if r['seat_position'] == 'front'), 0)
        back_used  = next((r['cnt'] for r in rows if r['seat_position'] == 'back'), 0)

        return {
            'total': total,
            'front_cap': 1,
            'back_cap': max(1, total - 1),
            'front_used': front_used,
            'back_used': back_used,
            'front_free': max(0, 1 - front_used),
            'back_free': max(0, (total - 1) - back_used),
        }


async def get_passenger_queue_entry_by_id(pq_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT pq.*, u.full_name, u.phone
            FROM passenger_queue pq
            JOIN users u ON u.id = pq.user_id
            WHERE pq.id = $1
        """, pq_id)


async def get_driver_queue_by_group(group_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT dq.* FROM driver_queue dq
            JOIN match_groups mg ON mg.driver_queue_id = dq.id
            WHERE mg.id = $1
        """, group_id)
