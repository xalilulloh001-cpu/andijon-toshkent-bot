# 🚖 Andijon-Toshkent Taksi Bot

Andijon ↔ Toshkent yo'nalishida yo'lovchi va haydovchilarni bog'lovchi Telegram bot.

## 🚀 O'rnatish

### 1. .env fayl yaratish
```bash
cp .env.example .env
```
`.env` faylni tahrirlang:
```
BOT_TOKEN=your_bot_token
DATABASE_URL=postgresql://taxibot:taxibot123@db:5432/taxibot
ADMIN_IDS=your_telegram_id
```

### 2. Docker bilan ishga tushirish
```bash
docker-compose up -d
```

### 3. Yoki oddiy Python bilan
```bash
pip install -r requirements.txt
python bot.py
```

## 📋 Funksiyalar

### Yo'lovchi uchun:
- ✅ Yo'nalish tanlash (Andijon↔Toshkent)
- ✅ O'tirish joyi (Oldi/Orqa)
- ✅ Nechta kishi (1/2/3)
- ✅ Vaqt oralig'i belgilash
- ✅ Lokatsiya yuborish
- ✅ Haydovchi topilganda bildirishnoma
- ✅ So'rovni bekor qilish
- ✅ Haydovchiga reyting berish

### Haydovchi uchun:
- ✅ Mashina ro'yxatdan o'tkazish
- ✅ Yo'nalish e'lon qilish
- ✅ Nechta yo'lovchi olishini belgilash
- ✅ Vaqt belgilash
- ✅ Bot avtomatik yo'lovchilarni topib beradi
- ✅ Har birini Qabul/Rad qilish
- ✅ Safarni yakunlash
- ✅ Statistika ko'rish

### Admin uchun:
- ✅ /admin - admin paneli
- ✅ Statistika
- ✅ Barcha foydalanuvchilarga xabar yuborish
- ✅ Foydalanuvchi bloklash/blokdan chiqarish

## 🤖 Matching Algoritmi

1. **Vaqt**: Haydovchi vaqti ±2 soat ichidagi yo'lovchilar
2. **1-qadam**: Bir xil yo'nalish, eng yaqin yo'lovchilar
3. **2-qadam**: Yetarli emas → Yo'l bo'ylab uzoqroq yo'lovchilar
4. **3-qadam**: Baribir yetarli emas → Qarama-qarshi yo'nalish, yo'l ustidagi yo'lovchilar

## 📞 Yordam

Bot muallifi: [@your_username](https://t.me/your_username)
