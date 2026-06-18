import asyncio
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import matching as mx
from keyboards import passenger_menu_keyboard, direction_keyboard
from texts import t

router = Router()

DIRS = {
    'uz': {'andijon_toshkent': 'Andijon → Toshkent', 'toshkent_andijon': 'Toshkent → Andijon'},
    'ru': {'andijon_toshkent': 'Андижан → Ташкент', 'toshkent_andijon': 'Ташкент → Андижан'},
}


class PassengerStates(StatesGroup):
    choosing_direction = State()
    choosing_seat_pos = State()
    choosing_seat_count = State()
    sending_location = State()
    confirming_location = State()
    entering_location_text = State()


async def get_lang(user_id):
    user = await db.get_user(user_id)
    return user['lang'] if user else 'uz'


def seat_pos_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🪑 Oldi o'rindiq" if lang == 'uz' else "🪑 Перед", callback_data="spos_front"),
        InlineKeyboardButton(text="💺 Orqa o'rindiq" if lang == 'uz' else "💺 Зад", callback_data="spos_back"),
    ]])


def seat_count_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="1️⃣", callback_data="scnt_1"),
        InlineKeyboardButton(text="2️⃣", callback_data="scnt_2"),
        InlineKeyboardButton(text="3️⃣", callback_data="scnt_3"),
    ]])


def location_kb(lang):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(
            text="📍 Lokatsiya yuborish" if lang == 'uz' else "📍 Отправить геолокацию",
            request_location=True
        )],
        [KeyboardButton(text="✏️ Joy nomini yozish" if lang == 'uz' else "✏️ Написать название места")],
    ], resize_keyboard=True, one_time_keyboard=True)


def confirm_location_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ To'g'ri" if lang == 'uz' else "✅ Верно",
            callback_data="loc_ok"
        ),
        InlineKeyboardButton(
            text="🔄 Qayta yuborish" if lang == 'uz' else "🔄 Отправить снова",
            callback_data="loc_retry"
        ),
    ]])


