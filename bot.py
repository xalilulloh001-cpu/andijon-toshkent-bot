"""
AndTaxi Bot - Main Handler
FLOW:
  1. /start → rol tanlash
  2. "Raqamni ulash" tugmasi → Telegram contact share (real telefon raqam)
  3. Bot Telegram orqali 6 raqamli OTP yuboradi
  4. Foydalanuvchi OTP kiritadi → tasdiqlandi ✅
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from hashlib import sha256

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

from sms_service import VerificationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8961922618:AAFENS26vL5bVO1mBGrHDWjQRdOlnLW_jtg")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ===================== FSM STATES =====================

class DriverStates(StatesGroup):
    choosing_role     = State()
    sharing_contact   = State()   # QADAM 1: Telegram contact
    entering_otp      = State()   # QADAM 2: OTP tasdiqlash
    entering_location = State()
    entering_seats    = State()
    entering_vehicle  = State()
    active            = State()

class PassengerStates(StatesGroup):
    choosing_role     = State()
    sharing_contact   = State()   # QADAM 1: Telegram contact
    entering_otp      = State()   # QADAM 2: OTP tasdiqlash
    entering_location = State()
    entering_seat_pref = State()
    active            = State()

class TripCancel(StatesGroup):
    entering_reason = State()

# ===================== KEYBOARDS =====================

def kb_role():
    """Rol tanlash klaviaturasi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Haydovchi")],
            [KeyboardButton(text="👤 Yo'lovchi")],
        ],
        resize_keyboard=True
    )

