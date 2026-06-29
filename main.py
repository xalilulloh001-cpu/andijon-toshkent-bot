"""
AndTaxi - Bot + API Server
Bot polling + FastAPI bitta jarayonda
"""
import os, json, logging, asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

from database import db

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN env var qo'yilmagan!")

ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS","0").split(",") if x.strip().isdigit()]
WEBAPP_URL = os.getenv("WEBAPP_URL",
    "https://xalilulloh001-cpu.github.io/andijon-toshkent-bot/webapp.html")
PORT       = int(os.getenv("PORT","8000"))
API_BASE   = os.getenv("RAILWAY_PUBLIC_DOMAIN",
    "andijon-toshkent-bot-production.up.railway.app")

ALLOWED_ORIGINS = [
    "https://xalilulloh001-cpu.github.io",
    "https://web.telegram.org",
    "null",  # local test
]

bot    = Bot(token=BOT_TOKEN)
dp     = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ───────────────────────────────────────────
# BOT HANDLERS
# ───────────────────────────────────────────

def webapp_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚕 AndTaxi ochish",
            web_app=WebAppInfo(url=WEBAPP_URL))]
    ], resize_keyboard=True)


@router.message(Command("start"))
async def cmd_start(msg: types.Message):
    user_id = msg.from_user.id
    name    = msg.from_user.first_name or "Do'st"

    # DB dan foydalanuvchini olish
    user = await db.get_user(user_id)

    if user and user.get("registered"):
        role_txt = "🚗 Haydovchi" if user["role"] == "driver" else "👤 Yo'lovchi"
        # Aktiv trip bormi?
        trip = await db.get_active_trip(user_id)
        if trip:
            await msg.answer(
                f"Salom, {name}! Sizning aktiv tripingiz bor.\n"
                f"Ilovani oching 👇",
                reply_markup=webapp_kb()
            )
        else:
            await msg.answer(
                f"Salom, {name}! Siz {role_txt} sifatida ro'yxatdasiz.\n"
                f"Ilovani oching 👇",
                reply_markup=webapp_kb()
            )
    else:
        await msg.answer(
            f"🚕 *Salom, {name}!*\n\n"
            f"Andijon ↔ Toshkent taxi xizmati\n\n"
            f"Ro'yxatdan o'tish va taksi chaqirish uchun ilovani oching 👇",
            reply_markup=webapp_kb(), parse_mode="Markdown"
        )


@router.message(F.web_app_data)
async def on_webapp_data(msg: types.Message):
    """WebApp'dan kelgan barcha ma'lumotlar shu yerda"""
    try:
        data    = json.loads(msg.web_app_data.data)
        action  = data.get("action", "")
        user_id = msg.from_user.id
        name    = msg.from_user.first_name or "Foydalanuvchi"
        logger.info(f"WebApp action={action} user={user_id}")

        # ─── RO'YXATDAN O'TISH ───
        if action == "register":
            role       = data.get("role", "passenger")
            phone      = data.get("phone", "")
            loc        = data.get("location", {})
            seat_pref  = data.get("seat_pref")
            seat_count = data.get("seat_count")
            car_model  = data.get("car_model", "")
            car_plate  = data.get("car_plate", "")

            await db.save_user(
                user_id,
                name       = name,
                phone      = phone,
                role       = role,
                seat_pref  = seat_pref,
                seat_count = seat_count,
                car_model  = car_model,
                car_plate  = car_plate,
                loc_lat    = loc.get("lat"),
                loc_lng    = loc.get("lng"),
                loc_addr   = loc.get("address",""),
                registered = True,
                is_active  = True,
            )

            role_txt = "🚗 Haydovchi" if role == "driver" else "👤 Yo'lovchi"
            await msg.answer(
                f"✅ *Ro'yxatdan o'tdingiz!*\n"
                f"Rol: {role_txt}\nTelefon: {phone}\n\n"
                f"Ilovani oching 👇",
                reply_markup=webapp_kb(), parse_mode="Markdown"
            )

            for aid in ADMIN_IDS:
                try:
                    await bot.send_message(aid,
                        f"🆕 *Yangi {role_txt}*\n"
                        f"👤 {name} | `{user_id}`\n📱 {phone}",
                        parse_mode="Markdown")
                except Exception:
                    pass

        # ─── TAKSI CHAQIRISH (YO'LOVCHI) ───
        elif action == "call_taxi":
            loc  = data.get("location", {})
            lat  = loc.get("lat")
            lng  = loc.get("lng")
            addr = loc.get("address", "Noma'lum")

            trip_id = await db.create_trip(user_id, lat, lng, addr)
            if not trip_id:
                await msg.answer("❌ Trip yaratishda xato. Qayta urining.")
                return

            await msg.answer(
                f"🔍 *Haydovchi qidirilmoqda...*\n\n"
                f"📍 {addr}\n\n"
                f"Haydovchi topilgach xabar beramiz! "
                f"Ilovada jarayonni ko'rishingiz mumkin.",
                parse_mode="Markdown"
            )

            for aid in ADMIN_IDS:
                try:
                    map_url = f"https://maps.google.com/?q={lat},{lng}"
                    await bot.send_message(aid,
                        f"🚕 *Yangi buyurtma #{trip_id}*\n"
                        f"👤 {name} | `{user_id}`\n"
                        f"📍 [{addr}]({map_url})",
                        parse_mode="Markdown")
                except Exception:
                    pass

        # ─── LOKATSIYA YANGILASH ───
        elif action == "update_location":
            loc = data.get("location", {})
            await db.save_user(
                user_id,
                loc_lat  = loc.get("lat"),
                loc_lng  = loc.get("lng"),
                loc_addr = loc.get("address",""),
            )

        # ─── BAHO BERISH ───
        elif action == "rate_driver":
            trip_id = data.get("trip_id")
            rating  = data.get("rating")
            comment = data.get("comment","")

            if trip_id and rating:
                await db.update_trip(trip_id,
                    rating=rating,
                    rating_comment=comment,
                    status="completed",
                    completed_at=datetime.now()
                )
                trip = await db.get_trip(trip_id)
                if trip and trip.get("driver_id"):
                    try:
                        await bot.send_message(
                            trip["driver_id"],
                            f"⭐ *Yangi baho!*\n"
                            f"{'⭐'*rating} ({rating}/5)\n"
                            f"{comment or ''}",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
            await msg.answer("✅ Bahoingiz uchun rahmat!")

        # ─── TRIP BEKOR QILISH ───
        elif action == "cancel_trip":
            trip_id = data.get("trip_id")
            if trip_id:
                await db.update_trip(trip_id, status="cancelled")
                await msg.answer("❌ Trip bekor qilindi.")

    except Exception as e:
        logger.error(f"webapp_data error: {e}", exc_info=True)


# ───────────────────────────────────────────
# FASTAPI SETUP
# ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=["message","web_app_data"])
    )
    logger.info("🤖 Bot polling started")
    yield
    task.cancel()
    await db.close()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET","POST","OPTIONS"],
    allow_headers=["Content-Type","Authorization"])


