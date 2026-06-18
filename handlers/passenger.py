from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import pytz

import database as db
from matching import find_best_matches
from keyboards import (
    direction_keyboard, seat_position_keyboard, seat_count_keyboard,
    time_keyboard, hours_keyboard, location_keyboard, passenger_menu_keyboard,
)
from texts import t

router = Router()

TZ = pytz.timezone("Asia/Tashkent")

DIRECTION_LABELS = {
    'uz': {
        'andijon_toshkent': 'Andijon → Toshkent',
        'toshkent_andijon': 'Toshkent → Andijon',
    },
    'ru': {
        'andijon_toshkent': 'Андижан → Ташкент',
        'toshkent_andijon': 'Ташкент → Андижан',
    }
}
SEAT_POS_LABELS = {
    'uz': {'front': '🪑 Oldi', 'back': '💺 Orqa'},
    'ru': {'front': '🪑 Перед', 'back': '💺 Зад'},
}
STATUS_LABELS = {
    'uz': {'waiting': '⏳ Kutilmoqda', 'matched': '✅ Haydovchi topildi', 'completed': '🏁 Yakunlandi', 'cancelled': '❌ Bekor qilindi'},
    'ru': {'waiting': '⏳ Ожидание', 'matched': '✅ Водитель найден', 'completed': '🏁 Завершено', 'cancelled': '❌ Отменено'},
}


class PassengerStates(StatesGroup):
    choosing_seat_pos = State()
    choosing_seat_count = State()
    choosing_time = State()
    choosing_hour_from = State()
    choosing_hour_to = State()
    sending_location = State()


async def get_lang(user_id):
    user = await db.get_user(user_id)
    return user['lang'] if user else 'uz'


def now_tashkent():
    return datetime.now(TZ)


