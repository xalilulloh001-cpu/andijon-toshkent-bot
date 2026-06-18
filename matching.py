import math
from typing import List, Dict, Any

ROUTE_POINTS = [
    {"name": "Andijon",    "lat": 40.7821, "lng": 72.3442},
    {"name": "Asaka",      "lat": 40.6397, "lng": 72.2356},
    {"name": "Namangan",   "lat": 40.9983, "lng": 71.6726},
    {"name": "Qo'qon",    "lat": 40.5283, "lng": 70.9422},
    {"name": "Marg'ilon", "lat": 40.4736, "lng": 71.7225},
    {"name": "Farg'ona",  "lat": 40.3842, "lng": 71.7843},
    {"name": "Sirdaryo",   "lat": 40.8393, "lng": 68.6643},
    {"name": "Guliston",   "lat": 40.4897, "lng": 68.7842},
    {"name": "Yangiyo'l", "lat": 41.1097, "lng": 69.0500},
    {"name": "Ohangaron",  "lat": 41.0828, "lng": 69.6397},
    {"name": "Angren",     "lat": 41.0169, "lng": 70.1444},
    {"name": "Toshkent",   "lat": 41.2995, "lng": 69.2401},
]

# Har bir mashina turi uchun o'rindiq cheklovi
# front = oldi o'rindiq (har doim 1 ta)
# back  = orqa o'rindiq (seats_total - 1)
SEAT_LIMITS = {
    "front": 1,   # Oldi o'rindiq — faqat 1 ta joy
    "back": None, # Orqa — haydovchi e'lon qilgan seats - 1
}


def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_on_route(lat, lng, max_km=30) -> bool:
    return any(haversine(lat, lng, p["lat"], p["lng"]) <= max_km for p in ROUTE_POINTS)


def get_seat_capacity(seat_position: str, total_seats: int) -> int:
    """
    O'rindiq joyi bo'yicha nechta odam o'tira olishini qaytaradi.

    front → har doim 1
    back  → total_seats - 1  (masalan: 4 o'rinli mashina = 3 orqa joy)
    """
    if seat_position == "front":
        return 1
    return max(1, total_seats - 1)


def count_booked_seats(passengers: List[Dict], seat_position: str) -> int:
    """
    Berilgan o'rindiq turida allaqachon band qilingan joylar sonini hisoblaydi.
    Har bir yo'lovchining seat_count si ham hisobga olinadi.
    """
    total = 0
    for p in passengers:
        if p.get("seat_position") == seat_position and p.get("status") == "matched":
            total += p.get("seat_count", 1)
    return total


def check_seat_available(
    seat_position: str,
    requested_count: int,
    total_trip_seats: int,
    already_matched: List[Dict]
) -> tuple[bool, str]:
    """
    So'ralgan o'rindiq mavjudligini tekshiradi.

    Qaytaradi: (mavjud: bool, sabab: str)
    """
    capacity = get_seat_capacity(seat_position, total_trip_seats)
    booked = count_booked_seats(already_matched, seat_position)
    available = capacity - booked

    if requested_count > available:
        pos_name = "oldi o'rindiq" if seat_position == "front" else "orqa o'rindiq"
        if available <= 0:
            return False, f"{pos_name.capitalize()} to'liq band"
        return False, f"{pos_name.capitalize()}da faqat {available} ta joy bor, siz {requested_count} ta so'radingiz"

    return True, "ok"


def find_best_matches(
    driver_lat: float,
    driver_lng: float,
    driver_direction: str,
    driver_seats: int,
    same_dir_passengers: List[Dict],
    opposite_dir_passengers: List[Dict],
    already_matched: List[Dict] = None
) -> List[Dict]:
    """
    To'liq matching — o'rindiq cheklovi bilan.

    Har bir yo'lovchi uchun:
    1. O'rindiq turi bo'sh ekanligini tekshiradi
    2. Bir vaqtda band bo'lmaslik uchun hisobga oladi
    3. Masofaga qarab saralaydi
    """
    if already_matched is None:
        already_matched = []

    # Hozirgi band joylar holatini kuzatish uchun
    # (matching davomida yangi qo'shilganlarni ham hisobga olamiz)
    running_matched = list(already_matched)
    result = []
    needed = driver_seats

    def try_add_passenger(p: Dict) -> bool:
        """Yo'lovchini qo'shishga harakat qiladi, o'rindiq tekshiruvi bilan"""
        seat_pos = p.get("seat_position", "back")
        seat_cnt = p.get("seat_count", 1)

        ok, reason = check_seat_available(
            seat_pos, seat_cnt, driver_seats, running_matched
        )
        if not ok:
            p["_rejected_reason"] = reason
            return False

        # O'rindiq bo'sh — qo'shamiz
        p["_matched"] = True
        p["_rejected_reason"] = None
        running_matched.append({**p, "status": "matched"})
        result.append(p)
        return True

    # Masofani hisoblash
    def with_distance(passengers):
        for p in passengers:
            if p.get("lat") and p.get("lng") and driver_lat and driver_lng:
                p["_distance"] = haversine(driver_lat, driver_lng, p["lat"], p["lng"])
            else:
                p["_distance"] = 0.0
        return sorted(passengers, key=lambda x: x["_distance"])

    # 1-bosqich: bir xil yo'nalish, masofaga qarab
    for p in with_distance(same_dir_passengers):
        if len(result) >= needed:
            break
        try_add_passenger(p)

    # 2-bosqich: yo'l ustidagi qarama-qarshi yo'nalish
    if len(result) < needed:
        on_route = [p for p in opposite_dir_passengers
                    if p.get("lat") and is_on_route(p["lat"], p.get("lng", 0))]
        for p in with_distance(on_route):
            if len(result) >= needed:
                break
            try_add_passenger(p)

    return result[:needed]
