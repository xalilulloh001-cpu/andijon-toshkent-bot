"""
AndTaxi Bot - Main Bot Handler (COMPLETE FIXES)
Trip cancellation, PIN verification, notification history, admin moderation
"""

import logging
import asyncio
from typing import Optional
from datetime import datetime, timedelta
from hashlib import sha256

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import db
from sms_service import sms_service
from matching import matching_engine, seat_tracker
from ban_system import ban_system, rating_moderation
from config import (
    TELEGRAM_BOT_TOKEN, MESSAGES, FEATURES, ADMIN_IDS,
    OFFER_TIMEOUT_MINUTES
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
main_router = Router()

# ===== FSM STATES =====
class DriverRegistration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_sms_code = State()
    waiting_for_pin = State()  # FIX #1
    waiting_for_location = State()
    waiting_for_seats = State()
    waiting_for_vehicle_info = State()
    active = State()

class PassengerRegistration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_sms_code = State()
    waiting_for_pin = State()  # FIX #1
    waiting_for_location = State()
    waiting_for_destination = State()
    waiting_for_seat_preference = State()
    active = State()

class TripCancellation(StatesGroup):  # FIX #7
    waiting_for_reason = State()

class AdminPanel(StatesGroup):
    choosing_action = State()
    viewing_ratings = State()  # FIX #9

# ===== FIX #1: PIN VERIFICATION AFTER SMS =====
@main_router.message(StateFilter(DriverRegistration.waiting_for_sms_code))
async def driver_sms_code(message: types.Message, state: FSMContext):
    """Haydovchi SMS kodini tasdiqlash"""
    user_id = message.from_user.id
    code = message.text.strip()
    
    data = await state.get_data()
    expected_code = data.get('code')
    
    if code != expected_code:
        await message.answer("❌ Kod noto'g'ri! Iltimos qayta urinib ko'ring.")
        return
    
    success = await db.verify_code(user_id, code)
    
    if success:
        await message.answer("✅ SMS tasdiqlandi!\n📌 Endi 4-raqamli PIN yarating:")
        await state.set_state(DriverRegistration.waiting_for_pin)
    else:
        await message.answer("❌ Tasdiqlash muvaffaqiyatsiz bo'ldi!")

@main_router.message(StateFilter(DriverRegistration.waiting_for_pin))
async def driver_set_pin(message: types.Message, state: FSMContext):
    """
    FIX #1: Driver PIN belgilash
    4 raqamli PIN
    """
    user_id = message.from_user.id
    pin = message.text.strip()
    
    if not (len(pin) == 4 and pin.isdigit()):
        await message.answer("❌ PIN 4 raqamli bo'lishi kerak! (0000-9999)")
        return
    
    success = await db.set_user_pin(user_id, pin)
    
    if success:
        await message.answer("✅ PIN saqlandi!")
        await db.update_user(user_id, role='driver')
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📍 Lokatsiyani yuborish", 
                               request_location=True)]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            MESSAGES['driver_location_request'],
            reply_markup=keyboard
        )
        
        await state.set_state(DriverRegistration.waiting_for_location)

# ... (Yo'lovchi uchun ham xuddi shaydaagi kabi)

# ===== FIX #3: OFFER EXPIRATION CHECK BEFORE ACCEPTANCE =====
@main_router.callback_query(F.data.startswith("accept_offer_"))
async def accept_offer_with_validation(callback: types.CallbackQuery, state: FSMContext):
    """
    FIX #3: Taklif muddati tekshiriladi
    """
    try:
        parts = callback.data.split("_")
        driver_id = int(parts[2])
        passenger_id = callback.from_user.id
        group_id = int(parts[3])
        
        async with db.pool.acquire() as conn:
            offer = await conn.fetchrow("""
            SELECT * FROM driver_offers
            WHERE driver_id = $1 AND passenger_id = $2 AND group_id = $3
            """, driver_id, passenger_id, group_id)
            
            # ===== FIX #3: Check expiration =====
            if not offer:
                await callback.answer("❌ Taklif topilmadi!", show_alert=True)
                return
            
            if offer['offer_expires_at'] < datetime.now():
                await conn.execute("""
                UPDATE driver_offers SET response_status = 'expired'
                WHERE group_id = $1 AND passenger_id = $2
                """, group_id, passenger_id)
                
                await callback.answer(
                    "❌ Taklif muddati tugadi! (5 daqiqa)",
                    show_alert=True
                )
                return
            
            # Proceed with acceptance
            success, seat = await matching_engine.check_and_match_passenger(
                passenger_id, group_id
            )
            
            if success:
                await callback.answer(f"✅ Qabul qilindi! {seat.upper()} o'rindiq", show_alert=True)
            else:
                await callback.answer(f"❌ {seat}", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error accepting offer: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)