def kb_share_contact():
    """
    QADAM 1: Telegram contact sharing tugmasi
    Foydalanuvchi bosadi → Telegram o'zi real raqamni beradi
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="📱 Raqamni ulash",
                request_contact=True        # ← Telegram'ning o'zi raqamni beradi
            )],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def kb_seat_pref():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬆️ Old o'rindiq (qimmat)")],
            [KeyboardButton(text="⬇️ Orqa o'rindiq (arzon)")],
        ],
        resize_keyboard=True
    )

def kb_seats():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2")],
            [KeyboardButton(text="3"), KeyboardButton(text="4")],
        ],
        resize_keyboard=True
    )

def kb_main_driver():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Navbatga kirish"),
             KeyboardButton(text="🔴 Navbatdan chiqish")],
            [KeyboardButton(text="📊 Mening hisobim"),
             KeyboardButton(text="🆘 SOS")],
        ],
        resize_keyboard=True
    )

def kb_main_passenger():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚕 Taksi chaqirish")],
            [KeyboardButton(text="📊 Mening hisobim"),
             KeyboardButton(text="🆘 SOS")],
            [KeyboardButton(text="❌ Trip bekor qilish")],
        ],
        resize_keyboard=True
    )

def kb_location():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyamni yuborish",
                            request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ===================== /start =====================

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    name = message.from_user.first_name or "Do'st"

    await message.answer(
        f"🚕 *AndTaxi'ga xush kelibsiz, {name}!*\n\n"
        f"Andijon ↔ Toshkent yo'nalishi\n\n"
        f"Siz kimсiz?",
        reply_markup=kb_role(),
        parse_mode="Markdown"
    )
    await state.set_state(DriverStates.choosing_role)


# ===================== ROL TANLASH =====================

@router.message(F.text == "🚗 Haydovchi",
                StateFilter(DriverStates.choosing_role))
async def choose_driver(message: types.Message, state: FSMContext):
    await state.update_data(role="driver")

    await message.answer(
        "🚗 *Haydovchi sifatida ro'yxatdan o'tish*\n\n"
        "📱 *1-qadam:* Telefon raqamingizni ulang\n"
        "_(Telegram o'zi real raqamingizni beradi)_",
        reply_markup=kb_share_contact(),
        parse_mode="Markdown"
    )
    await state.set_state(DriverStates.sharing_contact)


@router.message(F.text == "👤 Yo'lovchi",
                StateFilter(DriverStates.choosing_role))
async def choose_passenger(message: types.Message, state: FSMContext):
    await state.update_data(role="passenger")

    await message.answer(
        "👤 *Yo'lovchi sifatida ro'yxatdan o'tish*\n\n"
        "📱 *1-qadam:* Telefon raqamingizni ulang\n"
        "_(Telegram o'zi real raqamingizni beradi)_",
        reply_markup=kb_share_contact(),
        parse_mode="Markdown"
    )
    await state.set_state(PassengerStates.sharing_contact)


# ===================== QADAM 1: CONTACT SHARE =====================

async def handle_contact_shared(message: types.Message, state: FSMContext, role: str):
    """
    Foydalanuvchi "Raqamni ulash" bosdi → Telegram real raqamni berdi
    Endi OTP yuboramiz
    """
    contact = message.contact
    phone = VerificationService.normalize_phone(contact.phone_number)

    if not phone:
        await message.answer(
            "❌ Telefon raqam noto'g'ri!\n"
            "Iltimos qayta urinib ko'ring.",
            reply_markup=kb_share_contact()
        )
        return

    # Raqamni saqlab qo'yamiz
    await state.update_data(phone=phone)

    # ===== QADAM 2: OTP yuborish =====
    success, code = await VerificationService.send_otp_via_telegram(
        bot, message.from_user.id
    )

    if not success:
        await message.answer("❌ Kod yuborishda xato. Qayta /start bosing.")
        return

    # Kodni va vaqtni saqlaymiz
    await state.update_data(
        otp_code=code,
        otp_sent_at=datetime.now().isoformat()
    )

    await message.answer(
        f"✅ Raqam ulandi: *{phone}*\n\n"
        f"📨 *2-qadam:* Telegram-ga kod yubordik\n"
        f"Yuqoridagi 6 raqamli kodni kiriting:\n\n"
        f"⏰ 10 daqiqa vaqtingiz bor",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    # Keyingi holatga o'tamiz
    if role == "driver":
        await state.set_state(DriverStates.entering_otp)
    else:
        await state.set_state(PassengerStates.entering_otp)


@router.message(F.contact, StateFilter(DriverStates.sharing_contact))
async def driver_contact_shared(message: types.Message, state: FSMContext):
    await handle_contact_shared(message, state, "driver")


@router.message(F.contact, StateFilter(PassengerStates.sharing_contact))
async def passenger_contact_shared(message: types.Message, state: FSMContext):
    await handle_contact_shared(message, state, "passenger")


# Agar contact o'rniga matn yozsa
@router.message(StateFilter(DriverStates.sharing_contact,
                             PassengerStates.sharing_contact))
async def contact_not_shared(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer(
        "⚠️ Iltimos *\"📱 Raqamni ulash\"* tugmasini bosing!\n"
        "Matn yozish orqali raqam qabul qilinmaydi.",
        reply_markup=kb_share_contact(),
        parse_mode="Markdown"
    )


# ===================== QADAM 2: OTP TASDIQLASH =====================

async def handle_otp_entry(message: types.Message, state: FSMContext, role: str):
    """
    Foydalanuvchi OTP kodni kiritdi → tekshiramiz
    """
    entered_code = message.text.strip()
    data = await state.get_data()

    saved_code = data.get("otp_code")
    sent_at_str = data.get("otp_sent_at")

    # Vaqt tekshiruvi (10 daqiqa)
    if sent_at_str:
        sent_at = datetime.fromisoformat(sent_at_str)
        if datetime.now() - sent_at > timedelta(minutes=10):
            await message.answer(
                "⏰ Kod muddati tugadi!\n"
                "Qayta /start bosing.",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return

    # Kod tekshiruvi
    if entered_code != saved_code:
        await message.answer(
            "❌ Kod noto'g'ri!\n"
            "Qayta urinib ko'ring (kod Telegram-da yuborilgan)."
        )
        return

    # ✅ TASDIQLANDI
    phone = data.get("phone", "")

    await message.answer(
        f"✅ *Tasdiqlandi!*\n\n"
        f"📱 Raqam: {phone}\n"
        f"🔐 Hisob xavfsizlashtirildi",
        parse_mode="Markdown"
    )

    # Keyingi qadam
    if role == "driver":
        await message.answer(
            "📍 *3-qadam:* Joylashuvingizni yuboring",
            reply_markup=kb_location(),
            parse_mode="Markdown"
        )
        await state.set_state(DriverStates.entering_location)
    else:
        await message.answer(
            "📍 *3-qadam:* Joylashuvingizni yuboring",
            reply_markup=kb_location(),
            parse_mode="Markdown"
        )
        await state.set_state(PassengerStates.entering_location)


@router.message(StateFilter(DriverStates.entering_otp))
async def driver_otp_entry(message: types.Message, state: FSMContext):
    await handle_otp_entry(message, state, "driver")


@router.message(StateFilter(PassengerStates.entering_otp))
async def passenger_otp_entry(message: types.Message, state: FSMContext):
    await handle_otp_entry(message, state, "passenger")


# ===================== LOKATSIYA =====================

@router.message(F.location, StateFilter(DriverStates.entering_location))
async def driver_location(message: types.Message, state: FSMContext):
    lat = message.location.latitude
    lng = message.location.longitude
    await state.update_data(lat=lat, lng=lng)

    await message.answer(
        f"✅ Joylashuv saqlandi!\n\n"
        f"🪑 *4-qadam:* Necha o'rindiq bor?",
        reply_markup=kb_seats(),
        parse_mode="Markdown"
    )
    await state.set_state(DriverStates.entering_seats)


@router.message(F.location, StateFilter(PassengerStates.entering_location))
async def passenger_location(message: types.Message, state: FSMContext):
    lat = message.location.latitude
    lng = message.location.longitude
    await state.update_data(lat=lat, lng=lng)

    await message.answer(
        "✅ Joylashuv saqlandi!\n\n"
        "🪑 *Qaysi o'rindiqni xohlaysiz?*",
        reply_markup=kb_seat_pref(),
        parse_mode="Markdown"
    )
    await state.set_state(PassengerStates.entering_seat_pref)


@router.message(StateFilter(DriverStates.entering_location,
                             PassengerStates.entering_location))
async def location_not_sent(message: types.Message):
    if message.text == "❌ Bekor qilish":
        return
    await message.answer(
        "⚠️ Iltimos *\"📍 Lokatsiyamni yuborish\"* tugmasini bosing!",
        reply_markup=kb_location(),
        parse_mode="Markdown"
    )


# ===================== HAYDOVCHI O'RINDIQ =====================

@router.message(F.text.in_(["1","2","3","4"]),
                StateFilter(DriverStates.entering_seats))
async def driver_seats(message: types.Message, state: FSMContext):
    seats = int(message.text)
    await state.update_data(seats=seats)

    await message.answer(
        f"✅ {seats} ta o'rindiq!\n\n"
        "🚗 *5-qadam:* Mashina ma'lumotlari\n"
        "_(Masalan: Cobalt 01B123AB)_",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(DriverStates.entering_vehicle)


@router.message(StateFilter(DriverStates.entering_vehicle))
async def driver_vehicle(message: types.Message, state: FSMContext):
    vehicle = message.text.strip()
    if len(vehicle) < 5:
        await message.answer("❌ Mashina ma'lumotlarini to'liqroq kiriting!")
        return

    data = await state.get_data()
    await state.update_data(vehicle=vehicle)

    await message.answer(
        f"🎉 *Ro'yxatdan o'tdingiz!*\n\n"
        f"📱 Raqam: {data.get('phone')}\n"
        f"📍 Joylashuv: saqlandi\n"
        f"🪑 O'rindiq: {data.get('seats')} ta\n"
        f"🚗 Mashina: {vehicle}\n\n"
        f"Navbatga kirish uchun tugmani bosing 👇",
        reply_markup=kb_main_driver(),
        parse_mode="Markdown"
    )
    await state.set_state(DriverStates.active)


# ===================== YO'LOVCHI O'RINDIQ =====================

@router.message(F.text.in_(["⬆️ Old o'rindiq (qimmat)",
                              "⬇️ Orqa o'rindiq (arzon)"]),
                StateFilter(PassengerStates.entering_seat_pref))
async def passenger_seat_pref(message: types.Message, state: FSMContext):
    is_front = "Old" in message.text
    await state.update_data(seat_pref="front" if is_front else "back")

    data = await state.get_data()

    seat_emoji = "⬆️ Old" if is_front else "⬇️ Orqa"
    price_note = "_(Biroz qimmatroq)_" if is_front else "_(Arzonroq)_"

    await message.answer(
        f"🎉 *Ro'yxatdan o'tdingiz!*\n\n"
        f"📱 Raqam: {data.get('phone')}\n"
        f"📍 Joylashuv: saqlandi\n"
        f"🪑 O'rindiq: {seat_emoji} {price_note}\n\n"
        f"Taksi chaqirish uchun tugmani bosing 👇",
        reply_markup=kb_main_passenger(),
        parse_mode="Markdown"
    )
    await state.set_state(PassengerStates.active)


# ===================== ASOSIY TUGMALAR =====================

@router.message(F.text == "🟢 Navbatga kirish",
                StateFilter(DriverStates.active))
async def driver_join_queue(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        f"✅ *Navbatga kirdingiz!*\n\n"
        f"🚗 {data.get('vehicle', '-')}\n"
        f"🪑 {data.get('seats', 0)} ta o'rindiq\n\n"
        f"Yo'lovchilar topilganda xabar olasiz...",
        parse_mode="Markdown"
    )


@router.message(F.text == "🔴 Navbatdan chiqish",
                StateFilter(DriverStates.active))
async def driver_leave_queue(message: types.Message, state: FSMContext):
    await message.answer("🔴 Navbatdan chiqdingiz.")


@router.message(F.text == "🚕 Taksi chaqirish",
                StateFilter(PassengerStates.active))
async def passenger_call_taxi(message: types.Message, state: FSMContext):
    await message.answer(
        "🔍 *Haydovchi qidiryapmiz...*\n\n"
        "Tez orada haydovchi topiladi ⏳",
        parse_mode="Markdown"
    )


@router.message(F.text == "📊 Mening hisobim")
async def my_profile(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone", "Noma'lum")
    role = data.get("role", "Noma'lum")

    role_text = "🚗 Haydovchi" if role == "driver" else "👤 Yo'lovchi"

    await message.answer(
        f"👤 *Mening hisobim*\n\n"
        f"📱 Raqam: {phone}\n"
        f"🏷️ Rol: {role_text}\n"
        f"⭐ Reyting: 5.0\n"
        f"🚕 Triplar: 0",
        parse_mode="Markdown"
    )


@router.message(F.text == "🆘 SOS")
async def sos_handler(message: types.Message):
    await message.answer(
        "🚨 *SOS - Favqulodda yordam*\n\n"
        "Joylashuvingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📍 Joylashuvimni yubor",
                                request_location=True)],
                [KeyboardButton(text="❌ Bekor")]
            ],
            resize_keyboard=True
        ),
        parse_mode="Markdown"
    )


@router.message(F.location)
async def sos_location_received(message: types.Message):
    lat = message.location.latitude
    lng = message.location.longitude
    user = message.from_user

    # Admin-larga xabar
    await VerificationService.send_sos_alert(
        bot, ADMIN_IDS,
        user.full_name, user.id,
        lat, lng
    )

    await message.answer(
        "✅ *SOS xabari adminga yuborildi!*\n"
        "Tez orada aloqa qilinadi.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )


@router.message(F.text == "❌ Trip bekor qilish")
async def cancel_trip_start(message: types.Message, state: FSMContext):
    await message.answer(
        "❌ Trip-ni bekor qilish sababi?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🚗 Haydovchida muammo")],
                [KeyboardButton(text="👤 Shaxsiy sabab")],
                [KeyboardButton(text="🔙 Orqaga")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(TripCancel.entering_reason)


@router.message(StateFilter(TripCancel.entering_reason))
async def cancel_trip_reason(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(PassengerStates.active)
        await message.answer("🔙 Orqaga", reply_markup=kb_main_passenger())
        return

    await message.answer(
        "✅ Trip bekor qilindi.\n"
        "⚠️ Yana 2 marta bekor qilsangiz ban bo'lasiz!",
        reply_markup=kb_main_passenger()
    )
    await state.set_state(PassengerStates.active)


# ===================== ADMIN =====================

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Ruxsat yo'q!")
        return

    await message.answer(
        "👨‍💼 *Admin panel*\n\n"
        "/stats — Statistika\n"
        "/ban {user_id} — Foydalanuvchini bloklash\n"
        "/unban {user_id} — Blokdan chiqarish",
        parse_mode="Markdown"
    )


@router.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        "📊 *Statistika*\n\n"
        "🚗 Faol haydovchilar: 0\n"
        "👤 Navbatdagi yo'lovchilar: 0\n"
        "🚕 Bugungi triplar: 0",
        parse_mode="Markdown"
    )


# ===================== ISHGA TUSHIRISH =====================

async def main():
    dp.include_router(router)

    logger.info("🚀 AndTaxi Bot ishga tushmoqda...")
    logger.info(f"👨‍💼 Admin IDs: {ADMIN_IDS}")

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())


# =========== WEBAPP HANDLER ===========
from aiogram.types import WebAppInfo

@router.message(Command("app"))
async def open_webapp(message: types.Message):
    """Web ko'rinishda ochish"""
    webapp_url = os.getenv("WEBAPP_URL", "https://xalilulloh001-cpu.github.io/andijon-toshkent-bot/webapp.html")
    
    await message.answer(
        "🚕 *AndTaxi Web App*\n\nQuyidagi tugmani bosing:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[
                KeyboardButton(
                    text="🚕 AndTaxi ochish",
                    web_app=WebAppInfo(url=webapp_url)
                )
            ]],
            resize_keyboard=True
        ),
        parse_mode="Markdown"
    )

