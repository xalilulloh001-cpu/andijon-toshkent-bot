import asyncpg
import os
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
                is_approved BOOLEAN DEFAULT TRUE,
                is_blocked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS drivers (
                user_id BIGINT PRIMARY KEY REFERENCES users(id),
                car_model TEXT,
                car_number TEXT,
                car_color TEXT,
                is_approved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS driver_trips (
                id SERIAL PRIMARY KEY,
                driver_id BIGINT REFERENCES users(id),
                direction TEXT NOT NULL,
                seats INT NOT NULL,
                depart_time TIMESTAMPTZ NOT NULL,
                lat FLOAT,
                lng FLOAT,
                status TEXT DEFAULT 'waiting',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS passenger_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id),
                direction TEXT NOT NULL,
                seat_position TEXT NOT NULL,
                seat_count INT NOT NULL,
                time_from TIMESTAMPTZ NOT NULL,
                time_to TIMESTAMPTZ NOT NULL,
                lat FLOAT,
                lng FLOAT,
                status TEXT DEFAULT 'waiting',
                matched_trip_id INT REFERENCES driver_trips(id),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS ratings (
                id SERIAL PRIMARY KEY,
                from_user BIGINT REFERENCES users(id),
                to_user BIGINT REFERENCES users(id),
                trip_id INT REFERENCES driver_trips(id),
                stars INT CHECK (stars BETWEEN 1 AND 5),
                comment TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    return pool


async def get_pool():
    return pool


async def get_user(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)


async def create_user(user_id: int, full_name: str, phone: str, lang: str = 'uz'):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, full_name, phone, lang) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            user_id, full_name, phone, lang
        )


async def set_user_role(user_id: int, role: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET role=$1 WHERE id=$2", role, user_id)


async def set_user_lang(user_id: int, lang: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET lang=$1 WHERE id=$2", lang, user_id)


async def register_driver(user_id: int, car_model: str, car_number: str, car_color: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO drivers (user_id, car_model, car_number, car_color, is_approved)
               VALUES ($1,$2,$3,$4,TRUE)
               ON CONFLICT (user_id) DO UPDATE SET car_model=$2, car_number=$3, car_color=$4""",
            user_id, car_model, car_number, car_color
        )
        await conn.execute("UPDATE users SET role='driver' WHERE id=$1", user_id)


async def get_active_trip(driver_id: int):
    """Haydovchining faol trippi bor-yo'qligini tekshiradi"""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id FROM driver_trips WHERE driver_id=$1 AND status IN ('waiting','active') LIMIT 1",
            driver_id
        )


async def create_driver_trip(driver_id, direction, seats, depart_time, lat, lng):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO driver_trips (driver_id, direction, seats, depart_time, lat, lng)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
            driver_id, direction, seats, depart_time, lat, lng
        )
        return row['id']


async def create_passenger_request(user_id, direction, seat_position, seat_count, time_from, time_to, lat, lng):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO passenger_requests
               (user_id, direction, seat_position, seat_count, time_from, time_to, lat, lng)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            user_id, direction, seat_position, seat_count, time_from, time_to, lat, lng
        )
        return row['id']


async def get_active_passenger_request(user_id: int):
    """Yo'lovchining faol so'rovini qaytaradi"""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """SELECT pr.*, dt.driver_id, dt.direction as trip_dir
               FROM passenger_requests pr
               LEFT JOIN driver_trips dt ON dt.id = pr.matched_trip_id
               WHERE pr.user_id=$1 AND pr.status IN ('waiting','matched')
               ORDER BY pr.created_at DESC LIMIT 1""",
            user_id
        )


async def get_waiting_passengers(direction: str, depart_time, max_time_diff_hours=2):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT pr.*, u.full_name, u.phone, u.rating
               FROM passenger_requests pr
               JOIN users u ON u.id = pr.user_id
               WHERE pr.direction = $1
                 AND pr.status = 'waiting'
                 AND pr.time_from <= $2 + INTERVAL '2 hours'
                 AND pr.time_to >= $2 - INTERVAL '2 hours'
               ORDER BY pr.created_at""",
            direction, depart_time
        )


async def get_waiting_passengers_extended(direction: str, depart_time):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT pr.*, u.full_name, u.phone, u.rating
               FROM passenger_requests pr
               JOIN users u ON u.id = pr.user_id
               WHERE pr.direction = $1
                 AND pr.status = 'waiting'
                 AND pr.time_from <= $2 + INTERVAL '2 hours'
                 AND pr.time_to >= $2 - INTERVAL '2 hours'
               ORDER BY pr.created_at""",
            direction, depart_time
        )


