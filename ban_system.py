"""
AndTaxi Bot - Ban & Penalty System (FIXED)
Trip cancellation, enhanced false cancel detection, SOS abuse
"""

import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
from database import db
from sms_service import sms_service

logger = logging.getLogger(__name__)

class BanSystem:
    """Ban va jarima tizimi (takomillashtirilgan)"""
    
    BAN_TYPES = {
        'false_cancel': {
            'description': 'Yolg\'on bekor qilish',
            'threshold': 3,
            'duration_hours': 24
        },
        'sos_abuse': {
            'description': 'SOS zulmi',
            'threshold': 2,
            'duration_hours': 48
        },
        'low_rating': {
            'description': 'Past reyting',
            'threshold': 3.0,
            'duration_hours': 0  # Permanent
        },
        'manual': {
            'description': 'Admin ban',
            'threshold': 0,
            'duration_hours': 0
        }
    }
    
    @staticmethod
    async def check_and_apply_bans(user_id: int) -> Tuple[bool, Optional[dict]]:
        """
        Foydalanuvchi ban-ga layoqli ekanligini tekshirish
        Barcha ban turlari
        """
        try:
            user_stats = await db.pool.fetchrow(
                "SELECT * FROM user_stats WHERE user_id = $1",
                user_id
            )
            
            if not user_stats:
                return False, None
            
            # 1. FALSE CANCEL CHECK
            if user_stats['false_cancel_count'] >= BanSystem.BAN_TYPES['false_cancel']['threshold']:
                duration = BanSystem.BAN_TYPES['false_cancel']['duration_hours']
                ban_until = datetime.now() + timedelta(hours=duration)
                
                await db.ban_user(
                    user_id,
                    'false_cancel',
                    f"{user_stats['false_cancel_count']} marta yolg'on bekor qilish",
                    ban_until
                )
                
                user = await db.get_user(user_id)
                if user and user['phone']:
                    await sms_service.send_ban_notification(
                        user['phone'],
                        'Yolg\'on bekor qilish',
                        ban_until,
                        f"{user_stats['false_cancel_count']} marta yolg'on bekor qilish"
                    )
                
                logger.warning(f"🚫 User {user_id} banned for false cancels")
                return True, {'type': 'false_cancel', 'ban_until': ban_until}
            
            # 2. SOS ABUSE CHECK
            if user_stats['sos_count'] >= BanSystem.BAN_TYPES['sos_abuse']['threshold']:
                duration = BanSystem.BAN_TYPES['sos_abuse']['duration_hours']
                ban_until = datetime.now() + timedelta(hours=duration)
                
                await db.ban_user(
                    user_id,
                    'sos_abuse',
                    f"SOS {user_stats['sos_count']} marta zulmiga uchradi",
                    ban_until
                )
                
                user = await db.get_user(user_id)
                if user and user['phone']:
                    await sms_service.send_ban_notification(
                        user['phone'],
                        'SOS zulmi',
                        ban_until,
                        'SOS tugmasini noto\'g\'ri ishlatish'
                    )
                
                logger.warning(f"🚫 User {user_id} banned for SOS abuse")
                return True, {'type': 'sos_abuse', 'ban_until': ban_until}
            
            # 3. LOW RATING CHECK
            rating, count = await db.get_user_rating(user_id)
            threshold = BanSystem.BAN_TYPES['low_rating']['threshold']
            
            if count >= 5 and rating < threshold:
                ban_until = datetime.now() + timedelta(days=365)
                
                await db.ban_user(
                    user_id,
                    'low_rating',
                    f"Past reyting: {rating}/5 ({count} rating)",
                    ban_until
                )
                
                user = await db.get_user(user_id)
                if user and user['phone']:
                    await sms_service.send_ban_notification(
                        user['phone'],
                        'Past reyting',
                        ban_until,
                        f'Reyting: {rating}/5. Siz hizmatni yaxshi qayta boshlang'
                    )
                
                logger.warning(f"🚫 User {user_id} banned for low rating: {rating}")
                return True, {'type': 'low_rating', 'rating': rating, 'ban_until': ban_until}
            
            return False, None
        
        except Exception as e:
            logger.error(f"Error checking bans: {e}")
            return False, None
    
    # ===== FIX #7: TRIP CANCELLATION WITH PENALTIES =====
    @staticmethod
    async def handle_trip_cancellation(trip_id: int, user_id: int, 
                                      cancelled_by: str, reason: str = None) -> Tuple[bool, Optional[str]]:
        """
        Trip bekor qilishni qayd qilish + penalty qo'llash
        cancelled_by: 'driver' | 'passenger'
        
        Penalty:
        - Passenger: false_cancel_count++, 30 min wait, ban at 3x
        - Driver: reputation penalty (future: rating decreased)
        """
        try:
            success, error = await db.cancel_trip(trip_id, user_id, cancelled_by, reason)
            
            if not success:
                return False, error
            
            user = await db.get_user(user_id)
            
            # FIX #7: Send cancellation notification
            if user and user['phone']:
                await sms_service.send_trip_cancellation_confirmation(
                    user['phone'],
                    reason or "Sababı: Foydalanuvchi"
                )
            
            # Passenger penalty
            if cancelled_by == 'passenger':
                false_cancels = await db.get_false_cancel_count(user_id)
                remaining = 3 - false_cancels
                
                if remaining > 0:
                    # FIX #7: Send warning
                    if user and user['phone']:
                        await sms_service.send_cancellation_penalty_warning(
                            user['phone'],
                            remaining
                        )
                
                # Check for ban
                is_banned, ban_info = await BanSystem.check_and_apply_bans(user_id)
                
                if is_banned:
                    return True, f"⚠️ 3 ta bekor qilish sababli 24 soat ban"
                
                return True, "⏳ 30 daqiqaga taksi so'rasang bo'ladi"
            
            return True, "Trip bekor qilindi"
        
        except Exception as e:
            logger.error(f"Error handling trip cancellation: {e}")
            return False, str(e)
    
    @staticmethod
    async def handle_false_cancel(user_id: int) -> Tuple[bool, Optional[dict]]:
        """
        Yolg'on bekor qilishni qayd qilish (deprecated - use handle_trip_cancellation)
        """
        try:
            await db.increment_false_cancels(user_id)
            is_banned, ban_info = await BanSystem.check_and_apply_bans(user_id)
            
            if is_banned:
                return True, ban_info
            
            return False, {'action': 'wait_30_minutes'}
        
        except Exception as e:
            logger.error(f"Error handling false cancel: {e}")
            return False, None
    
    @staticmethod
    async def check_active_offers(user_id: int) -> bool:
        """Foydalanuvchining faol takliflar bor ekanligini tekshirish"""
        try:
            async with db.pool.acquire() as conn:
                count = await conn.fetchval("""
                SELECT COUNT(*) FROM driver_offers
                WHERE (passenger_id = $1 OR driver_id = $1)
                AND response_status = 'pending'
                AND offer_expires_at > NOW()
                """, user_id)
            
            return count > 0
        except Exception as e:
            logger.error(f"Error checking active offers: {e}")
            return False
    
    @staticmethod
    async def warn_user(user_id: int, warning_type: str, message: str = None) -> bool:
        """Foydalanuvchiga ogohlantirish yuborish"""
        try:
            user = await db.get_user(user_id)
            
            if not user or not user['phone']:
                return False
            
            if not message:
                messages = {
                    'false_cancel': 'Yolg\'on bekor qilish. Yana 2 bor qilsangiz 24 soat ban olasiz.',
                    'low_rating': 'Reyting pasaymoqda. Xizmat sifatini yaxshilang.',
                    'sos_abuse': 'SOS noto\'g\'ri ishlatmang!'
                }
                message = messages.get(warning_type, 'Diqqat!')
            
            await sms_service.send_sms(user['phone'], f"AndTaxi: {message}")
            return True
        
        except Exception as e:
            logger.error(f"Error warning user: {e}")
            return False
    
    @staticmethod
    async def get_ban_info(user_id: int) -> Optional[dict]:
        """Ban haqida ma'lumot"""
        is_banned, ban_info = await db.check_if_banned(user_id)
        
        if is_banned:
            return {
                'type': ban_info['ban_type'],
                'reason': ban_info['reason'],
                'ban_until': ban_info['ban_until'],
                'remaining_time': (ban_info['ban_until'] - datetime.now()).total_seconds()
            }
        
        return None
    
    @staticmethod
    async def unban_user_admin(user_id: int, admin_id: int) -> bool:
        """Admin tomonidan ban o'tkazish"""
        try:
            await db.unban_user(user_id)
            logger.info(f"👤 User {user_id} unbanned by admin {admin_id}")
            
            user = await db.get_user(user_id)
            if user and user['phone']:
                await sms_service.send_sms(
                    user['phone'],
                    "AndTaxi: Ban o'tkazildi! Qayta ishlatishni boshlaysiz."
                )
            
            return True
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            return False