# ───────────────────────────────────────────
# API ENDPOINTS
# ───────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.now().isoformat()}


@app.post("/api/user")
async def get_user(request: Request):
    """WebApp ochilganda foydalanuvchi ma'lumotini olish"""
    try:
        body    = await request.json()
        user_id = int(body.get("user_id", 0))
        if not user_id:
            return JSONResponse({"ok": False, "error": "user_id kerak"})

        user = await db.get_user(user_id)
        trip = await db.get_active_trip(user_id)

        return JSONResponse({
            "ok":   True,
            "user": user,
            "trip": trip,
        })
    except Exception as e:
        logger.error(f"/api/user error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})



@app.post("/api/register")
async def api_register(request: Request):
    """
    WebApp to'g'ridan DB ga yozadi — tg.sendData race condition muammosi yo'q.
    """
    try:
        body       = await request.json()
        user_id    = int(body.get("user_id", 0))
        if not user_id:
            return JSONResponse({"ok": False, "error": "user_id kerak"})

        name       = body.get("name", "Foydalanuvchi")
        role       = body.get("role", "passenger")
        phone      = body.get("phone", "")
        loc        = body.get("location", {})
        seat_pref  = body.get("seat_pref")
        seat_count = body.get("seat_count")
        car_model  = body.get("car_model", "")
        car_plate  = body.get("car_plate", "")

        await db.save_user(
            user_id,
            name       = name,
            phone      = phone,
            role       = role,
            seat_pref  = seat_pref,
            seat_count = seat_count,
            car_model  = car_model,
            car_plate  = car_plate,
            loc_lat    = loc.get("lat"),
            loc_lng    = loc.get("lng"),
            loc_addr   = loc.get("address", ""),
            registered = True,
            is_active  = True,
        )

        role_txt = "🚗 Haydovchi" if role == "driver" else "👤 Yo'lovchi"
        logger.info(f"Registered: {role_txt} user={user_id}")

        # Bot orqali xabar (ixtiyoriy — xato bo'lsa ham ok qaytaramiz)
        try:
            await bot.send_message(
                user_id,
                f"✅ *{role_txt} sifatida ro'yxatdan o'tdingiz!*\n"
                f"📱 {phone}\n\nIlovani oching 👇",
                reply_markup=webapp_kb(), parse_mode="Markdown"
            )
        except Exception:
            pass

        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid,
                    f"🆕 *{role_txt}*\n👤 {name} `{user_id}`\n📱 {phone}",
                    parse_mode="Markdown")
            except Exception:
                pass

        return JSONResponse({"ok": True, "role": role})
    except Exception as e:
        logger.error(f"/api/register: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/call-taxi")