async def match_passenger_to_trip(passenger_id: int, trip_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE passenger_requests SET status='matched', matched_trip_id=$1 WHERE id=$2",
            trip_id, passenger_id
        )


async def reject_passenger(passenger_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE passenger_requests SET status='waiting', matched_trip_id=NULL WHERE id=$1",
            passenger_id
        )


async def complete_trip(trip_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE driver_trips SET status='completed' WHERE id=$1", trip_id)
        rows = await conn.fetch(
            "SELECT user_id FROM passenger_requests WHERE matched_trip_id=$1 AND status='matched'",
            trip_id
        )
        await conn.execute(
            "UPDATE passenger_requests SET status='completed' WHERE matched_trip_id=$1",
            trip_id
        )
        return [r['user_id'] for r in rows]


async def save_rating(from_user: int, to_user: int, trip_id: int, stars: int, comment: str = None):
    async with pool.acquire() as conn:
        # Bir safar uchun ikki marta baho berishni oldini olish
        existing = await conn.fetchval(
            "SELECT id FROM ratings WHERE from_user=$1 AND trip_id=$2",
            from_user, trip_id
        )
        if existing:
            return False

        await conn.execute(
            "INSERT INTO ratings (from_user, to_user, trip_id, stars, comment) VALUES ($1,$2,$3,$4,$5)",
            from_user, to_user, trip_id, stars, comment
        )
        await conn.execute(
            """UPDATE users SET
               rating = (SELECT AVG(stars) FROM ratings WHERE to_user=$1),
               rating_count = (SELECT COUNT(*) FROM ratings WHERE to_user=$1)
               WHERE id=$1""",
            to_user
        )
        return True


async def cancel_passenger_request(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE passenger_requests SET status='cancelled' WHERE user_id=$1 AND status IN ('waiting','matched')",
            user_id
        )


async def cancel_driver_trip(trip_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id FROM passenger_requests WHERE matched_trip_id=$1 AND status='matched'",
            trip_id
        )
        await conn.execute(
            "UPDATE passenger_requests SET status='waiting', matched_trip_id=NULL WHERE matched_trip_id=$1",
            trip_id
        )
        await conn.execute("UPDATE driver_trips SET status='cancelled' WHERE id=$1", trip_id)
        return [r['user_id'] for r in rows]


async def get_driver_info(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT d.*, u.full_name, u.phone, u.rating FROM drivers d JOIN users u ON u.id=d.user_id WHERE d.user_id=$1",
            user_id
        )


async def get_driver_stats(user_id: int):
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM driver_trips WHERE driver_id=$1 AND status='completed'", user_id
        )
        today = await conn.fetchval(
            "SELECT COUNT(*) FROM driver_trips WHERE driver_id=$1 AND status='completed' AND DATE(created_at)=CURRENT_DATE",
            user_id
        )
        rating = await conn.fetchval("SELECT rating FROM users WHERE id=$1", user_id)
        rating_count = await conn.fetchval("SELECT rating_count FROM users WHERE id=$1", user_id)
        return {'total': total, 'today': today, 'rating': rating, 'rating_count': rating_count}


async def get_trip_history(user_id: int, role: str, limit: int = 10):
    """Foydalanuvchi safar tarixini qaytaradi"""
    async with pool.acquire() as conn:
        if role == 'driver':
            return await conn.fetch(
                """SELECT id, direction, seats, depart_time, status, created_at
                   FROM driver_trips WHERE driver_id=$1
                   ORDER BY created_at DESC LIMIT $2""",
                user_id, limit
            )
        else:
            return await conn.fetch(
                """SELECT pr.id, pr.direction, pr.seat_count, pr.time_from, pr.status, pr.created_at,
                          u.full_name as driver_name, d.car_model, d.car_number
                   FROM passenger_requests pr
                   LEFT JOIN driver_trips dt ON dt.id = pr.matched_trip_id
                   LEFT JOIN users u ON u.id = dt.driver_id
                   LEFT JOIN drivers d ON d.user_id = dt.driver_id
                   WHERE pr.user_id=$1
                   ORDER BY pr.created_at DESC LIMIT $2""",
                user_id, limit
            )


