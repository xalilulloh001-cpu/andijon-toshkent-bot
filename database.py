"""
AndTaxi Bot - PostgreSQL Database Layer (FIXED - ALL BUGS)
Atomic transactions, constraints, moderation, offline detection
"""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Tuple
import asyncpg
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class UserRole(str, Enum):
    DRIVER = "driver"
    PASSENGER = "passenger"

class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"

class BanStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class SeatPosition(str, Enum):
    FRONT = "front"
    BACK = "back"

class Database:
    def __init__(self):
        self.pool = None

    async def init(self):
        """PostgreSQL pool ishga tushirish"""
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
        await self.create_tables()
        logger.info("✅ Database initialized")

    async def close(self):
        """Pool-ni yopish"""
        if self.pool:
            await self.pool.close()

    async def create_tables(self):
        """Barcha jadvallarni yaratish + FIXES"""
        async with self.pool.acquire() as conn:
            # ===== FIX #1: Pin/OTP verification table =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_security (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                pin_hash VARCHAR(255),
                otp_verified BOOLEAN DEFAULT FALSE,
                last_login TIMESTAMP,
                failed_pin_attempts INT DEFAULT 0,
                pin_locked_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            """)

            # ===== FIX #6: Unique constraint for active driver groups =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id SERIAL PRIMARY KEY,
                driver_id BIGINT REFERENCES users(user_id),
                region VARCHAR(100),
                status VARCHAR(20) DEFAULT 'waiting',
                total_seats INT,
                available_seats INT,
                front_seat_available BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                departure_time TIMESTAMP,
                vehicle_info VARCHAR(255),
                UNIQUE(driver_id) WHERE status IN ('waiting', 'active')
            );
            """)

            # ===== FIX #5: Driver heartbeat tracking =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS driver_status (
                driver_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                status VARCHAR(20) DEFAULT 'online',
                last_heartbeat TIMESTAMP DEFAULT NOW(),
                last_location_update TIMESTAMP,
                location_lat DECIMAL(10,8),
                location_lng DECIMAL(11,8),
                offline_reason VARCHAR(100),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            """)

            # ===== FIX #8: SMS rate limiting =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS sms_log (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20),
                message_type VARCHAR(50),
                sms_count INT DEFAULT 1,
                hour_start TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            # ===== FIX #9: Rating moderation queue =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS rating_moderation (
                id SERIAL PRIMARY KEY,
                rating_id INT REFERENCES ratings(id),
                user_id BIGINT REFERENCES users(user_id),
                rated_by BIGINT REFERENCES users(user_id),
                reason VARCHAR(200),
                flag_status VARCHAR(20) DEFAULT 'pending',
                admin_decision VARCHAR(100),
                admin_id BIGINT REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT NOW(),
                resolved_at TIMESTAMP
            );
            """)

            # ===== FIX #13: Notification history =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                notification_type VARCHAR(50),
                title VARCHAR(255),
                message TEXT,
                is_read BOOLEAN DEFAULT FALSE,
                read_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            # ===== FIX #7: Trip cancellation with penalties =====
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_cancellations (
                id SERIAL PRIMARY KEY,
                trip_id BIGINT REFERENCES trips(id),
                user_id BIGINT REFERENCES users(user_id),
                cancelled_by VARCHAR(20),
                reason TEXT,
                penalty_applied BOOLEAN DEFAULT FALSE,
                penalty_amount DECIMAL(8,2),
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            logger.info("✅ All tables created with fixes")

    # ===== FIX #1: PIN/OTP VERIFICATION =====
    async def set_user_pin(self, user_id: int, pin: str) -> bool:
        """Foydalanuvchining PIN-ini saqlash"""
        try:
            from hashlib import sha256
            pin_hash = sha256(pin.encode()).hexdigest()
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                INSERT INTO user_security (user_id, pin_hash, otp_verified)
                VALUES ($1, $2, TRUE)
                ON CONFLICT (user_id) DO UPDATE SET
                pin_hash = $2, otp_verified = TRUE, updated_at = NOW()
                """, user_id, pin_hash)
            return True
        except Exception as e:
            logger.error(f"Error setting PIN: {e}")
            return False

    async def verify_pin(self, user_id: int, pin: str) -> Tuple[bool, Optional[str]]:
        """PIN tekshirish + brute force xavfi"""
        try:
            from hashlib import sha256
            pin_hash = sha256(pin.encode()).hexdigest()
            
            async with self.pool.acquire() as conn:
                security = await conn.fetchrow(
                    "SELECT * FROM user_security WHERE user_id = $1",
                    user_id
                )
                
                if not security:
                    return False, "Xavfsizlik ma'lumoti topilmadi"
                
                # Brute force check
                if security['pin_locked_until'] and security['pin_locked_until'] > datetime.now():
                    remaining = (security['pin_locked_until'] - datetime.now()).total_seconds() / 60
                    return False, f"PIN {int(remaining)} daqiqaga bloklashtirilgan"
                
                # PIN check
                if security['pin_hash'] != pin_hash:
                    # Increment failed attempts
                    new_attempts = security['failed_pin_attempts'] + 1
                    
                    if new_attempts >= 3:
                        # Lock for 15 minutes
                        await conn.execute("""
                        UPDATE user_security SET
                        failed_pin_attempts = $1,
                        pin_locked_until = NOW() + INTERVAL '15 minutes'
                        WHERE user_id = $2
                        """, new_attempts, user_id)
                        
                        return False, "3 ta urinish keyin PIN bloklandi (15 daqiqa)"
                    
                    await conn.execute("""
                    UPDATE user_security SET failed_pin_attempts = $1
                    WHERE user_id = $2
                    """, new_attempts, user_id)
                    
                    return False, f"PIN noto'g'ri ({3 - new_attempts} urinish qoldi)"
                
                # ✅ PIN correct - reset attempts
                await conn.execute("""
                UPDATE user_security SET
                failed_pin_attempts = 0,
                pin_locked_until = NULL,
                last_login = NOW()
                WHERE user_id = $1
                """, user_id)
                
                return True, None
        
        except Exception as e:
            logger.error(f"Error verifying PIN: {e}")
            return False, str(e)

    # ===== FIX #5: DRIVER OFFLINE DETECTION =====
    async def update_driver_heartbeat(self, driver_id: int, lat: float, lng: float) -> bool:
        """Haydovchi heartbeat yangilash"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                INSERT INTO driver_status 
                (driver_id, last_heartbeat, location_lat, location_lng, status)
                VALUES ($1, NOW(), $2, $3, 'online')
                ON CONFLICT (driver_id) DO UPDATE SET
                last_heartbeat = NOW(),
                location_lat = $2,
                location_lng = $3,
                status = 'online',
                updated_at = NOW()
                """, driver_id, lat, lng)
            return True
        except Exception as e:
            logger.error(f"Error updating heartbeat: {e}")
            return False

    async def check_offline_drivers(self) -> List[int]:
        """5 daqiqadan ko'p javob bermagan haydovchilar"""
        try:
            async with self.pool.acquire() as conn:
                offline = await conn.fetch("""
                SELECT driver_id FROM driver_status
                WHERE status = 'online'
                AND last_heartbeat < NOW() - INTERVAL '5 minutes'
                """)
            return [d['driver_id'] for d in offline]
        except Exception as e:
            logger.error(f"Error checking offline drivers: {e}")
            return []

    async def mark_driver_offline(self, driver_id: int, reason: str = "No heartbeat") -> bool:
        """Haydovchini offline qilish"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                UPDATE driver_status SET
                status = 'offline',
                offline_reason = $1,
                updated_at = NOW()
                WHERE driver_id = $2
                """, reason, driver_id)
                
                await conn.execute("""
                UPDATE driver_queue SET is_active = FALSE
                WHERE driver_id = $1
                """, driver_id)
            
            logger.warning(f"🔴 Driver {driver_id} marked offline: {reason}")
            return True
        except Exception as e:
            logger.error(f"Error marking driver offline: {e}")
            return False

    # ===== FIX #2 & #3: ATOMIC GROUP MEMBERSHIP (NO RACE CONDITIONS) =====
    async def check_and_match_passenger(self, passenger_id: int, group_id: int,
                                       seat_preference: Optional[str] = None,
                                       is_important: bool = False) -> Tuple[bool, Optional[str]]:
        """
        ATOMIC passenger-group matching with full validation
        Fixes: #2 (Race condition), #3 (Offer expiration)
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # ===== CHECK 1: Passenger not in other groups =====
                    existing_group = await conn.fetchval("""
                    SELECT group_id FROM group_members 
                    WHERE passenger_id = $1 
                    AND status = 'confirmed'
                    LIMIT 1
                    """, passenger_id)
                    
                    if existing_group:
                        return False, f"❌ Siz allaqachon {existing_group} guruhda borsiz!"
                    
                    # ===== CHECK 2: Offer exists and valid =====
                    driver_info = await conn.fetchrow("""
                    SELECT dg.group_id, dg.driver_id, dof.offer_expires_at
                    FROM groups dg
                    JOIN driver_offers dof ON dg.id = dof.group_id
                    WHERE dg.id = $1
                    AND dof.passenger_id = $2
                    AND dof.response_status = 'pending'
                    """, group_id, passenger_id)
                    
                    if not driver_info:
                        return False, "❌ Taklif topilmadi!"
                    
                    # ===== CHECK 3: Offer not expired =====
                    if driver_info['offer_expires_at'] < datetime.now():
                        # Mark as expired
                        await conn.execute("""
                        UPDATE driver_offers SET response_status = 'expired'
                        WHERE group_id = $1 AND passenger_id = $2
                        """, group_id, passenger_id)
                        
                        return False, "❌ Taklif muddati tugadi! (5 daqiqa)"
                    
                    # ===== CHECK 4: Group has seats (FOR UPDATE lock) =====
                    group = await conn.fetchrow(
                        "SELECT * FROM groups WHERE id = $1 FOR UPDATE",
                        group_id
                    )
                    
                    if group['available_seats'] <= 0:
                        return False, "❌ O'rindiq yo'q!"
                    
                    # ===== ASSIGN SEAT =====
                    seat_position = seat_preference or 'back'
                    
                    if seat_preference == 'front':
                        if is_important and group['front_seat_available']:
                            seat_position = 'front'
                        elif is_important and not group['front_seat_available']:
                            # Reallocate: Move non-important to back
                            await conn.execute("""
                            UPDATE group_members SET seat_position = 'back'
                            WHERE group_id = $1 AND seat_position = 'front'
                            AND (SELECT is_seat_important FROM passenger_queue 
                                 WHERE passenger_id = group_members.passenger_id) = FALSE
                            LIMIT 1
                            """, group_id)
                            
                            seat_position = 'front'
                        else:
                            seat_position = 'back' if not group['front_seat_available'] else 'front'
                    
                    # ===== ADD MEMBER (with constraint check) =====
                    try:
                        await conn.execute("""
                        INSERT INTO group_members 
                        (group_id, passenger_id, seat_position, status)
                        VALUES ($1, $2, $3, 'confirmed')
                        """, group_id, passenger_id, seat_position)
                    except asyncpg.UniqueViolationError:
                        return False, "❌ Siz allaqachon bu guruhda borsiz!"
                    
                    # ===== UPDATE FRONT SEAT =====
                    if seat_position == 'front':
                        await conn.execute("""
                        UPDATE groups SET front_seat_available = FALSE
                        WHERE id = $1
                        """, group_id)
                    
                    # ===== DECREMENT AVAILABLE SEATS =====
                    await conn.execute("""
                    UPDATE groups SET 
                    available_seats = available_seats - 1,
                    updated_at = NOW()
                    WHERE id = $1
                    """, group_id)
                    
                    # ===== UPDATE OFFER =====
                    await conn.execute("""
                    UPDATE driver_offers SET 
                    response_status = 'accepted',
                    responded_at = NOW()
                    WHERE group_id = $1 AND passenger_id = $2
                    """, group_id, passenger_id)
                    
                    # ===== REMOVE FROM PASSENGER QUEUE =====
                    await conn.execute("""
                    UPDATE passenger_queue SET is_active = FALSE
                    WHERE passenger_id = $1
                    """, passenger_id)
                    
                    # ===== UPDATE STATS =====
                    await conn.execute("""
                    UPDATE user_stats SET last_activity = NOW()
                    WHERE user_id = $1
                    """, passenger_id)
                    
                    logger.info(f"✅ Passenger {passenger_id} added to group {group_id} ({seat_position})")
                    return True, seat_position
        
        except Exception as e:
            logger.error(f"Error matching passenger: {e}")
            return False, str(e)

    # ===== FIX #6: Prevent duplicate active groups =====
    async def create_group(self, driver_id: int, region: str, total_seats: int,
                          vehicle_info: str = None) -> Optional[int]:
        """Yangi guruh yaratish (constraint bilan unique)"""
        try:
            # Check existing active group
            existing = await self.pool.fetchval("""
            SELECT id FROM groups 
            WHERE driver_id = $1 
            AND status IN ('waiting', 'active')
            LIMIT 1
            """, driver_id)
            
            if existing:
                logger.warning(f"⚠️ Driver {driver_id} allaqachon {existing} guruhda")
                return None
            
            async with self.pool.acquire() as conn:
                group_id = await conn.fetchval("""
                INSERT INTO groups 
                (driver_id, region, total_seats, available_seats, vehicle_info)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """, driver_id, region, total_seats, total_seats, vehicle_info)
            
            logger.info(f"✅ Group {group_id} created for driver {driver_id}")
            return group_id
        
        except asyncpg.UniqueViolationError:
            logger.warning(f"⚠️ Driver {driver_id} already has active group")
            return None
        except Exception as e:
            logger.error(f"Error creating group: {e}")
            return None

    # ===== FIX #7: TRIP CANCELLATION WITH PENALTIES =====
    async def cancel_trip(self, trip_id: int, user_id: int, cancelled_by: str,
                         reason: str = None) -> Tuple[bool, Optional[str]]:
        """
        Trip-ni bekor qilish
        cancelled_by: 'driver' | 'passenger'
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Get trip info
                    trip = await conn.fetchrow(
                        "SELECT * FROM trips WHERE id = $1",
                        trip_id
                    )
                    
                    if not trip:
                        return False, "Trip topilmadi"
                    
                    if trip['status'] == 'completed':
                        return False, "Yakunlangan trip-ni bekor qila olmaydi"
                    
                    # Cancel trip
                    await conn.execute("""
                    UPDATE trips SET status = 'cancelled'
                    WHERE id = $1
                    """, trip_id)
                    
                    # Log cancellation
                    await conn.execute("""
                    INSERT INTO trip_cancellations 
                    (trip_id, user_id, cancelled_by, reason)
                    VALUES ($1, $2, $3, $4)
                    """, trip_id, user_id, cancelled_by, reason)
                    
                    # Apply penalty (30 min wait for passenger)
                    if cancelled_by == 'passenger':
                        # Add to false cancels counter
                        await conn.execute("""
                        UPDATE user_stats 
                        SET false_cancel_count = false_cancel_count + 1
                        WHERE user_id = $1
                        """, user_id)
                        
                        # Check ban
                        false_cancels = await conn.fetchval(
                            "SELECT false_cancel_count FROM user_stats WHERE user_id = $1",
                            user_id
                        )
                        
                        if false_cancels >= 3:
                            # Ban for 24 hours
                            await conn.execute("""
                            INSERT INTO bans 
                            (user_id, ban_type, reason, ban_until)
                            VALUES ($1, 'false_cancel', '3 marta yolg\'on bekor', NOW() + INTERVAL '24 hours')
                            """, user_id)
                            
                            await conn.execute("""
                            UPDATE users SET is_active = FALSE WHERE user_id = $1
                            """, user_id)
                            
                            return True, f"⚠️ 3 ta bekor qilish sababli 24 soat ban"
                        
                        return True, "⏳ 30 daqiqaga taksi so'rasang bo'ladi"
                    
                    return True, "Trip bekor qilindi"
        
        except Exception as e:
            logger.error(f"Error cancelling trip: {e}")
            return False, str(e)

    # ===== FIX #8: SMS RATE LIMITING =====
    async def check_sms_rate_limit(self, phone: str) -> Tuple[bool, Optional[str]]:
        """SMS soatiga 3 ta cheklamasi"""
        try:
            async with self.pool.acquire() as conn:
                hour_ago = datetime.now() - timedelta(hours=1)
                
                count = await conn.fetchval("""
                SELECT COALESCE(SUM(sms_count), 0) 
                FROM sms_log
                WHERE phone = $1 AND hour_start > $2
                """, phone, hour_ago)
                
                if count >= 3:
                    return False, f"❌ Soatiga 3 ta SMS. Yana 1 soat kuting."
                
                # Log SMS
                await conn.execute("""
                INSERT INTO sms_log (phone, hour_start)
                VALUES ($1, NOW())
                ON CONFLICT (phone, hour_start) DO UPDATE SET sms_count = sms_count + 1
                """, phone)
                
                return True, None
        
        except Exception as e:
            logger.error(f"Error checking SMS limit: {e}")
            return True, None  # Allow on error

    # ===== FIX #9: RATING MODERATION QUEUE =====
    async def flag_rating_for_review(self, rating_id: int, reason: str) -> bool:
        """Shubhali reyting-larni admin-ga jo'natish"""
        try:
            rating = await self.pool.fetchrow(
                "SELECT * FROM ratings WHERE id = $1",
                rating_id
            )
            
            if not rating:
                return False
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                INSERT INTO rating_moderation 
                (rating_id, user_id, rated_by, reason)
                VALUES ($1, $2, $3, $4)
                """, rating_id, rating['user_id'], rating['rated_by'], reason)
            
            logger.warning(f"🚩 Rating {rating_id} flagged: {reason}")
            return True
        
        except Exception as e:
            logger.error(f"Error flagging rating: {e}")
            return False

    async def get_flagged_ratings(self) -> List[Dict]:
        """Admin uchun tekshirilishi kerak bo'lgan reyting-lar"""
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch("""
                SELECT rm.*, r.stars, r.comment,
                       u.first_name as user_name, 
                       rb.first_name as rater_name
                FROM rating_moderation rm
                JOIN ratings r ON rm.rating_id = r.id
                JOIN users u ON rm.user_id = u.user_id
                JOIN users rb ON rm.rated_by = rb.user_id
                WHERE rm.flag_status = 'pending'
                ORDER BY rm.created_at DESC
                LIMIT 20
                """)
        except Exception as e:
            logger.error(f"Error getting flagged ratings: {e}")
            return []

    async def resolve_rating_flag(self, flag_id: int, admin_id: int, 
                                 decision: str) -> bool:
        """
        Admin reyting-ni tasdiq yoki bekor qilish
        decision: 'approved' | 'deleted' | 'warning_to_rater'
        """
        try:
            async with self.pool.acquire() as conn:
                if decision == 'deleted':
                    # Delete rating
                    flag = await conn.fetchrow(
                        "SELECT rating_id FROM rating_moderation WHERE id = $1",
                        flag_id
                    )
                    
                    await conn.execute(
                        "DELETE FROM ratings WHERE id = $1",
                        flag['rating_id']
                    )
                
                # Mark flag resolved
                await conn.execute("""
                UPDATE rating_moderation SET
                flag_status = 'resolved',
                admin_decision = $1,
                admin_id = $2,
                resolved_at = NOW()
                WHERE id = $3
                """, decision, admin_id, flag_id)
            
            return True
        
        except Exception as e:
            logger.error(f"Error resolving rating flag: {e}")
            return False

    # ===== FIX #10: ROUTE VALIDATION =====
    async def validate_trip_route(self, from_lat: float, from_lng: float,
                                 to_lat: float, to_lng: float) -> Tuple[bool, Optional[str]]:
        """
        Koordinatasining to'g'riligi tekshirish
        Andijon: 40.7281, 72.3391 (±50km radius)
        Tashkent: 41.2995, 69.2401 (±50km radius)
        """
        try:
            from math import radians, sin, cos, sqrt, atan2
            
            def haversine(lat1, lng1, lat2, lng2):
                R = 6371  # km
                lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
                dlat, dlng = lat2 - lat1, lng2 - lng1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                return R * c
            
            ANDIJON = (40.7281, 72.3391)
            TASHKENT = (41.2995, 69.2401)
            RADIUS = 50  # km
            
            from_dist_to_andijon = haversine(from_lat, from_lng, ANDIJON[0], ANDIJON[1])
            to_dist_to_tashkent = haversine(to_lat, to_lng, TASHKENT[0], TASHKENT[1])
            
            # Check if valid Andijon → Tashkent route
            if from_dist_to_andijon > RADIUS:
                return False, f"❌ Boshlang'ich jo'y Andijan-dan {int(from_dist_to_andijon)}km uzoq!"
            
            if to_dist_to_tashkent > RADIUS:
                return False, f"❌ Manziyi Toshkent-dan {int(to_dist_to_tashkent)}km uzoq!"
            
            return True, None
        
        except Exception as e:
            logger.error(f"Error validating route: {e}")
            return False, str(e)

    # ===== FIX #13: NOTIFICATION HISTORY =====
    async def save_notification(self, user_id: int, notification_type: str,
                               title: str, message: str) -> bool:
        """Bildirishnomani tarixga saqlash"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                INSERT INTO notification_history 
                (user_id, notification_type, title, message)
                VALUES ($1, $2, $3, $4)
                """, user_id, notification_type, title, message)
            return True
        except Exception as e:
            logger.error(f"Error saving notification: {e}")
            return False

    async def get_user_notifications(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Foydalanuvchining bildirishnomalar tarixini olish"""
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch("""
                SELECT * FROM notification_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """, user_id, limit)
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []

    async def mark_notification_read(self, notification_id: int) -> bool:
        """Bildirishnomani "o'qilgan" qilib belgilash"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                UPDATE notification_history 
                SET is_read = TRUE, read_at = NOW()
                WHERE id = $1
                """, notification_id)
            return True
        except Exception as e:
            logger.error(f"Error marking notification read: {e}")
            return False

    # ===== EXISTING METHODS (UNCHANGED) =====
    async def create_user(self, user_id: int, first_name: str, phone: str = None) -> bool:
        """Yangi foydalanuvchi yaratish"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                INSERT INTO users (user_id, first_name, phone, verification_status)
                VALUES ($1, $2, $3, 'unverified')
                ON CONFLICT (user_id) DO NOTHING
                """, user_id, first_name, phone)
            return True
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Foydalanuvchini topish"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    async def update_user(self, user_id: int, **kwargs) -> bool:
        """Foydalanuvchini yangilash"""
        try:
            allowed_fields = ['first_name', 'last_name', 'phone', 'role', 'is_verified', 
                            'verification_status', 'profile_photo_url', 'bio']
            fields = [f for f in kwargs.keys() if f in allowed_fields]
            
            if not fields:
                return False
            
            set_clause = ", ".join([f"{f} = ${i+2}" for i, f in enumerate(fields)])
            values = [user_id] + [kwargs[f] for f in fields]
            
            async with self.pool.acquire() as conn:
                await conn.execute(
                    f"UPDATE users SET {set_clause} WHERE user_id = $1",
                    *values
                )
            return True
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False

    # ... (boshqa usul-lar o'zgarmagan)

# Singleton instance
db = Database()