async def call_taxi(request: Request):
    """Yo'lovchi taksi chaqiradi"""
    try:
        body    = await request.json()
        user_id = int(body.get("user_id", 0))
        loc     = body.get("location", {})

        user = await db.get_user(user_id)
        if not user or not user.get("registered"):
            return JSONResponse({"ok": False, "error": "Avval ro'yxatdan o'ting"})

        # Aktiv trip bormi?
        existing = await db.get_active_trip(user_id)
        if existing:
            return JSONResponse({"ok": True, "trip_id": existing["id"],
                                 "status": existing["status"]})

        trip_id = await db.create_trip(
            user_id,
            loc.get("lat"), loc.get("lng"), loc.get("address","")
        )

        # Haydovchilarga xabar yuborish
        drivers = await db.get_available_drivers()
        map_url = f"https://maps.google.com/?q={loc.get('lat')},{loc.get('lng')}"
        for driver in drivers[:5]:
            try:
                await bot.send_message(
                    driver["user_id"],
                    f"🚕 *Yangi yo'lovchi!*\n"
                    f"📍 [{loc.get('address','Manzil')}]({map_url})\n"
                    f"Ilovada qabul qiling 👇",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        return JSONResponse({"ok": True, "trip_id": trip_id, "status": "searching"})
    except Exception as e:
        logger.error(f"/api/call-taxi error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/accept-trip")
async def accept_trip(request: Request):
    """Haydovchi tripni qabul qiladi"""
    try:
        body      = await request.json()
        driver_id = int(body.get("driver_id", 0))
        trip_id   = int(body.get("trip_id", 0))

        trip = await db.get_trip(trip_id)
        if not trip:
            return JSONResponse({"ok": False, "error": "Trip topilmadi"})
        if trip["status"] != "searching":
            return JSONResponse({"ok": False, "error": "Trip allaqachon olingan"})

        await db.update_trip(trip_id,
            driver_id  = driver_id,
            status     = "matched",
            matched_at = datetime.now()
        )

        driver = await db.get_user(driver_id)
        driver_name = driver.get("name","Haydovchi") if driver else "Haydovchi"
        car = f"{driver.get('car_model','')} {driver.get('car_plate','')}".strip() if driver else ""

        # Yo'lovchiga xabar
        try:
            await bot.send_message(
                trip["passenger_id"],
                f"✅ *Haydovchi topildi!*\n\n"
                f"👤 {driver_name}\n"
                f"🚗 {car or 'Mashina'}\n\n"
                f"Ilovada kuzatishingiz mumkin 👇",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"/api/accept-trip error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/trip-status")
async def trip_status(request: Request):
    """Trip holatini yangilash: started | completed"""
    try:
        body      = await request.json()
        trip_id   = int(body.get("trip_id", 0))
        status    = body.get("status", "")
        driver_id = int(body.get("driver_id", 0))

        if status not in ("started","completed","cancelled"):
            return JSONResponse({"ok": False, "error": "Noto'g'ri status"})

        kwargs = {"status": status}
        if status == "started":
            kwargs["started_at"] = datetime.now()
        elif status == "completed":
            kwargs["completed_at"] = datetime.now()

        await db.update_trip(trip_id, **kwargs)
        trip = await db.get_trip(trip_id)
        if not trip:
            return JSONResponse({"ok": False, "error": "Trip topilmadi"})

        # Yo'lovchiga xabar
        try:
            if status == "started":
                await bot.send_message(trip["passenger_id"],
                    "🚗 *Trip boshlandi!* Haydovchi yo'lda.",
                    parse_mode="Markdown")
            elif status == "completed":
                await bot.send_message(trip["passenger_id"],
                    "🎉 *Manzilga yetib keldingiz!*\n"
                    "Haydovchiga baho bering — ilovani oching 👇",
                    parse_mode="Markdown")
            elif status == "cancelled":
                await bot.send_message(trip["passenger_id"],
                    "❌ Trip bekor qilindi.")
        except Exception:
            pass

        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"/api/trip-status error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/rate")
async def rate_trip(request: Request):
    """Yo'lovchi haydovchiga baho beradi"""
    try:
        body    = await request.json()
        trip_id = int(body.get("trip_id", 0))
        rating  = int(body.get("rating", 0))
        comment = body.get("comment", "")

        if not 1 <= rating <= 5:
            return JSONResponse({"ok": False, "error": "Baho 1-5 oralig'ida bo'lishi kerak"})

        trip = await db.get_trip(trip_id)
        if not trip:
            return JSONResponse({"ok": False, "error": "Trip topilmadi"})

        await db.update_trip(trip_id,
            rating         = rating,
            rating_comment = comment,
            status         = "completed",
            completed_at   = datetime.now()
        )

        if trip.get("driver_id"):
            try:
                await bot.send_message(
                    trip["driver_id"],
                    f"⭐ *Yangi baho!*\n{'⭐'*rating} ({rating}/5)\n{comment}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"/api/rate error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/api/trips/searching")
async def searching_trips():
    """Haydovchi uchun: barcha kutayotgan triplar"""
    try:
        trips = await db.get_searching_trips()
        return JSONResponse({"ok": True, "trips": trips})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ───────────────────────────────────────────
# ISHGA TUSHIRISH
# ───────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"🚀 AndTaxi port={PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