async def update_driver_car(user_id: int, car_model: str, car_number: str, car_color: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE drivers SET car_model=$1, car_number=$2, car_color=$3 WHERE user_id=$4",
            car_model, car_number, car_color, user_id
        )


async def get_all_users_count():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


async def get_all_drivers_count():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM drivers WHERE is_approved=TRUE")


async def get_all_trips_count():
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM driver_trips WHERE status='completed'")


async def get_all_user_ids():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users WHERE is_blocked=FALSE")
        return [r['id'] for r in rows]


async def block_user(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked=TRUE WHERE id=$1", user_id)


async def unblock_user(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked=FALSE WHERE id=$1", user_id)


# ─── O'rindiq tekshiruvi ───────────────────────────────────────────────────

async def get_matched_passengers_for_trip(trip_id: int):
    """Trip ga band qilingan barcha yo'lovchilarni qaytaradi"""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT pr.user_id, pr.seat_position, pr.seat_count, pr.status
               FROM passenger_requests pr
               WHERE pr.matched_trip_id = $1
                 AND pr.status = 'matched'""",
            trip_id
        )


async def get_seat_stats(trip_id: int, total_seats: int) -> dict:
    """
    Trip uchun o'rindiq statistikasini qaytaradi:
    - front_booked: oldi o'rindiqda band joylar
    - front_available: oldi o'rindiqda bo'sh joy (har doim max 1)
    - back_booked: orqa o'rindiqda band joylar
    - back_available: orqa o'rindiqda bo'sh joylar
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT seat_position, SUM(seat_count) as total
               FROM passenger_requests
               WHERE matched_trip_id = $1 AND status = 'matched'
               GROUP BY seat_position""",
            trip_id
        )

    stats = {"front_booked": 0, "back_booked": 0}
    for row in rows:
        if row["seat_position"] == "front":
            stats["front_booked"] = row["total"]
        else:
            stats["back_booked"] = row["total"]

    stats["front_available"] = max(0, 1 - stats["front_booked"])
    stats["back_available"] = max(0, (total_seats - 1) - stats["back_booked"])
    stats["total_available"] = stats["front_available"] + stats["back_available"]
    return stats


async def check_and_match_passenger(
    passenger_req_id: int,
    trip_id: int,
    seat_position: str,
    seat_count: int,
    total_trip_seats: int
) -> tuple[bool, str]:
    """
    Atomik tekshiruv + band qilish.
    Race condition bo'lmasligi uchun FOR UPDATE lock ishlatiladi.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock bilan hozirgi band joylarni olamiz
            rows = await conn.fetch(
                """SELECT seat_position, seat_count
                   FROM passenger_requests
                   WHERE matched_trip_id = $1
                     AND status = 'matched'
                   FOR UPDATE""",
                trip_id
            )

            # Hisoblash
            booked_front = sum(r["seat_count"] for r in rows if r["seat_position"] == "front")
            booked_back  = sum(r["seat_count"] for r in rows if r["seat_position"] == "back")

            front_cap = 1
            back_cap  = max(1, total_trip_seats - 1)

            if seat_position == "front":
                if booked_front + seat_count > front_cap:
                    avail = max(0, front_cap - booked_front)
                    return False, f"Oldi o'rindiq to'liq band" if avail == 0 else f"Oldi o'rindiqda faqat {avail} ta joy bor"
            else:
                if booked_back + seat_count > back_cap:
                    avail = max(0, back_cap - booked_back)
                    return False, f"Orqa o'rindiq to'liq band" if avail == 0 else f"Orqa o'rindiqda faqat {avail} ta joy bor"

            # Bo'sh — band qilamiz
            await conn.execute(
                """UPDATE passenger_requests
                   SET status = 'matched', matched_trip_id = $1
                   WHERE id = $2""",
                trip_id, passenger_req_id
            )
            return True, "ok"
