import asyncio
from datetime import datetime, timedelta, timezone
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import matching as mx
from keyboards import driver_menu_keyboard, direction_keyboard, driver_seats_keyboard
from texts import t

router = Router()

CALL_TIMEOUT = 5 * 60  # 5 daqiqa sekund


class DriverRegStates(StatesGroup):
    car_model = State()
    car_number = State()
    car_color = State()


class EditCarStates(StatesGroup):
    car_model = State()
    car_number = State()
    car_color = State()


class QueueStates(StatesGroup):
    choosing_direction = State()
    choosing_seats = State()


async def get_lang(user_id):
    user = await db.get_user(user_id)
    return user['lang'] if user else 'uz'


# ─── RO'YXATDAN O'TISH ────────────────────────────────────
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
    await db.register_driver(message.from_user.id, data['car_model'], data['car_number'], message.text)
    await state.clear()
    await message.answer(t(lang, 'driver_registered'), reply_markup=driver_menu_keyboard(lang))


# ─── MASHINA TAHRIRLASH ───────────────────────────────────
@router.message(F.text.in_(["🚙 Mashinani tahrirlash", "🚙 Изменить авто"]))
async def start_edit_car(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    d = await db.get_driver_info(message.from_user.id)
    if not d:
        await message.answer(t(lang, 'register_driver'))
        return
    await state.set_state(EditCarStates.car_model)
    await message.answer(f"Hozirgi: {d['car_model']} | {d['car_number']} | {d['car_color']}\n\n" + t(lang, 'edit_car_model'))


@router.message(EditCarStates.car_model)
async def edit_car_model(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    await state.update_data(car_model=message.text)
    await state.set_state(EditCarStates.car_number)
    await message.answer(t(lang, 'edit_car_number'))


@router.message(EditCarStates.car_number)
async def edit_car_number(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    await state.update_data(car_number=message.text.upper())
    await state.set_state(EditCarStates.car_color)
    await message.answer(t(lang, 'edit_car_color'))


@router.message(EditCarStates.car_color)
async def edit_car_color(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    data = await state.get_data()
    await db.update_driver_car(message.from_user.id, data['car_model'], data['car_number'], message.text)
    await state.clear()
    await message.answer(t(lang, 'car_updated'), reply_markup=driver_menu_keyboard(lang))


# ─── NAVBATGA TURISH ──────────────────────────────────────
@router.message(F.text.in_(["🚀 Yo'nalish e'lon qilish", "🚀 Объявить рейс"]))
async def start_queue(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    driver = await db.get_driver_info(message.from_user.id)
    if not driver:
        await message.answer(t(lang, 'register_driver'))
        return
    active = await db.get_driver_active_group(message.from_user.id)
    if active:
        await message.answer("⚠️ Sizda faol guruh bor! Avval uni yakunlang." if lang == 'uz' else "⚠️ У вас есть активная группа!")
        return
    await state.set_state(QueueStates.choosing_direction)
    await message.answer(t(lang, 'choose_direction'), reply_markup=direction_keyboard(lang))


@router.callback_query(F.data.startswith("dir_"), QueueStates.choosing_direction)
async def choose_direction(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    direction = callback.data.replace("dir_", "")
    await state.update_data(direction=direction)
    await state.set_state(QueueStates.choosing_seats)
    await callback.message.edit_text(t(lang, 'choose_seats'), reply_markup=driver_seats_keyboard())


@router.callback_query(F.data.startswith("dseats_"))
async def choose_seats(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = await get_lang(callback.from_user.id)
    seats = int(callback.data.split("_")[1])
    data = await state.get_data()
    direction = data.get('direction', 'andijon_toshkent')
    await state.clear()

    dq_id = await db.add_driver_to_queue(callback.from_user.id, direction, seats)

    dir_txt = "Andijon → Toshkent" if direction == "andijon_toshkent" else "Toshkent → Andijon"
    await callback.message.edit_text(
        f"✅ Navbatga qo'shildingiz!\n\n"
        f"🗺 {dir_txt}\n💺 {seats} ta o'rin\n\n"
        f"⏳ Mos yo'lovchilar topilganda xabar beramiz..."
        if lang == 'uz' else
        f"✅ Вы в очереди!\n\n🗺 {dir_txt}\n💺 {seats} мест\n\n⏳ Сообщим когда найдём пассажиров..."
    )
    await callback.message.answer(t(lang, 'driver_menu'), reply_markup=driver_menu_keyboard(lang))

    # Mos guruh topishga harakat
    asyncio.create_task(try_match_driver(bot, dq_id, callback.from_user.id, direction, seats, lang))


async def try_match_driver(bot: Bot, dq_id: int, driver_user_id: int, direction: str, seats: int, lang: str):
    """Haydovchi uchun mos yo'lovchilar guruhini o'rindiq tekshiruvi bilan topadi"""
    waiting = await db.get_waiting_passengers(direction)
    if not waiting:
        return

    passengers = [dict(p) for p in waiting]
    result = mx.find_best_group(passengers, seats)
    if not result:
        return

    fitted, overflow = result

    # Asosiy guruhni yaratish
    group_id = await db.create_match_group(dq_id, direction)
    pq_ids = [p['id'] for p in fitted]
    await db.add_match_members(group_id, pq_ids, seat_overrides={p['id']: p.get('_final_seat') for p in fitted})
    await db.set_driver_queue_status(dq_id, 'matching')

    # Overflow yo'lovchilarga orqa o'rindiq taklifi
    for p in overflow:
        asyncio.create_task(offer_back_seat(bot, p, group_id, lang))

    await send_group_list(bot, driver_user_id, group_id, lang)


async def offer_back_seat(bot: Bot, passenger: dict, group_id: int, lang: str):
    """
    Oldi o'rindiq to'lganda yo'lovchiga orqa o'rindiq taklif qiladi.
    Yo'lovchi rozilasa guruhga qo'shiladi.
    """
    pq_id = passenger['id']
    user_id = passenger['user_id']
    back_avail = passenger.get('_back_available', 0)

    if back_avail <= 0:
        return  # Orqa ham to'lgan — taklif qilish shart emas

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Roziman, orqada ketaman",
            callback_data=f"back_ok_{pq_id}_{group_id}"
        ),
        InlineKeyboardButton(
            text="❌ Yo'q, kutaman",
            callback_data=f"back_no_{pq_id}"
        ),
    ]])

    try:
        await bot.send_message(
            user_id,
            f"🪑 Oldi o'rindiq band!\n\n"
            f"Siz oldi o'rindiq so'ragansiz, lekin u allaqachon band.\n"
            f"💺 Orqa o'rindiqda {back_avail} ta joy bor.\n\n"
            f"Orqa o'rindiqda ketasizmi?",
            reply_markup=kb
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("back_ok_"))
async def back_seat_accepted(callback: CallbackQuery, bot: Bot):
    """Yo'lovchi orqa o'rindiqqa rozi bo'ldi"""
    lang = await get_lang(callback.from_user.id)
    parts = callback.data.split("_")
    pq_id, group_id = int(parts[2]), int(parts[3])

    # Guruh hali ochiqmi?
    group = await db.get_match_group(group_id)
    if not group or group['status'] not in ('calling', 'confirmed'):
        await callback.message.edit_text("⚠️ Afsuski, bu guruh endi mavjud emas. Navbatda qolasiz.")
        return

    # Orqa o'rindiq hali bo'shmi?
    can_add, reason = await db.check_back_seat_available(group_id)
    if not can_add:
        await callback.message.edit_text(f"😔 {reason}\n\nNavbatda qolasiz.")
        return

    # Qo'shamiz — orqa o'rindiq bilan
    await db.add_match_members(group_id, [pq_id], seat_overrides={pq_id: 'back'})
    await callback.message.edit_text("✅ Qo'shildingiz! Haydovchi tez orada qo'ng'iroq qiladi.")

    # Haydovchiga xabar
    member_info = await db.get_passenger_queue_entry_by_id(pq_id)
    if member_info:
        dq = await db.get_driver_queue_by_group(group_id)
        if dq:
            try:
                await bot.send_message(
                    dq['user_id'],
                    f"➕ Yangi yo'lovchi qo'shildi (orqa o'rindiq):\n"
                    f"👤 {member_info['full_name'] if 'full_name' in member_info else '?'}\n"
                    f"📞 {member_info['phone'] if 'phone' in member_info else '?'}"
                )
            except Exception:
                pass


@router.callback_query(F.data.startswith("back_no_"))
async def back_seat_rejected(callback: CallbackQuery):
    """Yo'lovchi orqa o'rindiqqa rozi bo'lmadi — navbatda qoladi"""
    await callback.message.edit_text(
        "✅ Tushunildi. Siz navbatda qolasiz.\n"
        "Keyingi haydovchida oldi o'rindiq bo'sh bo'lsa xabar beramiz."
    )


async def send_group_list(bot: Bot, driver_user_id: int, group_id: int, lang: str):
    """Haydovchiga yo'lovchilar ro'yxatini o'rindiq ma'lumoti bilan yuboradi"""
    members = await db.get_group_members(group_id)
    if not members:
        return

    lines = []
    seat_labels = {'front': '🪑 Oldi', 'back': '💺 Orqa'}
    for i, m in enumerate(members):
        nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        n = nums[i] if i < 4 else f"{i+1}."
        loc = m['location_name'] or m['region'] or "Lokatsiya ko'rsatilmagan"
        seat = seat_labels.get(m['seat_position'], '💺')
        lines.append(f"{n} {m['full_name']} — {loc}\n   📞 {m['phone']} | {seat} | ⭐ {m['rating']:.1f}")

    text = (
        f"🎯 {len(members)} ta yo'lovchi topildi!\n\n" + "\n\n".join(lines) +
        "\n\n⏱ Har biriga 5 daqiqa vaqt beriladi. Qo'ng'iroq qilib tasdiqlang yoki rad eting."
    )
    await bot.send_message(driver_user_id, text)
    await start_next_call(bot, driver_user_id, group_id, lang)


async def start_next_call(bot: Bot, driver_user_id: int, group_id: int, lang: str):
    """Keyingi kutayotgan yo'lovchiga qo'ng'iroq jarayonini boshlaydi"""
    member = await db.get_next_pending_member(group_id)
    if not member:
        # Barcha ko'rib chiqildi
        await finalize_group(bot, driver_user_id, group_id, lang)
        return

    deadline = datetime.now(timezone.utc) + timedelta(seconds=CALL_TIMEOUT)
    await db.set_member_calling(member['id'], deadline)

    loc = member['location_name'] or member.get('region') or "Lokatsiya yo'q"
    seat_txt = "🪑 Oldi" if member['seat_position'] == 'front' else "💺 Orqa"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_m_{member['id']}_{group_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_m_{member['id']}_{group_id}")
    ]])

    await bot.send_message(
        driver_user_id,
        f"📞 Qo'ng'iroq qiling:\n\n"
        f"👤 {member['full_name']}\n"
        f"📱 {member['phone']}\n"
        f"📍 {loc}\n"
        f"💺 {seat_txt} | {member['seat_count']} kishi\n"
        f"⭐ {member['rating']:.1f}\n\n"
        f"⏱ 5 daqiqa ichida qaror qiling:",
        reply_markup=kb
    )

    # 5 daqiqa timeout
    asyncio.create_task(call_timeout_task(bot, driver_user_id, group_id, member['id'], lang))


async def call_timeout_task(bot: Bot, driver_user_id: int, group_id: int, member_id: int, lang: str):
    """5 daqiqa o'tsa avtomatik rad etish"""
    await asyncio.sleep(CALL_TIMEOUT)

    member = await db.get_next_pending_member(group_id)
    # Agar hali ham 'calling' bo'lsa — timeout
    async with db.pool.acquire() as conn:
        cur = await conn.fetchrow("SELECT call_status FROM match_members WHERE id=$1", member_id)

    if cur and cur['call_status'] == 'calling':
        await db.timeout_member(member_id)
        await bot.send_message(
            driver_user_id,
            "⏱ Vaqt tugadi! Yo'lovchi javob bermadi. Keyingi yo'lovchiga o'tamiz..."
        )
        await start_next_call(bot, driver_user_id, group_id, lang)


# ─── TASDIQLASH / RAD ETISH ──────────────────────────────
@router.callback_query(F.data.startswith("confirm_m_"))
async def confirm_member(callback: CallbackQuery, bot: Bot):
    lang = await get_lang(callback.from_user.id)
    parts = callback.data.split("_")
    member_id, group_id = int(parts[2]), int(parts[3])

    await db.confirm_member(member_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Tasdiqlandi!", show_alert=False)

    confirmed = await db.count_confirmed(group_id)
    pending = await db.count_pending(group_id)

    await callback.message.answer(f"✅ Tasdiqlandi! ({confirmed} ta tasdiqlangan)")

    if pending > 0:
        await start_next_call(bot, callback.from_user.id, group_id, lang)
    else:
        await finalize_group(bot, callback.from_user.id, group_id, lang)


@router.callback_query(F.data.startswith("reject_m_"))
async def reject_member_cb(callback: CallbackQuery, bot: Bot):
    lang = await get_lang(callback.from_user.id)
    parts = callback.data.split("_")
    member_id, group_id = int(parts[2]), int(parts[3])

    await db.reject_member(member_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("❌ Rad etildi", show_alert=False)
    await callback.message.answer("❌ Rad etildi. Keyingi yo'lovchiga o'tamiz...")

    # 30 daqiqa ichida o'sha hududdan yangi yo'lovchi qidirish
    asyncio.create_task(wait_for_replacement(bot, callback.from_user.id, group_id, lang))


async def wait_for_replacement(bot: Bot, driver_user_id: int, group_id: int, lang: str):
    """30 daqiqa kutib, o'sha hududdan yangi yo'lovchi qidiradi"""
    pending = await db.count_pending(group_id)
    if pending > 0:
        await start_next_call(bot, driver_user_id, group_id, lang)
        return

    # Yangi yo'lovchi keladimi?
    await bot.send_message(driver_user_id, "⏳ 30 daqiqa o'sha hududdan yangi yo'lovchi kutilmoqda...")
    await asyncio.sleep(30 * 60)

    # Hali ham guruh ochiq?
    group = await db.get_match_group(group_id)
    if not group or group['status'] not in ('calling', 'confirmed'):
        return

    # Topilmasa — mavjud a'zolar bilan yakunlash
    confirmed = await db.count_confirmed(group_id)
    if confirmed > 0:
        await bot.send_message(driver_user_id, f"⏱ Yangi yo'lovchi topilmadi. {confirmed} ta yo'lovchi bilan davom etamiz.")
        await finalize_group(bot, driver_user_id, group_id, lang)
    else:
        await bot.send_message(driver_user_id, "😔 Yo'lovchi topilmadi. Navbatga qaytdingiz.")
        await db.set_group_status(group_id, 'cancelled')


async def finalize_group(bot: Bot, driver_user_id: int, group_id: int, lang: str):
    """Barcha yo'lovchilar ko'rib chiqilgandan keyin marshrut tuzib beradi"""
    confirmed = await db.get_confirmed_members(group_id)
    if not confirmed:
        await bot.send_message(driver_user_id, "😔 Hech kim tasdiqlamadi. Navbatga qaytdingiz.")
        await db.set_group_status(group_id, 'cancelled')
        return

    await db.set_group_status(group_id, 'confirmed')

    # Haydovchi lokatsiyasini olish (hozircha None)
    driver_lat, driver_lng = None, None

    passengers = [dict(m) for m in confirmed]
    sorted_pass = mx.sort_passengers_for_pickup(driver_lat, driver_lng, passengers)

    route_text = mx.build_route_text(sorted_pass, lang)
    nav_url = mx.build_yandex_navigator_url(driver_lat, driver_lng, sorted_pass)

    text = (
        f"✅ {len(sorted_pass)} ta yo'lovchi tasdiqladi!\n\n"
        f"📍 <b>Marshrut tartibi:</b>\n{route_text}\n\n"
        f"🚗 Qaysi birini birinchi, qaysinisini keyin olish — yuqoridagi tartibda."
    )

    kb = None
    if nav_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗺 Yandex Navigator da ochish", url=nav_url)
        ], [
            InlineKeyboardButton(text="🏁 Safarni yakunlash", callback_data=f"finish_group_{group_id}")
        ]])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏁 Safarni yakunlash", callback_data=f"finish_group_{group_id}")
        ]])

    await bot.send_message(driver_user_id, text, parse_mode="HTML", reply_markup=kb)

    # Har bir yo'lovchiga tasdiqlangan xabar
    for p in sorted_pass:
        try:
            puser = await db.get_user(p['user_id'])
            if puser:
                driver_info = await db.get_driver_info(driver_user_id)
                await bot.send_message(
                    p['user_id'],
                    f"🚗 Haydovchi siz bilan kelishdi!\n\n"
                    f"👤 {driver_info['full_name']}\n"
                    f"📞 {driver_info['phone']}\n"
                    f"🚙 {driver_info['car_model']} · {driver_info['car_color']} · {driver_info['car_number']}\n"
                    f"⭐ {driver_info['rating']:.1f}\n\n"
                    f"Haydovchi tez orada siz bilan bog'lanadi!"
                )
        except Exception:
            pass


