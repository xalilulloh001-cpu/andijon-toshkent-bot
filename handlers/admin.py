from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import os

import database as db
from keyboards import admin_menu_keyboard
from texts import t

router = Router()

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class AdminStates(StatesGroup):
    broadcasting = State()
    blocking = State()
    unblocking = State()


@router.message(F.text == "/admin")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 Admin paneli", reply_markup=admin_menu_keyboard())


@router.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    users = await db.get_all_users_count()
    drivers = await db.get_all_drivers_count()
    trips = await db.get_all_trips_count()
    await message.answer(
        f"📊 <b>Bot Statistikasi</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{users}</b>\n"
        f"🚗 Faol haydovchilar: <b>{drivers}</b>\n"
        f"✅ Tugallangan safarlar: <b>{trips}</b>",
        parse_mode="HTML"
    )


@router.message(F.text == "📢 Broadcast")
async def start_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.broadcasting)
    await message.answer("Yubormoqchi bo'lgan xabaringizni kiriting:")


@router.message(AdminStates.broadcasting)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_ids = await db.get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, message.text)
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.")


@router.message(F.text == "🚫 Block user")
async def start_block(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.blocking)
    await message.answer("Bloklash uchun foydalanuvchi ID ni kiriting:")


@router.message(AdminStates.blocking)
async def do_block(message: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int(message.text.strip())
        await db.block_user(uid)
        await message.answer(f"✅ Foydalanuvchi {uid} bloklandi.")
    except ValueError:
        await message.answer("❌ Noto'g'ri ID.")


@router.message(F.text == "✅ Unblock user")
async def start_unblock(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.unblocking)
    await message.answer("Blokdan chiqarish uchun foydalanuvchi ID ni kiriting:")


@router.message(AdminStates.unblocking)
async def do_unblock(message: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int(message.text.strip())
        await db.unblock_user(uid)
        await message.answer(f"✅ Foydalanuvchi {uid} blokdan chiqarildi.")
    except ValueError:
        await message.answer("❌ Noto'g'ri ID.")