@router.message(F.web_app_data)
async def webapp_data_received(message: types.Message):
    """WebApp-dan kelgan ma'lumotlarni qayta ishlash"""
    import json
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get('action', '')

        if action == 'send_otp':
            phone = data.get('phone')
            success, code = await VerificationService.send_otp_via_telegram(bot, message.from_user.id)
            if success:
                await message.answer(f"📨 Tasdiqlash kodi yuborildi: `{code}`", parse_mode="Markdown")

        elif action == 'register':
            role = '🚗 Haydovchi' if data.get('role') == 'driver' else '👤 Yo\'lovchi'
            await message.answer(
                f"✅ *Ro'yxatdan o'tdingiz!*\n\n"
                f"Rol: {role}\n"
                f"Telefon: {data.get('phone', '—')}",
                parse_mode="Markdown"
            )

        elif action == 'join_queue':
            await message.answer("🟢 Navbatga kirdingiz! Yo'lovchilar kutilmoqda...")

        elif action == 'leave_queue':
            await message.answer("🔴 Navbatdan chiqdingiz.")

        elif action == 'search_taxi':
            await message.answer("🔍 Haydovchi qidiryapmiz...")

        elif action == 'accept_driver':
            await message.answer("✅ Haydovchi qabul qilindi! U siz tomon kelmoqda.")

        elif action == 'sos':
            lat = data.get('lat')
            lng = data.get('lng')
            await VerificationService.send_sos_alert(
                bot, ADMIN_IDS,
                message.from_user.full_name,
                message.from_user.id,
                lat, lng
            )
            await message.answer("🚨 SOS xabari adminga yuborildi!")

    except Exception as e:
        logger.error(f"WebApp data error: {e}")
