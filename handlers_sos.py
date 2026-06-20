"""
AndTaxi Bot - SOS Emergency Handler
Location capture, admin alert, abuse detection
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from sms_service import sms_service
from ban_system import ban_system
from config import ADMIN_IDS, MESSAGES

logger = logging.getLogger(__name__)

active_sos_sessions = {}

class SOSHandler:
    """SOS emergency handler"""
    
    @staticmethod
    async def initiate_sos(user_id: int, bot) -> bool:
        """
        SOS ni boshlash - location so'rash
        """
        try:
            user = await db.get_user(user_id)
            
            if not user:
                return False
            
            # Check if user is banned
            is_banned, ban_info = await db.check_if_banned(user_id)
            if is_banned:
                return False
            
            # Send location request
            keyboard = types.ReplyKeyboardMarkup(
                keyboard=[
                    [types.KeyboardButton(
                        text="📍 Lokatsiyamni yuborish",
                        request_location=True
                    )],
                    [types.KeyboardButton(text="Bekor qilish")]
                ],
                resize_keyboard=True
            )
            
            await bot.send_message(
                user_id,
                "🚨 **EMERGENCY MODE** 🚨\n\n"
                "Lokatsiyangizni yuboring. Admin-ga xabar boradi.",
                reply_markup=keyboard
            )
            
            active_sos_sessions[user_id] = {
                'started_at': datetime.now(),
                'status': 'waiting_location'
            }
            
            logger.warning(f"🚨 SOS initiated by user {user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error initiating SOS: {e}")
            return False
    
    @staticmethod
    async def handle_sos_location(user_id: int, latitude: float, longitude: float, bot) -> bool:
        """
        SOS lokatsiyasini qayd qilish va admin-ga xabar yuborish
        """
        try:
            user = await db.get_user(user_id)
            
            if not user:
                return False
            
            # Save incident to database
            async with db.pool.acquire() as conn:
                incident_id = await conn.fetchval("""
                INSERT INTO sos_incidents 
                (user_id, location_lat, location_lng, incident_type)
                VALUES ($1, $2, $3, 'emergency_call')
                RETURNING id
                """, user_id, latitude, longitude)
            
            # Prepare message for admins
            location_url = f"https://maps.google.com/?q={latitude},{longitude}"
            
            admin_message = (
                f"🚨 **EMERGENCY SOS** 🚨\n\n"
                f"👤 Foydalanuvchi: {user['first_name']}\n"
                f"📞 Telefon: {user['phone']}\n"
                f"📍 Joylashuvi: {latitude}, {longitude}\n"
                f"🔗 [Google Maps]({location_url})\n"
                f"⏰ Vaqti: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"ID: {incident_id}"
            )
            
            # Send to all admins
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Hal qilindi",
                        callback_data=f"resolve_sos_{incident_id}"
                    )
                ]
            ])
            
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        admin_message,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error sending SOS to admin {admin_id}: {e}")
            
            # Send SMS alert to first admin
            if ADMIN_IDS:
                admin = await db.get_user(ADMIN_IDS[0])
                if admin and admin['phone']:
                    await sms_service.send_sos_alert(
                        admin['phone'],
                        user['first_name'],
                        user['phone'],
                        f"{latitude}, {longitude}"
                    )
            
            # Increment SOS count
            await db.increment_sos_count(user_id)
            
            # Check for abuse
            user_stats = await db.pool.fetchrow(
                "SELECT sos_count FROM user_stats WHERE user_id = $1",
                user_id
            )
            
            if user_stats and user_stats['sos_count'] >= 2:
                is_banned, ban_info = await ban_system.check_and_apply_bans(user_id)
                
                if is_banned:
                    await bot.send_message(
                        user_id,
                        "⚠️ SOS zulmiga uchragan siz 48 soatlik ban oldingiz!"
                    )
            
            # Notify user
            await bot.send_message(
                user_id,
                "✅ Admin-ga xabar yuborildi. Ular tez vaqtda aloqa qiladilar.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            
            active_sos_sessions[user_id]['status'] = 'resolved'
            logger.warning(f"✅ SOS handled for user {user_id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error handling SOS location: {e}")
            return False
    
    @staticmethod
    async def resolve_sos_incident(incident_id: int, admin_id: int, bot) -> bool:
        """
        SOS incident-ni hal qilish
        """
        try:
            async with db.pool.acquire() as conn:
                incident = await conn.fetchrow(
                    "SELECT * FROM sos_incidents WHERE id = $1",
                    incident_id
                )
                
                if not incident:
                    return False
                
                # Mark as resolved
                await conn.execute(
                    "UPDATE sos_incidents SET resolved = TRUE, resolved_at = NOW() WHERE id = $1",
                    incident_id
                )
                
                # Notify user
                user = await db.get_user(incident['user_id'])
                
                await bot.send_message(
                    incident['user_id'],
                    "✅ SOS incident admin tomonidan hal qilindi.\n"
                    "Agar muammo bo'lsa qayta /sos boshlang."
                )
            
            logger.info(f"✅ SOS incident {incident_id} resolved by admin {admin_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error resolving SOS: {e}")
            return False
    
    @staticmethod
    async def cancel_sos(user_id: int, bot) -> bool:
        """
        SOS-ni bekor qilish
        """
        try:
            if user_id in active_sos_sessions:
                del active_sos_sessions[user_id]
            
            await bot.send_message(
                user_id,
                "❌ SOS bekor qilindi.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            
            logger.info(f"🔴 SOS cancelled by user {user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error cancelling SOS: {e}")
            return False


# Singleton
sos_handler = SOSHandler()
