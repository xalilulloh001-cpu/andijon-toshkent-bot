"""
AndTaxi Bot - Configuration
All environment variables and constants
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ===== TELEGRAM =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))
SUPPORT_CHAT_ID = int(os.getenv("SUPPORT_CHAT_ID", "-1001234567890"))

# ===== DATABASE =====
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/anditaxi"
)

# ===== REDIS =====
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ===== SMS SERVICE =====
SMS_API_URL = os.getenv(
    "SMS_API_URL",
    "https://api.esk.uz/api/messages/sms/send"
)
SMS_API_KEY = os.getenv("SMS_API_KEY", "your_api_key")
SMS_SENDER_NAME = os.getenv("SMS_SENDER_NAME", "AndTaxi")

# ===== WEBSOCKET =====
WEBSOCKET_URL = os.getenv("WEBSOCKET_URL", "ws://localhost:8001")
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", 8001))

# ===== FEATURES =====
FEATURES = {
    'PAYMENT_SYSTEM': os.getenv("FEATURE_PAYMENT_SYSTEM", "false").lower() == "true",
    'SMS_VERIFICATION': os.getenv("FEATURE_SMS_VERIFICATION", "true").lower() == "true",
    'PIN_VERIFICATION': os.getenv("FEATURE_PIN_VERIFICATION", "true").lower() == "true",  # FIX #1
    'REAL_TIME_TRACKING': os.getenv("FEATURE_REAL_TIME_TRACKING", "true").lower() == "true",
    'RATING_MODERATION': os.getenv("FEATURE_RATING_MODERATION", "true").lower() == "true",  # FIX #9
    'OFFLINE_DETECTION': os.getenv("FEATURE_OFFLINE_DETECTION", "true").lower() == "true",  # FIX #5
}

# ===== MATCHING SETTINGS =====
MATCHING_RADIUS_KM = int(os.getenv("MATCHING_RADIUS_KM", "15"))
MAX_PASSENGERS_PER_GROUP = int(os.getenv("MAX_PASSENGERS_PER_GROUP", "4"))
OFFER_TIMEOUT_MINUTES = int(os.getenv("OFFER_TIMEOUT_MINUTES", "5"))

# ===== BAN SETTINGS =====
FALSE_CANCEL_THRESHOLD = int(os.getenv("FALSE_CANCEL_THRESHOLD", "3"))
FALSE_CANCEL_BAN_HOURS = int(os.getenv("FALSE_CANCEL_BAN_HOURS", "24"))
SOS_ABUSE_THRESHOLD = int(os.getenv("SOS_ABUSE_THRESHOLD", "2"))
SOS_ABUSE_BAN_HOURS = int(os.getenv("SOS_ABUSE_BAN_HOURS", "48"))
LOW_RATING_THRESHOLD = float(os.getenv("LOW_RATING_THRESHOLD", "3.0"))
LOW_RATING_MIN_COUNT = int(os.getenv("LOW_RATING_MIN_COUNT", "5"))

# ===== SMS RATE LIMITING =====  # FIX #8
SMS_RATE_LIMIT_PER_HOUR = int(os.getenv("SMS_RATE_LIMIT_PER_HOUR", "3"))
SMS_RATE_LIMIT_WINDOW_MINUTES = int(os.getenv("SMS_RATE_LIMIT_WINDOW_MINUTES", "60"))

# ===== SECURITY =====
PIN_LENGTH = int(os.getenv("PIN_LENGTH", "4"))
PIN_FAILED_ATTEMPTS_LOCK = int(os.getenv("PIN_FAILED_ATTEMPTS_LOCK", "3"))
PIN_LOCK_DURATION_MINUTES = int(os.getenv("PIN_LOCK_DURATION_MINUTES", "15"))

# ===== LOCATION BOUNDS =====  # FIX #10
ANDIJON_LAT = float(os.getenv("ANDIJON_LAT", "40.7281"))
ANDIJON_LNG = float(os.getenv("ANDIJON_LNG", "72.3391"))
ANDIJON_RADIUS_KM = int(os.getenv("ANDIJON_RADIUS_KM", "50"))

TASHKENT_LAT = float(os.getenv("TASHKENT_LAT", "41.2995"))
TASHKENT_LNG = float(os.getenv("TASHKENT_LNG", "69.2401"))
TASHKENT_RADIUS_KM = int(os.getenv("TASHKENT_RADIUS_KM", "50"))

# ===== DRIVER OFFLINE DETECTION =====  # FIX #5
DRIVER_HEARTBEAT_TIMEOUT_SECONDS = int(os.getenv("DRIVER_HEARTBEAT_TIMEOUT_SECONDS", "300"))  # 5 min
OFFLINE_CHECK_INTERVAL_SECONDS = int(os.getenv("OFFLINE_CHECK_INTERVAL_SECONDS", "30"))

# ===== MESSAGES =====
MESSAGES = {
    'start': (
        "🚕 **AndTaxi'ga xush kelibsiz!**\n\n"
        "Andijon ↔ Toshkent orasida qulay taksi xizmati\n\n"
        "Siz haydovchimsiz yoki yo'lovchimiz?"
    ),
    
    'driver_location_request': (
        "📍 **Lokatsiyangizni yuboring**\n\n"
        "Biz sizning joylashuvingizni bilamiz, "
        "yo'lovchilarni topishimiz mumkin bo'ladi."
    ),
    
    'driver_seats_request': (
        "🪑 **O'rindiq soni?**\n\n"
        "1️⃣ - 4️⃣ oralig'ida raqam kiriting"
    ),
    
    'passenger_destination': (
        "🗺️ **Qayerga bormoqchisiz?**\n\n"
        "Toshkent/Andijon shahrining nomi yoki adresini kiriting"
    ),
    
    'offer_from_driver': (
        "🚕 **Haydovchidan taklif!**\n\n"
        "Haydovchi: {driver_name}\n"
        "Mashinasi: {vehicle_info}\n"
        "O'rindiq: {seats} o'rindiq bor\n\n"
        "Qabul qilasizmi? (5 daqiqa)"
    ),
    
    'trip_started': (
        "✅ **Trip boshlanmog'i bilan!**\n\n"
        "📍 Haydovchi manzilga borib chiqdi\n"
        "🗺️ Real-time tracking faol"
    ),
    
    'trip_completed': (
        "🎉 **Trip yakunlandi!**\n\n"
        "Xizmatdan rahul bo'ldingizmi?\n\n"
        "Haydovchiga baho bering (1-5 ⭐)"
    ),
    
    'banned': (
        "🚫 **Hisobingiz bloklashtirilgan**\n\n"
        "Sababi: {reason}\n"
        "Muddati: {ban_until}\n\n"
        "Maslahat: https://t.me/andijon_tashkent_taxi"
    ),
}

# ===== LOG LEVEL =====
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ===== VALIDATION =====
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set!")

if not SMS_API_KEY:
    raise ValueError("SMS_API_KEY not set!")

print("✅ Configuration loaded successfully")
