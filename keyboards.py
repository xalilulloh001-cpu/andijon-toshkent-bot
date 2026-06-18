from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from texts import t


def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")]
    ])


def role_keyboard(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'role_passenger'), callback_data="role_passenger"),
         InlineKeyboardButton(text=t(lang, 'role_driver'), callback_data="role_driver")]
    ])


def contact_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, 'contact_btn'), request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


def location_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, 'location_btn'), request_location=True)],
            [KeyboardButton(text=t(lang, 'skip_location'))]
        ],
        resize_keyboard=True, one_time_keyboard=True
    )


def direction_keyboard(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'dir_and_tosh'), callback_data="dir_andijon_toshkent")],
        [InlineKeyboardButton(text=t(lang, 'dir_tosh_and'), callback_data="dir_toshkent_andijon")]
    ])


def seat_position_keyboard(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'seat_front'), callback_data="seat_front"),
         InlineKeyboardButton(text=t(lang, 'seat_back'), callback_data="seat_back")]
    ])


def seat_count_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ 1 kishi", callback_data="count_1"),
         InlineKeyboardButton(text="2️⃣ 2 kishi", callback_data="count_2"),
         InlineKeyboardButton(text="3️⃣ 3 kishi", callback_data="count_3")]
    ])


def driver_seats_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣", callback_data="dseats_1"),
         InlineKeyboardButton(text="2️⃣", callback_data="dseats_2"),
         InlineKeyboardButton(text="3️⃣", callback_data="dseats_3"),
         InlineKeyboardButton(text="4️⃣", callback_data="dseats_4")]
    ])


def time_keyboard(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'time_now'), callback_data="time_now")],
        [InlineKeyboardButton(text=t(lang, 'time_today'), callback_data="time_today")],
        [InlineKeyboardButton(text=t(lang, 'time_tomorrow'), callback_data="time_tomorrow")]
    ])


def hours_keyboard(prefix="hour"):
    builder = InlineKeyboardBuilder()
    for h in range(5, 24):
        builder.button(text=f"{h:02d}:00", callback_data=f"{prefix}_{h}")
    builder.adjust(4)
    return builder.as_markup()


def passenger_menu_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, 'dir_and_tosh')), KeyboardButton(text=t(lang, 'dir_tosh_and'))],
            [KeyboardButton(text=t(lang, 'my_request')), KeyboardButton(text=t(lang, 'cancel_request'))],
            [KeyboardButton(text=t(lang, 'history_btn')), KeyboardButton(text=t(lang, 'settings_btn'))]
        ],
        resize_keyboard=True
    )


def driver_menu_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, 'announce_trip'))],
            [KeyboardButton(text=t(lang, 'finish_trip')), KeyboardButton(text=t(lang, 'my_stats'))],
            [KeyboardButton(text=t(lang, 'history_btn')), KeyboardButton(text=t(lang, 'edit_car_btn'))],
            [KeyboardButton(text=t(lang, 'settings_btn'))]
        ],
        resize_keyboard=True
    )


def admin_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Broadcast")],
            [KeyboardButton(text="🚫 Block user"), KeyboardButton(text="✅ Unblock user")],
        ],
        resize_keyboard=True
    )


def accept_reject_keyboard(passenger_id: int, trip_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Qabul", callback_data=f"accept_{passenger_id}_{trip_id}"),
         InlineKeyboardButton(text="❌ Rad", callback_data=f"reject_{passenger_id}_{trip_id}")]
    ])


def rating_keyboard(driver_id: int, trip_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1⭐", callback_data=f"rate_{driver_id}_{trip_id}_1"),
            InlineKeyboardButton(text="2⭐", callback_data=f"rate_{driver_id}_{trip_id}_2"),
            InlineKeyboardButton(text="3⭐", callback_data=f"rate_{driver_id}_{trip_id}_3"),
            InlineKeyboardButton(text="4⭐", callback_data=f"rate_{driver_id}_{trip_id}_4"),
            InlineKeyboardButton(text="5⭐", callback_data=f"rate_{driver_id}_{trip_id}_5"),
        ]
    ])


def settings_keyboard(lang):
    current = "🇺🇿 O'zbekcha" if lang == 'uz' else "🇷🇺 Русский"
    switch = "🇷🇺 Русскийга o'tish" if lang == 'uz' else "🇺🇿 O'zbekchaга перейти"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Til: {current} → {switch}", callback_data="switch_lang")],
        [InlineKeyboardButton(text="🔄 Rolni o'zgartirish" if lang == 'uz' else "🔄 Изменить роль",
                              callback_data="change_role")]
    ])


def confirm_keyboard(lang):
    yes = "✅ Ha" if lang == 'uz' else "✅ Да"
    no = "❌ Yo'q" if lang == 'uz' else "❌ Нет"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=yes, callback_data="confirm_yes"),
         InlineKeyboardButton(text=no, callback_data="confirm_no")]
    ])
