"""
AndTaxi Bot - SMS Service (ESKIZ.UZ)
O'zbekiston uchun eng mashhur SMS provider
"""

import logging
import aiohttp
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SMSService:
    """Eskiz.uz SMS xizmati"""

    def __init__(self):
        import os
        self.email = os.getenv("ESKIZ_EMAIL", "")
        self.password = os.getenv("ESKIZ_PASSWORD", "")
        self.token = os.getenv("SMS_API_KEY", "")  # yoki manual token
        self.base_url = "https://notify.eskiz.uz/api"
        self.session = None

    async def init(self):
        self.session = aiohttp.ClientSession()
        if not self.token and self.email and self.password:
            await self.get_token()
        logger.info("✅ SMS Service (Eskiz.uz) initialized")

    async def close(self):
        if self.session:
            await self.session.close()

    async def get_token(self) -> bool:
        """Email/parol bilan token olish"""
        try:
            async with self.session.post(
                f"{self.base_url}/auth/login",
                data={"email": self.email, "password": self.password}
            ) as resp:
                data = await resp.json()
                if data.get("data", {}).get("token"):
                    self.token = data["data"]["token"]
                    logger.info("✅ Eskiz token received")
                    return True
                logger.error(f"Token error: {data}")
                return False
        except Exception as e:
            logger.error(f"Token fetch error: {e}")
            return False

    async def send_sms(self, phone: str, message: str) -> Tuple[bool, str]:
        """SMS yuborish"""
        try:
            phone = self._normalize_phone(phone)
            if not phone:
                return False, "Noto'g'ri raqam"

            headers = {"Authorization": f"Bearer {self.token}"}

            async with self.session.post(
                f"{self.base_url}/message/sms/send",
                headers=headers,
                data={
                    "mobile_phone": phone,
                    "message": message,
                    "from": "4546",
                    "callback_url": ""
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if data.get("status") == "waiting" or data.get("id"):
                    logger.info(f"✅ SMS sent to {phone}")
                    return True, str(data.get("id", "ok"))
                else:
                    logger.error(f"SMS error: {data}")
                    return False, str(data.get("message", "Xato"))

        except Exception as e:
            logger.error(f"SMS send error: {e}")
            return False, str(e)

    async def send_verification_code(self, phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Tasdiqlash kodi yuborish"""
        import random
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        message = f"AndTaxi tasdiqlash kodi: {code}\n10 daqiqa ichida kiriting."
        success, result = await self.send_sms(phone, message)
        if success:
            return True, code, None
        return False, None, result

    async def send_welcome(self, phone: str, name: str = "") -> bool:
        msg = f"Salom{f', {name}' if name else ''}! AndTaxi'ga xush kelibsiz 🚕"
        ok, _ = await self.send_sms(phone, msg)
        return ok

    async def send_ban_notification(self, phone: str, reason: str,
                                    ban_until: datetime, desc: str) -> bool:
        msg = (f"AndTaxi: Hisobingiz bloklandi ⚠️\n"
               f"Sababi: {desc}\n"
               f"Muddati: {ban_until.strftime('%d.%m.%Y %H:%M')}")
        ok, _ = await self.send_sms(phone, msg)
        return ok

    async def send_sos_alert(self, admin_phone: str, user_name: str,
                             user_phone: str, location: str) -> bool:
        msg = (f"🚨 SOS! {user_name} ({user_phone})\n"
               f"Joylashuv: {location}")
        ok, _ = await self.send_sms(admin_phone, msg)
        return ok

    async def send_cancellation_penalty_warning(self, phone: str, remaining: int) -> bool:
        if remaining == 0:
            msg = "AndTaxi: 24 soat ban! 3 marta bekor qildingiz."
        else:
            msg = f"AndTaxi: Yana {remaining} marta bekor qilsangiz ban bo'lasiz!"
        ok, _ = await self.send_sms(phone, msg)
        return ok

    @staticmethod
    def _normalize_phone(phone: str) -> Optional[str]:
        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('998') and len(digits) == 12:
            return digits
        if len(digits) == 9:
            return '998' + digits
        if digits.startswith('8') and len(digits) == 11:
            return '998' + digits[1:]
        return None


sms_service = SMSService()
