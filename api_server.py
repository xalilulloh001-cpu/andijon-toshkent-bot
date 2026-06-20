"""
AndTaxi - API Server
WebApp <-> Bot orasidagi ko'prik
"""
import os, json, random, logging, asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Vaqtinchalik xotirada OTP saqlash
otp_store = {}  # {user_id: {code, phone, expires_at}}


async def send_telegram_message(chat_id: int, text: str):
    """Bot orqali Telegram xabar yuborish"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })


@app.post("/api/send-otp")
async def send_otp(request: Request):
    """
    WebApp telefon raqam kiritgandan keyin OTP yuboradi
    Body: {user_id, phone}
    """
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        phone = body.get("phone", "")

        if not user_id or not phone:
            return JSONResponse({"ok": False, "error": "user_id va phone kerak"})

        # 6 raqamli kod
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Saqlab qo'yamiz (10 daqiqa)
        otp_store[user_id] = {
            "code": code,
            "phone": phone,
            "expires_at": (datetime.now() + timedelta(minutes=10)).isoformat()
        }

        # Telegram orqali yuboramiz
        await send_telegram_message(
            user_id,
            f"🔐 *AndTaxi tasdiqlash kodi:*\n\n"
            f"`{code}`\n\n"
            f"⏰ 10 daqiqa ichida kiriting\n"
            f"❗ Kodni hech kimga bermang!"
        )

        logger.info(f"✅ OTP sent to user {user_id}")
        return JSONResponse({"ok": True, "message": "Kod Telegram-ga yuborildi"})

    except Exception as e:
        logger.error(f"send-otp error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/verify-otp")
async def verify_otp(request: Request):
    """
    WebApp kiritilgan kodni tekshiradi
    Body: {user_id, code}
    """
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        entered = str(body.get("code", "")).strip()

        stored = otp_store.get(user_id)

        if not stored:
            return JSONResponse({"ok": False, "error": "Kod topilmadi. Qayta yuboring."})

        # Vaqt tekshiruv
        expires = datetime.fromisoformat(stored["expires_at"])
        if datetime.now() > expires:
            del otp_store[user_id]
            return JSONResponse({"ok": False, "error": "Kod muddati tugadi!"})

        # Kod tekshiruv
        if entered != stored["code"]:
            return JSONResponse({"ok": False, "error": "Kod noto'g'ri!"})

        # ✅ To'g'ri
        phone = stored["phone"]
        del otp_store[user_id]

        await send_telegram_message(
            user_id,
            f"✅ *Tasdiqlandi!*\n📱 {phone} raqam bog'landi."
        )

        return JSONResponse({"ok": True, "phone": phone})

    except Exception as e:
        logger.error(f"verify-otp error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/register")
async def register(request: Request):
    """Ro'yxatdan o'tish ma'lumotlarini saqlash"""
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        role = body.get("role")
        phone = body.get("phone")

        role_text = "🚗 Haydovchi" if role == "driver" else "👤 Yo'lovchi"

        await send_telegram_message(
            user_id,
            f"🎉 *Ro'yxatdan o'tdingiz!*\n\n"
            f"Rol: {role_text}\n"
            f"Telefon: {phone}\n\n"
            f"Botdan foydalanishni boshlang 🚀"
        )

        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/sos")
async def sos_alert(request: Request):
    """SOS xabari"""
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        lat = body.get("lat")
        lng = body.get("lng")
        name = body.get("name", "Noma'lum")

        admin_ids = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
        maps_url = f"https://maps.google.com/?q={lat},{lng}"

        for admin_id in admin_ids:
            await send_telegram_message(
                admin_id,
                f"🚨 *SOS EMERGENCY!*\n\n"
                f"👤 {name} (ID: `{user_id}`)\n"
                f"📍 [Xarita]({maps_url})\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )

        await send_telegram_message(user_id, "✅ SOS adminga yuborildi!")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/health")
async def health():
    return {"ok": True, "service": "AndTaxi API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
