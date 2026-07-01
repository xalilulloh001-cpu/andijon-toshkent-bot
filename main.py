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
    "andijon-toshkent-bot2-production.up.railway.app")

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
            phone_raw  = data.get("phone", "")
            loc        = data.get("location", {})
            seat_pref  = data.get("seat_pref")
            seat_count = data.get("seat_count")
            car_model  = data.get("car_model", "")
            car_plate  = data.get("car_plate", "")

            phone = db.normalize_phone(phone_raw)
            if not phone:
                await msg.answer("❌ Telefon raqami noto'g'ri. Masalan: +998901234567")
                return

            is_banned, ban_info = await db.check_if_banned(user_id)
            if is_banned:
                reason = ban_info.get("reason", "sabab ko'rsatilmagan") if ban_info else ""
                await msg.answer(f"🚫 Hisobingiz bloklangan: {reason}")
                return

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

            is_banned, ban_info = await db.check_if_banned(user_id)
            if is_banned:
                reason = ban_info.get("reason", "sabab ko'rsatilmagan") if ban_info else ""
                await msg.answer(f"🚫 Hisobingiz bloklangan: {reason}")
                return

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

            # FIX: birinchi 5 ta emas — ENG YAQIN haydovchilarga xabar beriladi
            nearby = await db.get_nearby_drivers(lat, lng, limit=5)
            for driver in nearby:
                try:
                    map_url = f"https://maps.google.com/?q={lat},{lng}"
                    await bot.send_message(driver["user_id"],
                        f"🚕 *Yangi buyurtma #{trip_id}* ({driver['_distance_km']} km)\n"
                        f"👤 {name} | `{user_id}`\n"
                        f"📍 [{addr}]({map_url})",
                        parse_mode="Markdown")
                except Exception:
                    pass

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
        phone_raw  = body.get("phone", "")
        loc        = body.get("location", {})
        seat_pref  = body.get("seat_pref")
        seat_count = body.get("seat_count")
        car_model  = body.get("car_model", "")
        car_plate  = body.get("car_plate", "")

        # FIX: telefon raqamini tekshirish — noto'g'ri format qabul qilinmaydi
        phone = db.normalize_phone(phone_raw)
        if not phone:
            return JSONResponse({"ok": False, "error": "Telefon raqami noto'g'ri. Masalan: +998901234567"})

        # FIX: bloklangan foydalanuvchi ro'yxatdan o'ta olmaydi
        is_banned, ban_info = await db.check_if_banned(user_id)
        if is_banned:
            reason = ban_info.get("reason", "sabab ko'rsatilmagan") if ban_info else ""
            return JSONResponse({"ok": False, "error": f"Hisobingiz bloklangan: {reason}"})

        ok = await db.save_user(
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
        if not ok:
            logger.error(f"/api/register: save_user FAILED user_id={user_id}")
            return JSONResponse({"ok": False, "error": "DB xato, qayta urining"})
        logger.info(f"Registered OK: {role_txt} user={user_id}")

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
    """
    Yo'lovchi taksi chaqiradi.
    YANGI: yo'lovchi ENG YAQIN, navbatda turgan haydovchining, o'zi
    tanlagan o'rindiq turiga (old/orqa) mos guruhiga avtomatik qo'shiladi.
    Agar old o'rindiq xohlab, hech qayerda old bo'sh bo'lmasa — orqa
    o'rindiq taklif qilinadi (need_confirm=true), yo'lovchi rozi bo'lsa
    group_id + accept_fallback=true bilan qayta so'rov yuboradi.
    """
    try:
        body            = await request.json()
        user_id         = int(body.get("user_id", 0))
        loc             = body.get("location", {})
        accept_fallback = bool(body.get("accept_fallback", False))
        fallback_group  = body.get("group_id")

        user = await db.get_user(user_id)
        if not user:
            logger.warning(f"/api/call-taxi: user topilmadi user_id={user_id}")
            return JSONResponse({"ok": False, "error": "Foydalanuvchi topilmadi, qayta kiring"})
        if not user.get("registered"):
            logger.warning(f"/api/call-taxi: registered=False user_id={user_id} user={dict(user)}")
            return JSONResponse({"ok": False, "error": "Ro'yxat tugallanmagan, ilovani yopib qayta oching"})

        is_banned, ban_info = await db.check_if_banned(user_id)
        if is_banned:
            reason = ban_info.get("reason", "sabab ko'rsatilmagan") if ban_info else ""
            return JSONResponse({"ok": False, "error": f"Hisobingiz bloklangan: {reason}"})

        existing = await db.get_active_trip(user_id)
        if existing:
            return JSONResponse({"ok": True, "trip_id": existing["id"],
                                 "status": existing["status"]})

        lat, lng, addr = loc.get("lat"), loc.get("lng"), loc.get("address", "")
        seat_pref = user.get("seat_pref") or "back"

        async def do_join(group_id, seat_type):
            result = await db.join_group_atomic(group_id, user_id, lat, lng, addr, seat_type)
            if result:
                map_url = f"https://maps.google.com/?q={lat},{lng}"
                try:
                    await bot.send_message(
                        result["driver_id"],
                        f"🚕 *Yangi yo'lovchi qo'shildi!* ({result['taken_seats']}/{result['total_seats']})\n"
                        f"📍 [{addr or 'Manzil'}]({map_url})",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            return result

        # Yo'lovchi orqa o'rindiqni taklifga rozi bo'ldi
        if accept_fallback and fallback_group:
            result = await do_join(int(fallback_group), "back")
            if not result:
                return JSONResponse({"ok": False, "error": "Bu joy allaqachon band bo'ldi, qayta urining"})
            return JSONResponse({"ok": True, "trip_id": result["trip_id"], "status": "matched"})

        group = await db.find_nearest_group_with_space(lat, lng, seat_pref)
        if not group:
            return JSONResponse({"ok": False,
                "error": "Hozircha navbatda haydovchi yo'q. Birozdan so'ng qayta urinib ko'ring."})

        if group.get("_is_fallback"):
            # Old o'rindiq hech qayerda bo'sh emas — orqa o'rindiqni taklif qilamiz
            return JSONResponse({
                "ok": True, "need_confirm": True, "fallback_seat": "back",
                "group_id": group["id"], "driver_name": group.get("driver_name"),
                "distance_km": group.get("_distance_km"),
            })

        result = await do_join(group["id"], seat_pref)
        if not result:
            # Boshqa yo'lovchi bir zumda oldi — qayta izlaymiz
            group2 = await db.find_nearest_group_with_space(lat, lng, seat_pref)
            if group2 and not group2.get("_is_fallback"):
                result = await do_join(group2["id"], seat_pref)
        if not result:
            return JSONResponse({"ok": False, "error": "Bo'sh joy topilmadi, qayta urining"})

        return JSONResponse({"ok": True, "trip_id": result["trip_id"], "status": "matched"})
    except Exception as e:
        logger.error(f"/api/call-taxi error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/driver/join-queue")
async def driver_join_queue(request: Request):
    """
    YANGI: Haydovchi 'Navbatga qo'shilish' tugmasini bosganda chaqiriladi.
    Har safar YANGI GPS joylashuvi VA yangi o'rindiq sozlamasi
    (old bormi, orqada nechta) olinadi — ro'yxatdan o'tishdagi eski
    songa tayanilmaydi.
    """
    try:
        body            = await request.json()
        driver_id       = int(body.get("driver_id", 0))
        loc             = body.get("location", {})
        lat, lng        = loc.get("lat"), loc.get("lng")
        front_available = bool(body.get("front_available", False))
        back_seats      = int(body.get("back_seats", 0))
        if lat is None or lng is None:
            return JSONResponse({"ok": False, "error": "Joylashuv kerak"})
        if not front_available and back_seats <= 0:
            return JSONResponse({"ok": False, "error": "Kamida bitta o'rindiq belgilang"})

        is_banned, ban_info = await db.check_if_banned(driver_id)
        if is_banned:
            reason = ban_info.get("reason", "sabab ko'rsatilmagan") if ban_info else ""
            return JSONResponse({"ok": False, "error": f"Hisobingiz bloklangan: {reason}"})

        group = await db.join_queue(driver_id, lat, lng, front_available, back_seats)
        if not group:
            return JSONResponse({"ok": False, "error": "Navbatga qo'shilishda xato"})
        return JSONResponse({"ok": True, "group": group})
    except Exception as e:
        logger.error(f"/api/driver/join-queue error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/api/driver/group")
async def driver_group(driver_id: int):
    """Haydovchining joriy guruh holati (necha yo'lovchi qo'shilgani)"""
    try:
        group = await db.get_driver_active_group(driver_id)
        if not group:
            return JSONResponse({"ok": True, "group": None, "members": []})
        members = await db.get_group_members(group["id"])
        return JSONResponse({"ok": True, "group": group, "members": members})
    except Exception as e:
        logger.error(f"/api/driver/group error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/driver/start-group")
async def driver_start_group(request: Request):
    """Haydovchi 'Yo'lga chiqamiz!' bosganda — guruhdagi barcha yo'lovchilar uchun trip boshlanadi"""
    try:
        body      = await request.json()
        driver_id = int(body.get("driver_id", 0))
        group = await db.start_group(driver_id)
        if not group:
            return JSONResponse({"ok": False, "error": "Faol guruh topilmadi"})

        members = await db.get_group_members(group["id"])
        for m in members:
            try:
                await bot.send_message(m["passenger_id"],
                    "🚗 *Trip boshlandi!* Haydovchi yo'lda.", parse_mode="Markdown")
            except Exception:
                pass
        return JSONResponse({"ok": True, "group": group})
    except Exception as e:
        logger.error(f"/api/driver/start-group error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/driver/finish-group")
async def driver_finish_group(request: Request):
    """
    Haydovchi 'Safar tugadi!' bosganda — barcha yo'lovchilar uchun trip
    yakunlanadi VA haydovchi AVTOMATIK navbatdan chiqariladi (is_online=false).
    Qayta yo'lovchi olish uchun yana 'Navbatga qo'shilish' bosishi kerak.
    """
    try:
        body      = await request.json()
        driver_id = int(body.get("driver_id", 0))
        group = await db.finish_group(driver_id)
        if not group:
            return JSONResponse({"ok": False, "error": "Faol guruh topilmadi"})

        members = await db.get_group_members(group["id"])
        for m in members:
            try:
                await bot.send_message(m["passenger_id"],
                    "🎉 *Manzilga yetib keldingiz!*\nHaydovchiga baho bering — ilovani oching 👇",
                    parse_mode="Markdown")
            except Exception:
                pass
        return JSONResponse({"ok": True, "group": group})
    except Exception as e:
        logger.error(f"/api/driver/finish-group error: {e}")
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

        # FIX: RACE CONDITION oldini olish — tekshirish va yozish BITTA
        # atomic so'rovda bajariladi. Agar boshqa haydovchi bir zumda oldinroq
        # olgan bo'lsa, bu False qaytaradi va hech qanday xabar yubormaydi.
        won = await db.accept_trip_atomic(trip_id, driver_id)
        if not won:
            return JSONResponse({"ok": False, "error": "Afsuski, bu buyurtmani boshqa haydovchi allaqachon oldi"})

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
