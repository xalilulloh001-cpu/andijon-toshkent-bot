"""
AndTaxi - Bot + API Server (bitta jarayon)
Bot polling + FastAPI bir vaqtda ishlaydi
"""
import os, json, random, logging, asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, WebAppInfo
)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN env var qo'yilmagan!")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
WEBAPP_URL = os.getenv("WEBAPP_URL",
    "https://xalilulloh001-cpu.github.io/andijon-toshkent-bot/webapp.html")
PORT = int(os.getenv("PORT", "8000"))

# Ruxsat berilgan domenlar (CORS)
ALLOWED_ORIGINS = [
    "https://xalilulloh001-cpu.github.io",
    "https://web.telegram.org",
]

# ======= BOT SETUP =======
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ======= OTP STORE (xotira) =======
otp_store = {}  # {user_id: {code, phone, expires_at}}

# ======= FSM =======
class Reg(StatesGroup):
    role     = State()
    phone    = State()
    otp      = State()
    location = State()
    extra    = State()
    done     = State()

# ======= BOT HANDLERS =======
@router.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    name = msg.from_user.first_name or "Do'st"
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚕 AndTaxi ochish",
            web_app=WebAppInfo(url=WEBAPP_URL))]
    ], resize_keyboard=True)
    await msg.answer(
        f"🚕 *Salom, {name}!*\n\n"
        f"Andijon ↔ Toshkent taxi xizmati\n\n"
        f"Quyidagi tugmani bosing 👇",
        reply_markup=kb, parse_mode="Markdown"
    )

@router.message(Command("app"))
async def cmd_app(msg: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚕 AndTaxi ochish",
            web_app=WebAppInfo(url=WEBAPP_URL))]
    ], resize_keyboard=True)
    await msg.answer("🚕 Web ilovani oching:", reply_markup=kb)

@router.message(F.web_app_data)
async def webapp_data(msg: types.Message):
    try:
        data = json.loads(msg.web_app_data.data)
        action = data.get("action", "")

        if action == "register":
            role = "🚗 Haydovchi" if data.get("role") == "driver" else "👤 Yo'lovchi"
            phone = data.get("phone", "—")
            loc = data.get("location", {})
            addr = loc.get("address", "Noma'lum")
            lat = loc.get("lat")
            lng = loc.get("lng")
            map_url = f"https://maps.google.com/?q={lat},{lng}" if lat else ""

            text = (
                f"✅ *Ro'yxatdan o'tdingiz!*\n\n"
                f"Rol: {role}\n"
                f"📱 Telefon: {phone}\n"
                f"📍 Joylashuv: {addr}\n"
            )
            if map_url:
                text += f"[Xaritada ko'rish]({map_url})\n"
            text += "\nXush kelibsiz! 🎉"

            await msg.answer(text, parse_mode="Markdown")

            # Admin-larga xabar
            for aid in ADMIN_IDS:
                try:
                    await bot.send_message(aid,
                        f"🆕 *Yangi {role}*\n"
                        f"👤 {msg.from_user.full_name} (ID: `{msg.from_user.id}`)\n"
                        f"📱 {phone}\n"
                        f"📍 {addr}" + (f"\n[Xarita]({map_url})" if map_url else ""),
                        parse_mode="Markdown")
                except Exception:
                    pass

        elif action == "join_queue":
            await msg.answer("🟢 Navbatga kirdingiz!")

        elif action == "leave_queue":
            await msg.answer("🔴 Navbatdan chiqdingiz.")

        elif action == "sos":
            lat, lng = data.get("lat"), data.get("lng")
            url = f"https://maps.google.com/?q={lat},{lng}"
            for aid in ADMIN_IDS:
                try:
                    await bot.send_message(aid,
                        f"🚨 *SOS!*\n👤 {msg.from_user.full_name}\n"
                        f"📍 [Xarita]({url})", parse_mode="Markdown")
                except Exception:
                    pass
            await msg.answer("🚨 SOS adminga yuborildi!")

    except Exception as e:
        logger.error(f"webapp_data error: {e}")

# ======= FASTAPI SETUP =======
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(dp.start_polling(bot, allowed_updates=["message","web_app_data"]))
    logger.info("🤖 Bot polling started")
    yield
    task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"])

# ======= API ENDPOINTS =======

@app.post("/api/send-otp")
async def send_otp(request: Request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id", 0))
        phone = body.get("phone", "")

        if not user_id:
            return JSONResponse({"ok": False, "error": "user_id kerak"})

        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        otp_store[user_id] = {
            "code": code,
            "phone": phone,
            "expires_at": datetime.now() + timedelta(minutes=10)
        }

        await bot.send_message(
            user_id,
            f"🔐 *AndTaxi tasdiqlash kodi:*\n\n"
            f"```\n{code}\n```\n\n"
            f"⏰ 10 daqiqa ichida kiriting\n"
            f"🔒 Kodni hech kimga bermang!",
            parse_mode="Markdown"
        )

        logger.info(f"✅ OTP yuborildi → user {user_id}")
        return JSONResponse({"ok": True})

    except Exception as e:
        logger.error(f"send-otp error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/verify-otp")
async def verify_otp(request: Request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id", 0))
        entered = str(body.get("code", "")).strip()

        stored = otp_store.get(user_id)
        if not stored:
            return JSONResponse({"ok": False, "error": "Avval kod yuboring"})

        if datetime.now() > stored["expires_at"]:
            del otp_store[user_id]
            return JSONResponse({"ok": False, "error": "Kod muddati tugadi!"})

        if entered != stored["code"]:
            return JSONResponse({"ok": False, "error": "Kod noto'g'ri!"})

        phone = stored["phone"]
        del otp_store[user_id]

        await bot.send_message(
            user_id,
            f"✅ *Telefon tasdiqlandi!*\n📱 {phone}",
            parse_mode="Markdown"
        )
        return JSONResponse({"ok": True, "phone": phone})

    except Exception as e:
        logger.error(f"verify-otp error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/register")
async def register(request: Request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id", 0))
        role = body.get("role", "")
        phone = body.get("phone", "")
        role_txt = "🚗 Haydovchi" if role == "driver" else "👤 Yo'lovchi"

        await bot.send_message(
            user_id,
            f"🎉 *Ro'yxatdan o'tdingiz!*\n\n"
            f"Rol: {role_txt}\nTelefon: {phone}",
            parse_mode="Markdown"
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/sos")
async def sos(request: Request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id", 0))
        lat = body.get("lat")
        lng = body.get("lng")
        name = body.get("name", "Noma'lum")
        url = f"https://maps.google.com/?q={lat},{lng}"

        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid,
                    f"🚨 *SOS!*\n👤 {name}\n📍 [Xarita]({url})",
                    parse_mode="Markdown")
            except Exception:
                pass

        await bot.send_message(user_id, "✅ SOS adminga yuborildi!")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/health")
async def health():
    return {"ok": True, "bot": "running", "api": "running"}


# ======= ISHGA TUSHIRISH =======
if __name__ == "__main__":
    logger.info(f"🚀 AndTaxi starting on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

