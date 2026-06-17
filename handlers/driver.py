from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta

import database as db
from matching import find_best_matches
from keyboards import (
    direction_keyboard, driver_seats_keyboard, time_keyboard,
    hours_keyboard, location_keyboard, driver_menu_keyboard,
    accept_reject_keyboard, rating_keyboard
)
from texts import t

router = Router()


class DriverRegStates(StatesGroup):
    car_model = State()
    car_number = State()
    car_color = State()


class DriverTripStates(StatesGroup):
    choosing_direction = State()
    choosing_seats = State()
    choosing_time = State()
    choosing_hour = State()
    sending_location = State()


async def get_lang(user_id):
    user = await db.get_user(user_id)
    return user['lang'] if user else 'uz'


# --- Ro'yxatdan o'tish ---

@router.message(F.text.in_(["📝 Haydovchi sifatida ro'yxatdan o'tish", "📝 Зарегистрироваться как водитель"]))
async def start_driver_reg(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    await state.set_state(DriverRegStates.car_model)
    await message.answer(t(lang, 'car_model'))


@router.message(DriverRegStates.car_model)
async def get_car_model(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    await state.update_data(car_model=message.text)
    await state.set_state(DriverRegStates.car_number)
    await message.answer(t(lang, 'car_number'))


@router.message(DriverRegStates.car_number)
async def get_car_number(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    await state.update_data(car_number=message.text.upper())
    await state.set_state(DriverRegStates.car_color)
    await message.answer(t(lang, 'car_color'))


@router.message(DriverRegStates.car_color)
async def get_car_color(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    data = await state.get_data()
    await db.register_driver(
        user_id=message.from_user.id,
        car_model=data['car_model'],
        car_number=data['car_number'],
        car_color=message.text
    )
    await state.clear()
    await message.answer(t(lang, 'driver_registered'), reply_markup=driver_menu_keyboard(lang))


# --- Trip e'lon qilish ---

@router.message(F.text.in_(["🚀 Yo'nalish e'lon qilish", "🚀 Объявить рейс"]))
async def announce_trip(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    driver = await db.get_driver_info(message.from_user.id)
    if not driver:
        await message.answer(t(lang, 'register_driver'))
        return
    await state.set_state(DriverTripStates.choosing_direction)
    await message.answer(t(lang, 'choose_direction'), reply_markup=direction_keyboard(lang))


@router.callback_query(F.data.startswith("dir_"), DriverTripStates.choosing_direction)
async def driver_choose_direction(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    direction = callback.data.replace("dir_", "")
    await state.update_data(direction=direction)
    await state.set_state(DriverTripStates.choosing_seats)
    await callback.message.edit_text(t(lang, 'choose_seats'), reply_markup=driver_seats_keyboard())


@router.callback_query(F.data.startswith("dseats_"))
async def driver_choose_seats(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    seats = int(callback.data.split("_")[1])
    await state.update_data(seats=seats)
    await state.set_state(DriverTripStates.choosing_time)
    await callback.message.edit_text(t(lang, 'choose_time'), reply_markup=time_keyboard(lang))


@router.callback_query(F.data.in_(["time_now", "time_today", "time_tomorrow"]), DriverTripStates.choosing_time)
async def driver_choose_time(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    now = datetime.now()

    if callback.data == "time_now":
        await state.update_data(depart_time=now.isoformat())
        await state.set_state(DriverTripStates.sending_location)
        await callback.message.answer(t(lang, 'location_request'), reply_markup=location_keyboard(lang))
        await callback.message.delete()
    elif callback.data == "time_today":
        await state.update_data(base_date=now.date().isoformat())
        await state.set_state(DriverTripStates.choosing_hour)
        await callback.message.edit_text(t(lang, 'choose_hour_from'), reply_markup=hours_keyboard("dhour"))
    else:
        tomorrow = (now + timedelta(days=1)).date()
        await state.update_data(base_date=tomorrow.isoformat())
        await state.set_state(DriverTripStates.choosing_hour)
        await callback.message.edit_text(t(lang, 'choose_hour_from'), reply_markup=hours_keyboard("dhour"))


@router.callback_query(F.data.startswith("dhour_"))
async def driver_choose_hour(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    hour = int(callback.data.split("_")[1])
    data = await state.get_data()
    from datetime import date
    bd = date.fromisoformat(data['base_date'])
    depart_time = datetime(bd.year, bd.month, bd.day, hour)
    await state.update_data(depart_time=depart_time.isoformat())
    await state.set_state(DriverTripStates.sending_location)
    await callback.message.answer(t(lang, 'location_request'), reply_markup=location_keyboard(lang))
    await callback.message.delete()


@router.message(DriverTripStates.sending_location, F.location)
async def driver_receive_location(message: Message, state: FSMContext, bot: Bot):
    lang = await get_lang(message.from_user.id)
    data = await state.get_data()
    depart_time = datetime.fromisoformat(data['depart_time'])

    trip_id = await db.create_driver_trip(
        driver_id=message.from_user.id,
        direction=data['direction'],
        seats=data['seats'],
        depart_time=depart_time,
        lat=message.location.latitude,
        lng=message.location.longitude
    )

    await state.clear()
    await message.answer(t(lang, 'trip_announced'), reply_markup=driver_menu_keyboard(lang))

    # Matching boshlash
    await do_matching(bot, message.from_user.id, trip_id, data['direction'],
                      depart_time, data['seats'],
                      message.location.latitude, message.location.longitude, lang)


async def do_matching(bot: Bot, driver_id: int, trip_id: int, direction: str,
                      depart_time: datetime, seats: int, lat: float, lng: float, lang: str):
    same = await db.get_waiting_passengers(direction, depart_time)
    opposite_dir = 'toshkent_andijon' if direction == 'andijon_toshkent' else 'andijon_toshkent'
    opposite = await db.get_waiting_passengers_extended(opposite_dir, depart_time)

    matched = find_best_matches(lat, lng, direction, seats,
                                [dict(p) for p in same],
                                [dict(p) for p in opposite])

    if not matched:
        await bot.send_message(driver_id, t(lang, 'no_passengers'))
        return

    await bot.send_message(driver_id, t(lang, 'passengers_found', count=len(matched)))

    driver_info = await db.get_driver_info(driver_id)

    for p in matched:
        seat_pos_text = "Oldi 🪑" if p['seat_position'] == 'front' else "Orqa 💺"
        card = t(lang, 'passenger_card',
                 name=p['full_name'],
                 phone=p['phone'],
                 seat_pos=seat_pos_text,
                 seat_count=p['seat_count'],
                 dist=p['_distance'],
                 rating=p['rating'] or 5.0)

        location_url = f"https://maps.google.com/maps?q={p['lat']},{p['lng']}"
        card += f"\n🗺 <a href='{location_url}'>Xaritada ko'rish</a>"

        await bot.send_message(
            driver_id, card,
            reply_markup=accept_reject_keyboard(p['id'], trip_id),
            parse_mode="HTML"
        )

        # Match qilish
        await db.match_passenger_to_trip(p['id'], trip_id)


# --- Qabul / Rad ---

@router.callback_query(F.data.startswith("accept_"))
async def accept_passenger(callback: CallbackQuery, bot: Bot):
    lang = await get_lang(callback.from_user.id)
    _, passenger_id, trip_id = callback.data.split("_")
    passenger_id, trip_id = int(passenger_id), int(trip_id)

    driver_info = await db.get_driver_info(callback.from_user.id)
    passenger = await db.get_user(
        (await db.pool.acquire().__aenter__() if False else None) or passenger_id
    )

    # Haydovchi ma'lumotini yo'lovchiga yuborish
    async with db.pool.acquire() as conn:
        p = await conn.fetchrow("SELECT user_id, lang FROM passenger_requests pr JOIN users u ON u.id=pr.user_id WHERE pr.id=$1", passenger_id)

    if p:
        p_lang = p['lang']
        from handlers.passenger import notify_passenger_driver_found
        await notify_passenger_driver_found(bot, p['user_id'], dict(driver_info), p_lang)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(t(lang, 'passenger_accepted'), show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def reject_passenger(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    _, passenger_id, trip_id = callback.data.split("_")
    passenger_id = int(passenger_id)

    await db.reject_passenger(passenger_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(t(lang, 'passenger_rejected'), show_alert=True)


# --- Safarni yakunlash ---

@router.message(F.text.in_(["🏁 Safarni yakunlash", "🏁 Завершить поездку"]))
async def finish_trip(message: Message, bot: Bot):
    lang = await get_lang(message.from_user.id)

    async with db.pool.acquire() as conn:
        trip = await conn.fetchrow(
            "SELECT id FROM driver_trips WHERE driver_id=$1 AND status='waiting' OR status='active' ORDER BY created_at DESC LIMIT 1",
            message.from_user.id
        )

    if not trip:
        await message.answer("Faol safar topilmadi." if lang == 'uz' else "Активная поездка не найдена.")
        return

    passenger_ids = await db.complete_trip(trip['id'])
    await message.answer(t(lang, 'trip_finished'))

    driver_info = await db.get_driver_info(message.from_user.id)

    for pid in passenger_ids:
        puser = await db.get_user(pid)
        if puser:
            try:
                await bot.send_message(
                    pid,
                    t(puser['lang'], 'rate_driver', name=driver_info['full_name']),
                    reply_markup=rating_keyboard(message.from_user.id, trip['id'])
                )
            except Exception:
                pass


# --- Reyting ---

@router.callback_query(F.data.startswith("rate_"))
async def save_rating(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    parts = callback.data.split("_")
    driver_id, trip_id, stars = int(parts[1]), int(parts[2]), int(parts[3])

    await db.save_rating(callback.from_user.id, driver_id, trip_id, stars)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(t(lang, 'rating_saved'), show_alert=True)


# --- Statistika ---

@router.message(F.text.in_(["📊 Statistikam", "📊 Моя статистика"]))
async def my_stats(message: Message):
    lang = await get_lang(message.from_user.id)
    stats = await db.get_driver_stats(message.from_user.id)
    await message.answer(t(lang, 'stats_text',
                           total=stats['total'],
                           today=stats['today'],
                           rating=stats['rating'] or 5.0))