# ─── NAVBATGA TURISH ─────────────────────────────────────
@router.message(F.text.in_([
    "🚀 Andijon → Toshkent", "🔙 Toshkent → Andijon",
    "🚀 Андижан → Ташкент",  "🔙 Ташкент → Андижан"
]))
async def start_request(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("/start dan boshlang")
        return
    lang = user['lang']

    # Faol so'rovni tekshirish
    existing = await db.get_passenger_queue_entry(message.from_user.id)
    if existing:
        await message.answer(
            "⚠️ Sizda allaqachon faol so'rov bor! Avval uni bekor qiling." if lang == 'uz'
            else "⚠️ У вас уже есть активный запрос!"
        )
        return

    direction = 'andijon_toshkent' if ("Andijon" in message.text or "Андижан" in message.text) else 'toshkent_andijon'
    await state.update_data(direction=direction)
    await state.set_state(PassengerStates.choosing_seat_pos)
    await message.answer(t(lang, 'choose_seat_pos'), reply_markup=seat_pos_kb(lang))


@router.callback_query(F.data.in_(["spos_front", "spos_back"]))
async def choose_seat_pos(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    pos = 'front' if callback.data == 'spos_front' else 'back'
    await state.update_data(seat_pos=pos)
    await state.set_state(PassengerStates.choosing_seat_count)
    await callback.message.edit_text(t(lang, 'choose_seat_count'), reply_markup=seat_count_kb())


@router.callback_query(F.data.startswith("scnt_"))
async def choose_seat_count(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    cnt = int(callback.data.split("_")[1])
    await state.update_data(seat_count=cnt)
    await state.set_state(PassengerStates.sending_location)
    await callback.message.answer(
        "📍 Joylashuvingizni yuboring yoki joy nomini yozing.\n\n"
        "⚠️ GPS noto'g'ri bo'lishi mumkin — yuborgandan keyin tasdiqlash so'ralamiz."
        if lang == 'uz' else
        "📍 Отправьте геолокацию или напишите название места.\n\n"
        "⚠️ GPS может быть неточным — после отправки попросим подтвердить.",
        reply_markup=location_kb(lang)
    )
    await callback.message.delete()


# ─── LOKATSIYA (GPS) ──────────────────────────────────────
@router.message(PassengerStates.sending_location, F.location)
async def receive_location(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    lat = message.location.latitude
    lng = message.location.longitude

    await state.update_data(lat=lat, lng=lng, location_name=None)
    await state.set_state(PassengerStates.confirming_location)

    # Xaritada ko'rish havolasi
    maps_url = f"https://maps.google.com/maps?q={lat},{lng}"

    await message.answer(
        f"📍 Lokatsiyangiz:\n"
        f"<a href='{maps_url}'>Xaritada ko'rish</a>\n\n"
        f"Bu to'g'ri joyingizmi?" if lang == 'uz' else
        f"📍 Ваша локация:\n"
        f"<a href='{maps_url}'>Посмотреть на карте</a>\n\n"
        f"Это правильное место?",
        parse_mode="HTML",
        reply_markup=confirm_location_kb(lang)
    )


@router.callback_query(F.data == "loc_ok", PassengerStates.confirming_location)
async def confirm_location_ok(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = await get_lang(callback.from_user.id)
    data = await state.get_data()
    await state.clear()

    lat = data['lat']
    lng = data['lng']

    # Mintaqani aniqlash
    region = _detect_region(lat, lng)

    pq_id = await db.add_passenger_to_queue(
        callback.from_user.id, data['direction'],
        data['seat_pos'], data['seat_count']
    )
    await db.update_passenger_location(pq_id, lat, lng, None, region, confirmed=True)

    await callback.message.edit_text(
        "✅ Lokatsiya tasdiqlandi!\n\n⏳ Navbatda turibsiz. Haydovchi topilganda xabar beramiz." if lang == 'uz'
        else "✅ Локация подтверждена!\n\n⏳ Вы в очереди. Сообщим когда найдём водителя."
    )
    await callback.message.answer(t(lang, 'main_menu'), reply_markup=passenger_menu_keyboard(lang))

    # Mos haydovchi bormi?
    asyncio.create_task(try_match_passenger(bot, callback.from_user.id, data['direction'], lang))


@router.callback_query(F.data == "loc_retry")
async def retry_location(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    await state.set_state(PassengerStates.sending_location)
    await callback.message.edit_text(
        "📍 Qayta lokatsiya yuboring yoki joy nomini yozing:" if lang == 'uz'
        else "📍 Повторно отправьте геолокацию или напишите название места:"
    )
    await callback.message.answer("👇", reply_markup=location_kb(lang))


# ─── LOKATSIYA (MATN) ────────────────────────────────────
@router.message(PassengerStates.sending_location, F.text)
async def receive_location_text_trigger(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    skip_texts = ["✏️ Joy nomini yozish", "✏️ Написать название места"]
    if message.text in skip_texts:
        await state.set_state(PassengerStates.entering_location_text)
        await message.answer(
            "📝 Joy nomini yozing:\nMasalan: Andijon eski shahar, Xo'jaobod, Chilonzor" if lang == 'uz'
            else "📝 Напишите название места:\nНапример: Андижан старый город, Хужаабад, Чиланзар"
        )
    else:
        # Bevosita matn yozgan bo'lsa
        await state.set_state(PassengerStates.entering_location_text)
        await process_location_text(message, state)


@router.message(PassengerStates.entering_location_text, F.text)
async def process_location_text(message: Message, state: FSMContext, bot: Bot = None):
    lang = await get_lang(message.from_user.id)
    text = message.text.strip()
    region = mx.parse_region(text)

    data = await state.get_data()
    await state.clear()

    pq_id = await db.add_passenger_to_queue(
        message.from_user.id, data['direction'],
        data.get('seat_pos', 'back'), data.get('seat_count', 1)
    )
    await db.set_passenger_location_text(pq_id, text, region)

    await message.answer(
        f"✅ Joy qabul qilindi: <b>{text}</b>\n\n"
        f"⏳ Navbatda turibsiz. Haydovchi topilganda xabar beramiz." if lang == 'uz'
        else f"✅ Место принято: <b>{text}</b>\n\n"
        f"⏳ Вы в очереди. Сообщим когда найдём водителя.",
        parse_mode="HTML",
        reply_markup=passenger_menu_keyboard(lang)
    )

    if bot:
        asyncio.create_task(try_match_passenger(bot, message.from_user.id, data['direction'], lang))


def _detect_region(lat: float, lng: float) -> str:
    """GPS koordinatasidan mintaqani taxminiy aniqlaydi"""
    from matching import haversine, ROUTE_POINTS
    min_dist = float('inf')
    nearest = 'unknown'
    for p in ROUTE_POINTS:
        d = haversine(lat, lng, p['lat'], p['lng'])
        if d < min_dist:
            min_dist = d
            nearest = p['name'].lower().replace("'", "").replace(" ", "_")
    return nearest


async def try_match_passenger(bot: Bot, passenger_user_id: int, direction: str, lang: str):
    """Yo'lovchi uchun mos haydovchi borligini tekshiradi"""
    drivers = await db.get_waiting_drivers(direction)
    if not drivers:
        return

    waiting_pass = await db.get_waiting_passengers(direction)
    if not waiting_pass:
        return

    # Har bir kutayotgan haydovchi uchun guruh topishga harakat
    for dq in drivers:
        passengers = [dict(p) for p in waiting_pass]
        group = mx.find_best_group(passengers, dq['seats'])
        if group:
            # Yangi yo'lovchi shu guruhda bo'lishi kerak
            ids = [p['id'] for p in group]
            pq_entry = await db.get_passenger_queue_entry(passenger_user_id)
            if pq_entry and pq_entry['id'] in ids:
                from handlers.driver import try_match_driver
                asyncio.create_task(try_match_driver(bot, dq['id'], dq['user_id'], direction, dq['seats'], lang))
                break


# ─── SO'ROVNI BEKOR QILISH ───────────────────────────────
@router.message(F.text.in_(["❌ So'rovni bekor qilish", "❌ Отменить запрос"]))
async def cancel_request(message: Message):
    lang = await get_lang(message.from_user.id)
    await db.cancel_passenger_queue(message.from_user.id)
    await message.answer(
        "✅ So'rovingiz bekor qilindi." if lang == 'uz' else "✅ Ваш запрос отменён.",
        reply_markup=passenger_menu_keyboard(lang)
    )


# ─── FAOL SO'ROVNI KO'RISH ───────────────────────────────
@router.message(F.text.in_(["📋 Mening so'rovim", "📋 Мой запрос"]))
async def my_request(message: Message):
    lang = await get_lang(message.from_user.id)
    pq = await db.get_passenger_queue_entry(message.from_user.id)
    if not pq:
        await message.answer(
            "ℹ️ Sizda faol so'rov yo'q." if lang == 'uz' else "ℹ️ У вас нет активного запроса."
        )
        return

    dir_txt = DIRS[lang].get(pq['direction'], pq['direction'])
    seat_txt = ("🪑 Oldi" if lang == 'uz' else "🪑 Перед") if pq['seat_position'] == 'front' \
               else ("💺 Orqa" if lang == 'uz' else "💺 Зад")
    loc = pq['location_name'] or pq['region'] or ("Ko'rsatilmagan" if lang == 'uz' else "Не указано")
    status_map = {
        'waiting': "⏳ Kutilmoqda" if lang == 'uz' else "⏳ Ожидание",
        'matched': "✅ Haydovchi topildi" if lang == 'uz' else "✅ Водитель найден",
        'cancelled': "❌ Bekor" if lang == 'uz' else "❌ Отменено",
    }
    status = status_map.get(pq['status'], pq['status'])

    await message.answer(
        f"📋 <b>Faol so'rovingiz:</b>\n\n"
        f"🗺 Yo'nalish: {dir_txt}\n"
        f"💺 O'rindiq: {seat_txt} · {pq['seat_count']} kishi\n"
        f"📍 Joylashuv: {loc}\n"
        f"📊 Holat: {status}",
        parse_mode="HTML"
    )


async def notify_passenger_driver_found(bot: Bot, passenger_user_id: int, driver_info: dict, lang: str):
    try:
        await bot.send_message(
            passenger_user_id,
            f"🚗 Haydovchi siz bilan kelishdi!\n\n"
            f"👤 {driver_info['full_name']}\n"
            f"📞 {driver_info['phone']}\n"
            f"🚙 {driver_info['car_model']} · {driver_info['car_color']} · {driver_info['car_number']}\n"
            f"⭐ {driver_info['rating']:.1f}"
        )
    except Exception:
        pass