@router.callback_query(F.data.startswith("finish_group_"))
async def finish_group(callback: CallbackQuery, bot: Bot):
    lang = await get_lang(callback.from_user.id)
    group_id = int(callback.data.split("_")[2])

    confirmed = await db.get_confirmed_members(group_id)
    await db.set_group_status(group_id, 'completed')
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Safar yakunlandi!", show_alert=False)
    await callback.message.answer("🏁 Safar yakunlandi! Yo'lovchilardan baho so'ralmoqda...")

    driver_info = await db.get_driver_info(callback.from_user.id)

    for m in confirmed:
        try:
            puser = await db.get_user(m['user_id'])
            if puser:
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="1⭐", callback_data=f"rate_{callback.from_user.id}_{group_id}_1"),
                    InlineKeyboardButton(text="2⭐", callback_data=f"rate_{callback.from_user.id}_{group_id}_2"),
                    InlineKeyboardButton(text="3⭐", callback_data=f"rate_{callback.from_user.id}_{group_id}_3"),
                    InlineKeyboardButton(text="4⭐", callback_data=f"rate_{callback.from_user.id}_{group_id}_4"),
                    InlineKeyboardButton(text="5⭐", callback_data=f"rate_{callback.from_user.id}_{group_id}_5"),
                ]])
                await bot.send_message(
                    m['user_id'],
                    f"⭐ Haydovchini baholang ({driver_info['full_name']}):",
                    reply_markup=kb
                )
        except Exception:
            pass


