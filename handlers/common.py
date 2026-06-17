from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart

import database as db
from keyboards import (
    lang_keyboard, role_keyboard, contact_keyboard,
    passenger_menu_keyboard, driver_menu_keyboard, settings_keyboard
)
from texts import t

router = Router()


class RegisterStates(StatesGroup):
    choosing_lang = State()
    entering_name = State()
    sending_contact = State()
    choosing_role = State()


async def get_lang(user_id):
    user = await db.get_user(user_id)
    return user['lang'] if user else 'uz'


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)

    if user and not user['is_blocked']:
        lang = user['lang']
        if user['role'] == 'driver':
            await message.answer(t(lang, 'driver_menu'), reply_markup=driver_menu_keyboard(lang))
        else:
            await message.answer(t(lang, 'main_menu'), reply_markup=passenger_menu_keyboard(lang))
        return

    await state.set_state(RegisterStates.choosing_lang)
    await message.answer(t('uz', 'start'), reply_markup=lang_keyboard())


@router.callback_query(F.data.startswith("lang_"))
async def choose_lang(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    current_state = await state.get_state()

    if current_state == RegisterStates.choosing_lang:
        await state.update_data(lang=lang)
        await state.set_state(RegisterStates.entering_name)
        await callback.message.edit_text(t(lang, 'name_request'))
    else:
        await db.set_user_lang(callback.from_user.id, lang)
        await callback.message.edit_text(t(lang, 'lang_set'))


@router.message(RegisterStates.entering_name)
async def enter_name(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await state.update_data(name=message.text)
    await state.set_state(RegisterStates.sending_contact)
    await message.answer(t(lang, 'contact_request'), reply_markup=contact_keyboard(lang))


@router.message(RegisterStates.sending_contact, F.contact)
async def receive_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    phone = message.contact.phone_number
    name = data.get('name', message.from_user.full_name)

    await db.create_user(message.from_user.id, name, phone, lang)
    await state.update_data(phone=phone)
    await state.set_state(RegisterStates.choosing_role)
    await message.answer(t(lang, 'choose_role'), reply_markup=role_keyboard(lang))


@router.callback_query(F.data.startswith("role_"))
async def choose_role(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang') or await get_lang(callback.from_user.id)
    role = callback.data.split("_")[1]

    await db.set_user_role(callback.from_user.id, role)
    await state.clear()

    if role == 'driver':
        from keyboards import driver_menu_keyboard
        from texts import t as txt
        await callback.message.edit_text(t(lang, 'registered'))
        await callback.message.answer(
            t(lang, 'register_driver'),
            reply_markup=driver_menu_keyboard(lang)
        )
    else:
        await callback.message.edit_text(t(lang, 'registered'))
        await callback.message.answer(
            t(lang, 'main_menu'),
            reply_markup=passenger_menu_keyboard(lang)
        )


# Sozlamalar
@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки"]))
async def settings(message: Message):
    lang = await get_lang(message.from_user.id)
    await message.answer("⚙️ Sozlamalar" if lang == 'uz' else "⚙️ Настройки",
                         reply_markup=settings_keyboard(lang))


@router.callback_query(F.data == "switch_lang")
async def switch_lang(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    new_lang = 'ru' if lang == 'uz' else 'uz'
    await db.set_user_lang(callback.from_user.id, new_lang)

    user = await db.get_user(callback.from_user.id)
    if user['role'] == 'driver':
        kb = driver_menu_keyboard(new_lang)
    else:
        kb = passenger_menu_keyboard(new_lang)

    await callback.message.edit_text(t(new_lang, 'lang_set'))
    await callback.message.answer(
        t(new_lang, 'driver_menu' if user['role'] == 'driver' else 'main_menu'),
        reply_markup=kb
    )


@router.callback_query(F.data == "change_role")
async def change_role(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    await state.set_state(RegisterStates.choosing_role)
    await callback.message.edit_text(t(lang, 'choose_role'), reply_markup=role_keyboard(lang))