class RatingModerationSystem:
    """
    FIX #9: Admin moderation for ratings
    """
    
    @staticmethod
    async def flag_suspicious_rating(rating_id: int, reason: str) -> bool:
        """Shubhali reyting-larni flag qilish"""
        return await db.flag_rating_for_review(rating_id, reason)
    
    @staticmethod
    async def get_pending_ratings() -> list:
        """Tekshirilishi kerak bo'lgan reyting-lar"""
        return await db.get_flagged_ratings()
    
    @staticmethod
    async def approve_rating(flag_id: int, admin_id: int) -> bool:
        """Reyting-ni tasdiqlash"""
        return await db.resolve_rating_flag(flag_id, admin_id, 'approved')
    
    @staticmethod
    async def delete_rating(flag_id: int, admin_id: int) -> bool:
        """Shubhali reyting-ni o'chirish"""
        return await db.resolve_rating_flag(flag_id, admin_id, 'deleted')
    
    @staticmethod
    async def warn_rater(flag_id: int, admin_id: int) -> bool:
        """Noto'g'ri reyting berganni ogohlantirish"""
        return await db.resolve_rating_flag(flag_id, admin_id, 'warning_to_rater')


# Singletons
ban_system = BanSystem()
rating_moderation = RatingModerationSystem()
