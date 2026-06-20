"""
AndTaxi Bot - Verification Service
SMS o'rniga Telegram OTP (BEPUL)
"""

import random
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class VerificationService:
    """
    Telegram OTP - SMS shart emas, 100% bepul!
    Kod Telegram ichida yuboriladi.
    """

    @staticmethod
    def generate_code() -> str:
        """6 raqamli tasdiqlash kodi"""
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])

    @staticmethod
    async def send_code_via_telegram(bot, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Tasdiqlash kodini Telegram orqali yuborish (SMS o'rniga)
        """
        try:
            code = VerificationService.generate_code()

            await bot.send_message(
                user_id,
                f"🔐 *Tasdiqlash kodi:* `{code}`\n\n"
                f"⏰ 10 daqiqa ichida kiriting.\n"
                f"❌ Bu kodni hech kimga bermang!",
                parse_mode="Markdown"
            )

            logger.info(f"✅ OTP sent via Telegram to user {user_id}")
            return True, code

        except Exception as e:
            logger.error(f"Error sending OTP: {e}")
            return False, None

    @staticmethod
    async def send_ban_notification_tg(bot, user_id: int,
                                       reason: str, ban_until: datetime) -> bool:
        """Ban xabari Telegram orqali"""
        try:
            await bot.send_message(
                user_id,
                f"🚫 *Hisobingiz bloklandi!*\n\n"
                f"Sababi: {reason}\n"
                f"Muddati: {ban_until.strftime('%d.%m.%Y %H:%M')} gacha\n\n"
                f"Savol bo'lsa: @andtaxi_support",
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            logger.error(f"Error sending ban notification: {e}")
            return False

    @staticmethod
    async def send_sos_alert_tg(bot, admin_ids: list,
                                user_name: str, user_id: int,
                                lat: float, lng: float) -> bool:
        """SOS xabari admin-larga Telegram orqali"""
        try:
            location_url = f"https://maps.google.com/?q={lat},{lng}"
            text = (
                f"🚨 *SOS EMERGENCY!*\n\n"
                f"👤 {user_name} (ID: {user_id})\n"
                f"📍 [{lat:.4f}, {lng:.4f}]({location_url})\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            for admin_id in admin_ids:
                try:
                    await bot.send_message(admin_id, text, parse_mode="Markdown")
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.error(f"Error sending SOS: {e}")
            return False

    @staticmethod
    async def send_cancellation_warning_tg(bot, user_id: int, remaining: int) -> bool:
        """Bekor qilish ogohlantirishi"""
        try:
            if remaining == 0:
                msg = "⛔ *24 soat ban!* 3 marta bekor qildingiz."
            else:
                msg = f"⚠️ Yana *{remaining}* marta bekor qilsangiz ban bo'lasiz!"
            await bot.send_message(user_id, msg, parse_mode="Markdown")
            return True
        except Exception as e:
            logger.error(f"Error sending warning: {e}")
            return False

    @staticmethod
    async def send_trip_notification_tg(bot, user_id: int,
                                        driver_name: str, vehicle: str) -> bool:
        """Trip xabari"""
        try:
            await bot.send_message(
                user_id,
                f"🚕 *Haydovchi topildi!*\n\n"
                f"👤 {driver_name}\n"
                f"🚗 {vehicle}\n\n"
                f"Haydovchi siz tomon yo'lda...",
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            logger.error(f"Error sending trip notification: {e}")
            return False


# Alias - eski kod bilan moslik uchun
sms_service = VerificationService()
SMSService = VerificationService
