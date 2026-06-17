from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import asyncio

import database as db
from matching import find_best_matches
from keyboards import (
    direction_keyboard, seat_position_keyboard, seat_count_keyboard,
    time_keyboard, hours_keyboard, location_keyboard, passenger_menu_keyboard,
    accept_reject_keyboard
)
from texts import t

router = Router()

DIRECTION_MAP = {
    'andijon_toshkent': 'toshkent_andijon',
    'toshkent_andijon': 'andijon_toshkent'
}


class PassengerStates(StatesGroup):
    choosing_direction = State()
    choosing_seat_pos = State()
    choosing_seat_count = State()
    choosing_time = State()
    choosing_hour_from = State()
    choosing_hour_to = State()
    sending_location = State()


async def get_lang(user_id):
    user = await db.get_user(user_id)
    return user['lang'] if user else 'uz'


@router.message(F.text.in_(["🚀 Andijon → Toshkent", "🔙 Toshkent → Andijon",
                              "🚀 Андижан → Ташкент", "🔙 Ташкент → Андижан"]))
async def start_passenger_request(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Iltimos avval /start dan boshlang.")
        return
    lang = user['lang']

    if "Andijon" in message.text or "Андижан" in message.text:
        direction = 'andijon_toshkent'
    else:
        direction = 'toshkent_andijon'

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
    now = datetime.now()

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
    base_date = data.get('base_date')

    if hour_to <= hour_from:
        await callback.answer("❌ 'Gacha' vaqti 'Dan' vaqtidan katta bo'lishi kerak!", show_alert=True)
        return

    from datetime import date
    bd = date.fromisoformat(base_date)
    time_from = datetime(bd.year, bd.month, bd.day, hour_from)
    time_to = datetime(bd.year, bd.month, bd.day, hour_to)

    await state.update_data(time_from=time_from.isoformat(), time_to=time_to.isoformat())
    await state.set_state(PassengerStates.sending_location)
    await callback.message.answer(t(lang, 'location_request'), reply_markup=location_keyboard(lang))
    await callback.message.delete()


@router.message(PassengerStates.sending_location, F.location)
async def receive_location(message: Message, state: FSMContext, bot: Bot):
    lang = await get_lang(message.from_user.id)
    data = await state.get_data()

    user = await db.get_user(message.from_user.id)
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


@router.message(F.text.in_(["❌ So'rovni bekor qilish", "❌ Отменить запрос"]))
async def cancel_request(message: Message):
    lang = await get_lang(message.from_user.id)
    await db.cancel_passenger_request(message.from_user.id)
    await message.answer(t(lang, 'request_cancelled'))


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
