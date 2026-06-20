"""
AndTaxi Bot - SMS Service (FIXED)
Rate limiting, brute force protection, enhanced security
"""

import random
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
import aiohttp
from config import SMS_API_KEY, SMS_API_URL, SMS_SENDER_NAME
from database import db

logger = logging.getLogger(__name__)

class SMSService:
    """SMS yuborish va tasdiqlash xizmati (FIXED)"""
    
    def __init__(self):
        self.api_key = SMS_API_KEY
        self.api_url = SMS_API_URL
        self.sender = SMS_SENDER_NAME
        self.session = None
    
    async def init(self):
        """Aiohttp sessiya yaratish"""
        self.session = aiohttp.ClientSession()
        logger.info("✅ SMS Service initialized")
    
    async def close(self):
        """Sessiyani yopish"""
        if self.session:
            await self.session.close()
    
    @staticmethod
    def generate_code() -> str:
        """6 raqamli tasdiqlash kodi"""
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    async def send_sms(self, phone: str, message: str) -> Tuple[bool, str]:
        """
        SMS jo'natish + Rate limiting
        FIX #8: SMS soatiga 3 ta cheklamasi
        """
        try:
            phone = self._normalize_phone(phone)
            
            if not self._is_valid_phone(phone):
                logger.warning(f"❌ Invalid phone: {phone}")
                return False, "Noto'g'ri telefon raqami"
            
            # ===== FIX #8: Rate limiting =====
            is_allowed, error = await db.check_sms_rate_limit(phone)
            if not is_allowed:
                logger.warning(f"⚠️ SMS rate limit exceeded for {phone}: {error}")
                return False, error
            
            # API so'rovi
            payload = {
                'api_key': self.api_key,
                'phone': phone,
                'message': message,
                'sender': self.sender
            }
            
            async with self.session.post(
                self.api_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                data = await response.json()
                
                if data.get('success') or response.status == 200:
                    message_id = data.get('message_id', str(datetime.now().timestamp()))
                    logger.info(f"✅ SMS sent to {phone}: {message_id}")
                    return True, message_id
                else:
                    error_msg = data.get('error', 'Unknown error')
                    logger.error(f"❌ SMS error for {phone}: {error_msg}")
                    return False, error_msg
        
        except aiohttp.ClientError as e:
            logger.error(f"❌ Network error sending SMS: {e}")
            return False, "Tarmoq xatosi"
        except Exception as e:
            logger.error(f"❌ Unexpected error sending SMS: {e}")
            return False, str(e)
    
    async def send_verification_code(self, phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Tasdiqlash kodini SMS orqali yuborish
        
        FIX #1: PIN verification support
        """
        code = self.generate_code()
        message = f"AndTaxi: Sizning tasdiqlash kodingiz: {code}. 10 daqiqa davomida haqiqiy."
        
        success, result = await self.send_sms(phone, message)
        
        if success:
            return True, code, None
        else:
            return False, None, result
    
    async def send_welcome_message(self, phone: str, name: str = None) -> bool:
        """Xush kelibsiz xabarni yuborish"""
        greeting = f"Salom{f', {name}' if name else ''}! AndTaxi'ga xush kelibsiz."
        message = f"{greeting} https://t.me/andijon_tashkent_taxi"
        
        success, _ = await self.send_sms(phone, message)
        return success
    
    async def send_trip_notification(self, phone: str, driver_name: str, 
                                    vehicle_info: str, departure_time: str) -> bool:
        """Trip xabari"""
        message = (
            f"AndTaxi: Sizning chiptangiz tayyor!\n"
            f"Haydovchi: {driver_name}\n"
            f"Mashinasi: {vehicle_info}\n"
            f"Ketish vaqti: {departure_time}"
        )
        
        success, _ = await self.send_sms(phone, message)
        return success
    
    async def send_trip_completed(self, phone: str, destination: str, 
                                 rating_link: str = None) -> bool:
        """Trip yakunlandi xabari"""
        message = (
            f"AndTaxi: Trip yakunlandi! 🎉\n"
            f"Manzilingiz: {destination}\n"
        )
        
        if rating_link:
            message += f"Baholi qoldiring: {rating_link}"
        else:
            message += "Haydovchiga ijobiy baho berishni unutmang!"
        
        success, _ = await self.send_sms(phone, message)
        return success
    
    async def send_ban_notification(self, phone: str, ban_type: str, 
                                   ban_until: datetime, reason: str) -> bool:
        """Ban xabari"""
        formatted_time = ban_until.strftime("%d.%m.%Y %H:%M")
        message = (
            f"AndTaxi: Hisobingizga to'xtov berildi ⚠️\n"
            f"Sababi: {reason}\n"
            f"Muddati: {formatted_time} gacha\n"
            f"Maslahat: https://t.me/andijon_tashkent_taxi"
        )
        
        success, _ = await self.send_sms(phone, message)
        return success
    
    async def send_sos_alert(self, admin_phone: str, user_name: str, 
                            user_phone: str, location: str) -> bool:
        """SOS admin alerti"""
        message = (
            f"🚨 EMERGENCY SOS 🚨\n"
            f"Foydalanuvchi: {user_name}\n"
            f"Telefon: {user_phone}\n"
            f"Joylashuvi: {location}"
        )
        
        success, _ = await self.send_sms(admin_phone, message)
        return success
    
    async def send_cancellation_penalty_warning(self, phone: str, remaining_cancels: int) -> bool:
        """
        FIX #7: Cancellation penalty warning
        """
        if remaining_cancels == 0:
            message = "AndTaxi: ⚠️ 24 SOAT BAN! Sababı: 3 marta bekor qilish."
        else:
            message = f"AndTaxi: ⚠️ {remaining_cancels} marta yana bekor qilish mumkin, keyin 24 soat ban!"
        
        success, _ = await self.send_sms(phone, message)
        return success
    
    async def send_trip_cancellation_confirmation(self, phone: str, reason: str) -> bool:
        """
        FIX #7: Trip cancellation confirmation
        """
        message = (
            f"AndTaxi: Trip bekor qilindi ❌\n"
            f"Sababi: {reason}\n"
            f"⏳ 30 daqiqada yangi taksi so'rasang bo'ladi."
        )
        
        success, _ = await self.send_sms(phone, message)
        return success
    
    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Telefon raqamini normallashtirish"""
        phone = ''.join(filter(str.isdigit, phone))
        
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+998' + phone
        
        return phone
    
    @staticmethod
    def _is_valid_phone(phone: str) -> bool:
        """
        Telefon raqami haqiqiy ekanligini tekshirish
        O'zbekiston mobile operatorlari
        """
        if not phone.startswith('+998'):
            return False
        
        digits = phone[4:]
        
        valid_prefixes = [
            '90', '91', '92', '93', '94',  # Beeline, UMS, UCell, Perfectum
            '95', '96', '97', '98', '99',
            '33', '34'  # Landline
        ]
        
        if len(digits) != 9 or digits[:2] not in valid_prefixes:
            return False
        
        return True
    
    async def bulk_send(self, phones: list, message: str) -> dict:
        """Ko'p SMS yuborish"""
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        for phone in phones:
            success, result = await self.send_sms(phone, message)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({'phone': phone, 'error': result})
        
        return results


# Singleton
sms_service = SMSService()