@router.message(F.text.in_([
    "🚀 Andijon → Toshkent", "🔙 Toshkent → Andijon",
    "🚀 Андижан → Ташкент", "🔙 Ташкент → Андижан"
]))
async def start_passenger_request(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Iltimos avval /start dan boshlang.")
        return
    lang = user['lang']

    direction = 'andijon_toshkent' if ("Andijon" in message.text or "Андижан" in message.text) else 'toshkent_andijon'
    await state.update_data(direction=direction)
    await state.set_state(PassengerStates.choosing_seat_pos)
    await message.answer(t(lang, 'choose_seat_pos'), reply_markup=seat_position_keyboard(lang))


@router.callback_query(F.data.in_(["seat_front", "seat_back"]))
async def choose_seat_pos(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    seat_pos = 'front' if callback.data == 'seat_front' else 'back'
    await state.update_data(seat_pos=seat_pos)
    await state.set_state(PassengerStates.choosing_seat_count)
    await callback.message.edit_text(t(lang, 'choose_seat_count'), reply_markup=seat_count_keyboard())


@router.callback_query(F.data.startswith("count_"))
async def choose_seat_count(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    count = int(callback.data.split("_")[1])
    await state.update_data(seat_count=count)
    await state.set_state(PassengerStates.choosing_time)
    await callback.message.edit_text(t(lang, 'choose_time'), reply_markup=time_keyboard(lang))


@router.callback_query(F.data.in_(["time_now", "time_today", "time_tomorrow"]))
async def choose_time_type(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    now = now_tashkent()

    if callback.data == "time_now":
        time_from = now
        time_to = now + timedelta(hours=2)
        await state.update_data(time_from=time_from.isoformat(), time_to=time_to.isoformat())
        await state.set_state(PassengerStates.sending_location)
        await callback.message.answer(t(lang, 'location_request'), reply_markup=location_keyboard(lang))
        await callback.message.delete()
    elif callback.data == "time_today":
        await state.update_data(base_date=now.date().isoformat())
        await state.set_state(PassengerStates.choosing_hour_from)
        await callback.message.edit_text(t(lang, 'choose_hour_from'), reply_markup=hours_keyboard("pfrom"))
    else:
        tomorrow = (now + timedelta(days=1)).date()
        await state.update_data(base_date=tomorrow.isoformat())
        await state.set_state(PassengerStates.choosing_hour_from)
        await callback.message.edit_text(t(lang, 'choose_hour_from'), reply_markup=hours_keyboard("pfrom"))


@router.callback_query(F.data.startswith("pfrom_"))
async def choose_hour_from(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    hour = int(callback.data.split("_")[1])
    await state.update_data(hour_from=hour)
    await state.set_state(PassengerStates.choosing_hour_to)
    await callback.message.edit_text(t(lang, 'choose_hour_to'), reply_markup=hours_keyboard("pto"))


@router.callback_query(F.data.startswith("pto_"))
async def choose_hour_to(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    hour_to = int(callback.data.split("_")[1])
    data = await state.get_data()
    hour_from = data.get('hour_from', 0)

    if hour_to <= hour_from:
        await callback.answer("❌ 'Gacha' vaqti 'Dan' vaqtidan katta bo'lishi kerak!", show_alert=True)
        return

    from datetime import date
    bd = date.fromisoformat(data['base_date'])
    time_from = TZ.localize(datetime(bd.year, bd.month, bd.day, hour_from))
    time_to = TZ.localize(datetime(bd.year, bd.month, bd.day, hour_to))

    await state.update_data(time_from=time_from.isoformat(), time_to=time_to.isoformat())
    await state.set_state(PassengerStates.sending_location)
    await callback.message.answer(t(lang, 'location_request'), reply_markup=location_keyboard(lang))
    await callback.message.delete()


@router.message(PassengerStates.sending_location, F.location)
async def receive_location(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    data = await state.get_data()

    # Faol so'rov borligini tekshirish
    existing = await db.get_active_passenger_request(message.from_user.id)
    if existing:
        await state.clear()
        await message.answer(
            "⚠️ Sizda allaqachon faol so'rov bor!\n"
            "Avval uni bekor qiling, keyin yangi so'rov yuboring.",
            reply_markup=passenger_menu_keyboard(lang)
        )
        return

    time_from = datetime.fromisoformat(data['time_from'])
    time_to = datetime.fromisoformat(data['time_to'])

    await db.create_passenger_request(
        user_id=message.from_user.id,
        direction=data['direction'],
        seat_position=data['seat_pos'],
        seat_count=data['seat_count'],
        time_from=time_from,
        time_to=time_to,
        lat=message.location.latitude,
        lng=message.location.longitude
    )
    await state.clear()
    await message.answer(t(lang, 'request_sent'), reply_markup=passenger_menu_keyboard(lang))


# Lokatsiya o'tkazib yuborish
@router.message(PassengerStates.sending_location, F.text)
async def skip_location(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    skip_texts = [t('uz', 'skip_location'), t('ru', 'skip_location')]
    if message.text not in skip_texts:
        await message.answer(t(lang, 'location_request'), reply_markup=location_keyboard(lang))
        return

    data = await state.get_data()
    time_from = datetime.fromisoformat(data['time_from'])
    time_to = datetime.fromisoformat(data['time_to'])

    await db.create_passenger_request(
        user_id=message.from_user.id,
        direction=data['direction'],
        seat_position=data['seat_pos'],
        seat_count=data['seat_count'],
        time_from=time_from,
        time_to=time_to,
        lat=None,
        lng=None
    )
    await state.clear()
    await message.answer(t(lang, 'request_sent'), reply_markup=passenger_menu_keyboard(lang))


# Faol so'rovni ko'rish
@router.message(F.text.in_(["📋 Mening so'rovim", "📋 Мой запрос"]))
async def my_request(message: Message):
    lang = await get_lang(message.from_user.id)
    req = await db.get_active_passenger_request(message.from_user.id)
    if not req:
        await message.answer(t(lang, 'no_active_request'))
        return

    direction = DIRECTION_LABELS[lang].get(req['direction'], req['direction'])
    seat_pos = SEAT_POS_LABELS[lang].get(req['seat_position'], req['seat_position'])
    status = STATUS_LABELS[lang].get(req['status'], req['status'])
    time_from = req['time_from'].strftime('%d.%m %H:%M')
    time_to = req['time_to'].strftime('%d.%m %H:%M')

    await message.answer(
        t(lang, 'active_request_info',
          direction=direction,
          seat_pos=seat_pos,
          seat_count=req['seat_count'],
          time_from=time_from,
          time_to=time_to,
          status=status),
        parse_mode="HTML"
    )


# So'rovni bekor qilish
@router.message(F.text.in_(["❌ So'rovni bekor qilish", "❌ Отменить запрос"]))
async def cancel_request(message: Message):
    lang = await get_lang(message.from_user.id)
    await db.cancel_passenger_request(message.from_user.id)
    await message.answer(t(lang, 'request_cancelled'))


# Tarix
@router.message(F.text.in_(["📜 Tarix", "📜 История"]))
async def show_history(message: Message):
    lang = await get_lang(message.from_user.id)
    user = await db.get_user(message.from_user.id)
    rows = await db.get_trip_history(message.from_user.id, user['role'])

    if not rows:
        await message.answer(t(lang, 'history_empty'))
        return

    text = t(lang, 'history_title')
    for row in rows:
        direction = DIRECTION_LABELS[lang].get(row['direction'], row['direction'])
        status = STATUS_LABELS[lang].get(row['status'], row['status'])
        date = row['created_at'].strftime('%d.%m.%Y')

        if user['role'] == 'driver':
            text += t(lang, 'history_driver_row',
                      direction=direction,
                      seats=row['seats'],
                      date=date,
                      status=status)
        else:
            driver_name = row['driver_name'] or ('Noma\'lum' if lang == 'uz' else 'Неизвестно')
            text += t(lang, 'history_passenger_row',
                      direction=direction,
                      date=date,
                      driver=driver_name,
                      status=status)

    await message.answer(text, parse_mode="HTML")


async def notify_passenger_driver_found(bot: Bot, passenger_user_id: int, driver_info: dict, lang: str):
    try:
        await bot.send_message(
            passenger_user_id,
            t(lang, 'driver_found',
              name=driver_info['full_name'],
              phone=driver_info['phone'],
              car=f"{driver_info['car_model']} ({driver_info['car_color']})",
              number=driver_info['car_number'],
              rating=driver_info['rating'] or 5.0)
        )
    except Exception:
        pass