# ===== FIX #7: TRIP CANCELLATION =====
@main_router.command("cancel_trip")
async def cmd_cancel_trip(message: types.Message, state: FSMContext):
    """
    FIX #7: Trip bekor qilish
    """
    user_id = message.from_user.id
    
    # Check active trip
    async with db.pool.acquire() as conn:
        trip = await conn.fetchrow("""
        SELECT id FROM trips
        WHERE (driver_id = $1 OR id IN (
            SELECT trip_id FROM trips t
            JOIN group_members gm ON t.group_id = gm.group_id
            WHERE gm.passenger_id = $1
        ))
        AND status = 'active'
        LIMIT 1
        """, user_id)
        
        if not trip:
            await message.answer("❌ Faol trip-ingiz yo'q!")
            return
    
    await message.answer(
        "❌ Trip-ni bekor qilmoqchisiz?\n\n"
        "⚠️ 3 marta bekor qilsa 24 soat ban!\n\n"
        "Sababi nima?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🚗 Mashinada muammo")],
                [KeyboardButton(text="👤 Yo'lovchida muammo")],
                [KeyboardButton(text="🛣️ Yo'lda muammo")],
                [KeyboardButton(text="Bekor qilish")]
            ],
            resize_keyboard=True
        )
    )
    
    await state.set_state(TripCancellation.waiting_for_reason)
    await state.update_data(trip_id=trip['id'])

@main_router.message(StateFilter(TripCancellation.waiting_for_reason))
async def handle_trip_cancellation_reason(message: types.Message, state: FSMContext):
    """
    FIX #7: Trip cancellation sababini qayd qilish
    """
    if message.text == "Bekor qilish":
        await message.answer("❌ Bekor qilindi")
        await state.clear()
        return
    
    data = await state.get_data()
    trip_id = data['trip_id']
    user_id = message.from_user.id
    reason = message.text
    
    user = await db.get_user(user_id)
    cancelled_by = 'driver' if user['role'] == 'driver' else 'passenger'
    
    success, error = await ban_system.handle_trip_cancellation(
        trip_id, user_id, cancelled_by, reason
    )
    
    if success:
        await message.answer(
            f"✅ {error}",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.answer(f"❌ {error}")
    
    await state.clear()

# ===== FIX #9: ADMIN RATING MODERATION =====
@main_router.callback_query(F.data == "admin_moderation")
async def admin_moderation_panel(callback: types.CallbackQuery):
    """
    FIX #9: Admin reyting moderatsiyasi
    """
    user_id = callback.from_user.id
    
    if user_id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return
    
    flagged = await rating_moderation.get_pending_ratings()
    
    if not flagged:
        await callback.message.answer("✅ Tekshirilishi kerak bo'lgan reyting yo'q!")
        await callback.answer()
        return
    
    text = "🚩 **Tekshirilishi kerak bo'lgan reyting-lar:**\n\n"
    
    for flag in flagged[:10]:
        text += (
            f"ID: {flag['rating_id']}\n"
            f"👤 Reyting bermagan: {flag['rater_name']}\n"
            f"⭐ Yulduz: {flag['stars']}/5\n"
            f"💬 Sharh: {flag['comment'][:50]}...\n"
            f"🚩 Sabab: {flag['reason']}\n"
            f"─────────────────────\n\n"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_rating_{flagged[0]['id']}"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"delete_rating_{flagged[0]['id']}")
        ]
    ])
    
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()

@main_router.callback_query(F.data.startswith("approve_rating_"))
async def approve_rating_callback(callback: types.CallbackQuery):
    """Reyting-ni tasdiqlash"""
    admin_id = callback.from_user.id
    flag_id = int(callback.data.split("_")[-1])
    
    await rating_moderation.approve_rating(flag_id, admin_id)
    
    await callback.message.edit_text("✅ Reyting tasdiqlandi!")
    await callback.answer()

@main_router.callback_query(F.data.startswith("delete_rating_"))
async def delete_rating_callback(callback: types.CallbackQuery):
    """Reyting-ni o'chirish"""
    admin_id = callback.from_user.id
    flag_id = int(callback.data.split("_")[-1])
    
    await rating_moderation.delete_rating(flag_id, admin_id)
    
    await callback.message.edit_text("❌ Reyting o'chirildi!")
    await callback.answer()

# ===== FIX #13: NOTIFICATION HISTORY =====
@main_router.command("notifications")
async def cmd_view_notifications(message: types.Message):
    """
    FIX #13: Foydalanuvchining bildirishnomalar tarixini ko'rish
    """
    user_id = message.from_user.id
    
    notifications = await db.get_user_notifications(user_id, limit=20)
    
    if not notifications:
        await message.answer("📭 Bildirishnomangiz yo'q!")
        return
    
    text = "📬 **Bildirishnomalar tarixik:**\n\n"
    
    for notif in notifications:
        read_mark = "✅" if notif['is_read'] else "🔔"
        created = notif['created_at'].strftime("%H:%M")
        
        text += (
            f"{read_mark} [{created}] {notif['title']}\n"
            f"   {notif['message'][:80]}...\n\n"
        )
    
    await message.answer(text)
    
    # Mark all as read
    for notif in notifications:
        await db.mark_notification_read(notif['id'])

# ===== RATING FLAGGING =====
@main_router.message(F.text == "🚩 Flag rating")
async def flag_rating_command(message: types.Message):
    """Shubhali reyting-larni flag qilish (admin)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Faqat admin!")
        return
    
    await message.answer(
        "Reyting ID-sini va sababi kiriting:\n"
        "Masalan: 123 Yolg'on sharh"
    )

# ... (boshqa handlers o'zgarmagan)

# ===== DISPATCHER =====
dp.include_router(main_router)

async def main():
    """Bot ishga tushirish"""
    await db.init()
    await sms_service.init()
    
    logger.info("🚀 AndTaxi Bot started (FULLY FIXED)")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await sms_service.close()
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