@router.callback_query(F.data.startswith("rate_"))
async def save_rating(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    parts = callback.data.split("_")
    driver_id, group_id, stars = int(parts[1]), int(parts[2]), int(parts[3])

    saved = await db.save_rating(callback.from_user.id, driver_id, group_id, stars)
    await callback.message.edit_reply_markup(reply_markup=None)
    if saved:
        await callback.answer("⭐ Rahmat! Bahoyingiz qabul qilindi.", show_alert=True)
    else:
        await callback.answer("Siz allaqachon baho bergansiz.", show_alert=True)


# ─── NAVBATDAN CHIQISH ────────────────────────────────────
@router.message(F.text.in_(["❌ Navbatdan chiqish", "❌ Выйти из очереди"]))
async def leave_queue(message: Message):
    lang = await get_lang(message.from_user.id)
    await db.cancel_driver_queue(message.from_user.id)
    await message.answer(
        "✅ Navbatdan chiqdingiz." if lang == 'uz' else "✅ Вы вышли из очереди.",
        reply_markup=driver_menu_keyboard(lang)
    )


# ─── STATISTIKA ───────────────────────────────────────────
@router.message(F.text.in_(["📊 Statistikam", "📊 Моя статистика"]))
async def my_stats(message: Message):
    lang = await get_lang(message.from_user.id)
    async with db.pool.acquire() as conn:
        total = await conn.fetchval("""
            SELECT COUNT(*) FROM match_groups mg
            JOIN driver_queue dq ON dq.id=mg.driver_queue_id
            WHERE dq.user_id=$1 AND mg.status='completed'
        """, message.from_user.id)
        today = await conn.fetchval("""
            SELECT COUNT(*) FROM match_groups mg
            JOIN driver_queue dq ON dq.id=mg.driver_queue_id
            WHERE dq.user_id=$1 AND mg.status='completed' AND DATE(mg.created_at)=CURRENT_DATE
        """, message.from_user.id)
    user = await db.get_user(message.from_user.id)
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"🚗 Jami safarlar: <b>{total}</b>\n"
        f"📅 Bugun: <b>{today}</b>\n"
        f"⭐ Reyting: <b>{user['rating']:.1f}</b> ({user['rating_count']} baho)",
        parse_mode="HTML"
    )
