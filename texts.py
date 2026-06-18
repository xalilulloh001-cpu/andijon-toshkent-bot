TEXTS = {
    'uz': {
        # Umumiy
        'start': "Assalomu alaykum! 👋\nAndijon ↔ Toshkent Taksi Botiga xush kelibsiz!\n\nTilni tanlang:",
        'choose_lang': "Tilni tanlang / Выберите язык:",
        'lang_set': "Til o'rnatildi ✅",
        'main_menu': "🏠 Asosiy menyu",
        'choose_role': "Siz kimsiniz?",
        'role_passenger': "🧳 Yo'lovchi",
        'role_driver': "🚗 Haydovchi",
        'contact_request': "📱 Telefon raqamingizni yuboring:",
        'contact_btn': "📱 Raqamni ulashish",
        'name_request': "Ismingizni kiriting:",
        'registered': "✅ Ro'yxatdan o'tdingiz!",
        'settings_btn': "⚙️ Sozlamalar",

        # Yo'lovchi
        'choose_direction': "Yo'nalishni tanlang:",
        'dir_and_tosh': "🚀 Andijon → Toshkent",
        'dir_tosh_and': "🔙 Toshkent → Andijon",
        'choose_seat_pos': "O'tirish joyini tanlang:",
        'seat_front': "🪑 Oldi o'rindiq",
        'seat_back': "💺 Orqa o'rindiq",
        'choose_seat_count': "Nechta kishi?",
        'choose_time': "Vaqtni tanlang:",
        'time_now': "⚡ Hozir",
        'time_today': "📅 Bugun (soat tanlash)",
        'time_tomorrow': "📆 Ertaga (soat tanlash)",
        'choose_hour_from': "Jo'nash vaqti (dan):",
        'choose_hour_to': "Jo'nash vaqti (gacha):",
        'location_request': "📍 Joylashuvingizni yuboring (ixtiyoriy):",
        'location_btn': "📍 Lokatsiya yuborish",
        'skip_location': "⏭ O'tkazib yuborish",
        'request_sent': "✅ So'rovingiz qabul qilindi! Haydovchi topilganda xabar beramiz. 🚗",
        'in_queue': "⏳ Siz navbatdasiz. Sabr qiling...",
        'cancel_request': "❌ So'rovni bekor qilish",
        'request_cancelled': "✅ So'rovingiz bekor qilindi.",
        'my_request': "📋 Mening so'rovim",
        'no_active_request': "ℹ️ Sizda faol so'rov yo'q.",
        'active_request_info': "📋 <b>Faol so'rovingiz:</b>\n\n🗺 Yo'nalish: {direction}\n💺 O'rindiq: {seat_pos}\n👥 Kishi: {seat_count}\n🕐 Vaqt: {time_from} - {time_to}\n📊 Holat: {status}",
        'driver_found': "🚗 Haydovchi topildi!\n\n👤 Ism: {name}\n📞 Tel: {phone}\n🚙 Mashina: {car}\n🔢 Raqam: {number}\n⭐ Reyting: {rating:.1f}\n\nHaydovchi siz bilan bog'lanadi!",

        # Tarix
        'history_btn': "📜 Tarix",
        'history_empty': "📜 Safarlar tarixi bo'sh.",
        'history_title': "📜 <b>So'nggi safarlar:</b>\n\n",
        'history_driver_row': "🚗 <b>{direction}</b> | {seats} o'rin | {date}\n   Holat: {status}\n\n",
        'history_passenger_row': "🧳 <b>{direction}</b> | {date}\n   Haydovchi: {driver} | Holat: {status}\n\n",

        # Haydovchi
        'driver_menu': "🚗 Haydovchi menyusi",
        'register_driver': "📝 Haydovchi sifatida ro'yxatdan o'tish",
        'car_model': "Mashina modelini kiriting (masalan: Nexia 3):",
        'car_number': "Mashina raqamini kiriting (masalan: 30 A 123 AA):",
        'car_color': "Mashina rangini kiriting:",
        'driver_registered': "✅ Haydovchi sifatida ro'yxatdan o'tdingiz!",
        'announce_trip': "🚀 Yo'nalish e'lon qilish",
        'active_trip_exists': "⚠️ Sizda hozir faol safar bor! Avval uni yakunlang.",
        'choose_seats': "Nechta yo'lovchi olasiz?",
        'trip_announced': "✅ E'lon qilindi! Mos yo'lovchilar qidirilmoqda...",
        'no_passengers': "😔 Hozircha mos yo'lovchi topilmadi. Topilganda xabar beramiz!",
        'passengers_found': "🎯 {count} ta yo'lovchi topildi!\n\nHar birini ko'rib chiqing:",
        'passenger_card': "👤 {name}\n📞 {phone}\n💺 {seat_pos} | 👥 {seat_count} kishi\n📍 Masofa: {dist:.1f} km\n⭐ Reyting: {rating:.1f}",
        'accept': "✅ Qabul",
        'reject': "❌ Rad",
        'passenger_accepted': "✅ Yo'lovchi qabul qilindi. Ular bilan bog'laning!",
        'passenger_rejected': "❌ Rad etildi. Yo'lovchi navbatda qoldi.",
        'finish_trip': "🏁 Safarni yakunlash",
        'no_active_trip': "ℹ️ Faol safar topilmadi.",
        'trip_finished': "✅ Safar yakunlandi! Yo'lovchilardan baho so'ralmoqda...",
        'my_stats': "📊 Statistikam",
        'stats_text': "📊 <b>Statistika</b>\n\n🚗 Jami safarlar: <b>{total}</b>\n📅 Bugun: <b>{today}</b>\n⭐ Reyting: <b>{rating:.1f}</b> ({rating_count} ta baho)",

        # Mashina tahrirlash
        'edit_car_btn': "🚙 Mashinani tahrirlash",
        'edit_car_model': "Yangi mashina modelini kiriting:",
        'edit_car_number': "Yangi mashina raqamini kiriting:",
        'edit_car_color': "Yangi mashina rangini kiriting:",
        'car_updated': "✅ Mashina ma'lumotlari yangilandi!",

        # Reyting
        'rate_driver': "⭐ Haydovchini baholang ({name}):",
        'rate_already': "Siz bu safar uchun allaqachon baho bergansiz.",
        'rating_saved': "✅ Bahoyingiz saqlandi! Rahmat!",

        # Admin
        'admin_menu': "👑 Admin paneli",
        'not_registered': "Iltimos avval ro'yxatdan o'ting. /start",
        'error': "❌ Xatolik yuz berdi. Qayta urinib ko'ring.",
        'back': "🔙 Orqaga",
    },
    'ru': {
        # Общее
        'start': "Здравствуйте! 👋\nДобро пожаловать в Такси Бот Андижан ↔ Ташкент!\n\nВыберите язык:",
        'choose_lang': "Выберите язык / Tilni tanlang:",
        'lang_set': "Язык установлен ✅",
        'main_menu': "🏠 Главное меню",
        'choose_role': "Кто вы?",
        'role_passenger': "🧳 Пассажир",
        'role_driver': "🚗 Водитель",
        'contact_request': "📱 Отправьте ваш номер телефона:",
        'contact_btn': "📱 Поделиться номером",
        'name_request': "Введите ваше имя:",
        'registered': "✅ Вы зарегистрированы!",
        'settings_btn': "⚙️ Настройки",

        # Пассажир
        'choose_direction': "Выберите направление:",
        'dir_and_tosh': "🚀 Андижан → Ташкент",
        'dir_tosh_and': "🔙 Ташкент → Андижан",
        'choose_seat_pos': "Выберите место:",
        'seat_front': "🪑 Переднее сиденье",
        'seat_back': "💺 Заднее сиденье",
        'choose_seat_count': "Сколько человек?",
        'choose_time': "Выберите время:",
        'time_now': "⚡ Сейчас",
        'time_today': "📅 Сегодня (выбрать час)",
        'time_tomorrow': "📆 Завтра (выбрать час)",
        'choose_hour_from': "Время отправления (от):",
        'choose_hour_to': "Время отправления (до):",
        'location_request': "📍 Отправьте ваше местоположение (необязательно):",
        'location_btn': "📍 Отправить локацию",
        'skip_location': "⏭ Пропустить",
        'request_sent': "✅ Ваш запрос принят! Сообщим когда найдём водителя. 🚗",
        'in_queue': "⏳ Вы в очереди. Пожалуйста, подождите...",
        'cancel_request': "❌ Отменить запрос",
        'request_cancelled': "✅ Ваш запрос отменён.",
        'my_request': "📋 Мой запрос",
        'no_active_request': "ℹ️ У вас нет активного запроса.",
        'active_request_info': "📋 <b>Ваш активный запрос:</b>\n\n🗺 Направление: {direction}\n💺 Место: {seat_pos}\n👥 Человек: {seat_count}\n🕐 Время: {time_from} - {time_to}\n📊 Статус: {status}",
        'driver_found': "🚗 Водитель найден!\n\n👤 Имя: {name}\n📞 Тел: {phone}\n🚙 Авто: {car}\n🔢 Номер: {number}\n⭐ Рейтинг: {rating:.1f}\n\nВодитель свяжется с вами!",

        # История
        'history_btn': "📜 История",
        'history_empty': "📜 История поездок пуста.",
        'history_title': "📜 <b>Последние поездки:</b>\n\n",
        'history_driver_row': "🚗 <b>{direction}</b> | {seats} мест | {date}\n   Статус: {status}\n\n",
        'history_passenger_row': "🧳 <b>{direction}</b> | {date}\n   Водитель: {driver} | Статус: {status}\n\n",

        # Водитель
        'driver_menu': "🚗 Меню водителя",
        'register_driver': "📝 Зарегистрироваться как водитель",
        'car_model': "Введите модель авто (напр: Nexia 3):",
        'car_number': "Введите номер авто (напр: 30 A 123 AA):",
        'car_color': "Введите цвет авто:",
        'driver_registered': "✅ Вы зарегистрированы как водитель!",
        'announce_trip': "🚀 Объявить рейс",
        'active_trip_exists': "⚠️ У вас есть активная поездка! Сначала завершите её.",
        'choose_seats': "Сколько пассажиров берёте?",
        'trip_announced': "✅ Объявлено! Ищем подходящих пассажиров...",
        'no_passengers': "😔 Пока нет подходящих пассажиров. Сообщим когда найдём!",
        'passengers_found': "🎯 Найдено {count} пассажиров!\n\nПросмотрите каждого:",
        'passenger_card': "👤 {name}\n📞 {phone}\n💺 {seat_pos} | 👥 {seat_count} чел.\n📍 Расстояние: {dist:.1f} км\n⭐ Рейтинг: {rating:.1f}",
        'accept': "✅ Принять",
        'reject': "❌ Отказать",
        'passenger_accepted': "✅ Пассажир принят. Свяжитесь с ним!",
        'passenger_rejected': "❌ Отказано. Пассажир остался в очереди.",
        'finish_trip': "🏁 Завершить поездку",
        'no_active_trip': "ℹ️ Активная поездка не найдена.",
        'trip_finished': "✅ Поездка завершена! Запрашиваем оценку у пассажиров...",
        'my_stats': "📊 Моя статистика",
        'stats_text': "📊 <b>Статистика</b>\n\n🚗 Всего поездок: <b>{total}</b>\n📅 Сегодня: <b>{today}</b>\n⭐ Рейтинг: <b>{rating:.1f}</b> ({rating_count} оценок)",

        # Редактирование авто
        'edit_car_btn': "🚙 Изменить авто",
        'edit_car_model': "Введите новую модель авто:",
        'edit_car_number': "Введите новый номер авто:",
        'edit_car_color': "Введите новый цвет авто:",
        'car_updated': "✅ Данные автомобиля обновлены!",

        # Рейтинг
        'rate_driver': "⭐ Оцените водителя ({name}):",
        'rate_already': "Вы уже оценили эту поездку.",
        'rating_saved': "✅ Ваша оценка сохранена! Спасибо!",

        # Админ
        'admin_menu': "👑 Панель администратора",
        'not_registered': "Пожалуйста, сначала зарегистрируйтесь. /start",
        'error': "❌ Произошла ошибка. Попробуйте снова.",
        'back': "🔙 Назад",
    }
}


def t(lang: str, key: str, **kwargs) -> str:
    text = TEXTS.get(lang, TEXTS['uz']).get(key, TEXTS['uz'].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text
