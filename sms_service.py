"""
AndTaxi Bot - Verification Service
1. Telegram contact sharing (phone number)
2. Telegram OTP code (6 digit)
100% BEPUL - SMS shart emas!
"""

import random
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class VerificationService:

    @staticmethod
    def generate_code() -> str:
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])

    @staticmethod
    def normalize_phone(phone: str) -> Optional[str]:
        """Telefon raqamini normallashtirish"""
        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('998') and len(digits) == 12:
            return '+' + digits
        if len(digits) == 9:
            return '+998' + digits
        if digits.startswith('8') and len(digits) == 11:
            return '+998' + digits[1:]
        if digits.startswith('0') and len(digits) == 10:
            return '+998' + digits[1:]
        return None

    @staticmethod
    async def send_otp_via_telegram(bot, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        QADAM 2: Telegram orqali OTP kod yuborish
        """
        try:
            code = VerificationService.generate_code()

            await bot.send_message(
                user_id,
                f"🔐 *Tasdiqlash kodi:*\n\n"
                f"```{code}```\n\n"
                f"⏰ 10 daqiqa ichida kiriting\n"
                f"❗ Bu kodni hech kimga bermang!",
                parse_mode="Markdown"
            )

            logger.info(f"✅ OTP sent to user {user_id}")
            return True, code

        except Exception as e:
            logger.error(f"OTP send error: {e}")
            return False, None

    @staticmethod
    async def send_ban_notification(bot, user_id: int,
                                    reason: str, ban_until: datetime) -> bool:
        try:
            await bot.send_message(
                user_id,
                f"🚫 *Hisobingiz bloklandi!*\n\n"
                f"📌 Sababi: {reason}\n"
                f"📅 Muddati: `{ban_until.strftime('%d.%m.%Y %H:%M')}` gacha\n\n"
                f"❓ Savol: @andtaxi_support",
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            logger.error(f"Ban notify error: {e}")
            return False

    @staticmethod
    async def send_sos_alert(bot, admin_ids: list,
                             user_name: str, user_id: int,
                             lat: float, lng: float) -> bool:
        try:
            url = f"https://maps.google.com/?q={lat},{lng}"
            text = (
                f"🚨 *SOS EMERGENCY!*\n\n"
                f"👤 {user_name} (ID: `{user_id}`)\n"
                f"📍 [Xarita]({url})\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            for admin_id in admin_ids:
                try:
                    await bot.send_message(admin_id, text, parse_mode="Markdown")
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.error(f"SOS alert error: {e}")
            return False

    @staticmethod
    async def send_cancellation_warning(bot, user_id: int, remaining: int) -> bool:
        try:
            if remaining == 0:
                msg = "⛔ *24 soat ban!*\n3 marta bekor qildingiz."
            else:
                msg = f"⚠️ Yana *{remaining}* marta bekor qilsangiz ban bo'lasiz!"
            await bot.send_message(user_id, msg, parse_mode="Markdown")
            return True
        except Exception as e:
            logger.error(f"Warning send error: {e}")
            return False

    @staticmethod
    async def send_trip_notification(bot, user_id: int,
                                     driver_name: str, vehicle: str) -> bool:
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
            logger.error(f"Trip notify error: {e}")
            return False


sms_service = VerificationService()
