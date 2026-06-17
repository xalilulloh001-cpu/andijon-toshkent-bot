import math
from typing import List, Dict, Any

# Andijon-Toshkent yo'li bo'ylab asosiy shaharlar koordinatalari
ROUTE_POINTS = [
    {"name": "Andijon", "lat": 40.7821, "lng": 72.3442},
    {"name": "Asaka", "lat": 40.6397, "lng": 72.2356},
    {"name": "Namangan", "lat": 40.9983, "lng": 71.6726},
    {"name": "Qo'qon", "lat": 40.5283, "lng": 70.9422},
    {"name": "Marg'ilon", "lat": 40.4736, "lng": 71.7225},
    {"name": "Farg'ona", "lat": 40.3842, "lng": 71.7843},
    {"name": "Sirdaryo", "lat": 40.8393, "lng": 68.6643},
    {"name": "Guliston", "lat": 40.4897, "lng": 68.7842},
    {"name": "Yangiyo'l", "lat": 41.1097, "lng": 69.0500},
    {"name": "Ohangaron", "lat": 41.0828, "lng": 69.6397},
    {"name": "Angren", "lat": 41.0169, "lng": 70.1444},
    {"name": "Toshkent", "lat": 41.2995, "lng": 69.2401},
]


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Ikki nuqta orasidagi masofani km da hisoblaydi"""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_on_route(lat: float, lng: float, max_distance_km: float = 30) -> bool:
    """Nuqta Andijon-Toshkent yo'li ustida yoki yaqinida ekanligini tekshiradi"""
    for point in ROUTE_POINTS:
        dist = haversine(lat, lng, point["lat"], point["lng"])
        if dist <= max_distance_km:
            return True
    return False


def sort_passengers_by_distance(
    driver_lat: float,
    driver_lng: float,
    passengers: List[Dict[str, Any]],
    needed: int
) -> List[Dict[str, Any]]:
    """
    Kaskadli matching algoritmi:
    1. Eng yaqin yo'lovchilar (asosiy yo'nalish)
    2. Uzoqroq, lekin yo'l bo'ylab yo'lovchilar
    3. Qarama-qarshi yo'nalish, yo'l ustidagi yo'lovchilar
    """
    if not passengers:
        return []

    # Har bir yo'lovchiga masofa hisoblash
    for p in passengers:
        p['_distance'] = haversine(driver_lat, driver_lng, p['lat'], p['lng'])

    # Masofaga qarab saralash
    sorted_passengers = sorted(passengers, key=lambda x: x['_distance'])

    # Eng yaqin N tasini qaytarish
    return sorted_passengers[:needed]


def find_best_matches(
    driver_lat: float,
    driver_lng: float,
    driver_direction: str,
    driver_seats: int,
    same_direction_passengers: List[Dict],
    opposite_direction_passengers: List[Dict]
) -> List[Dict]:
    """
    To'liq matching:
    - Avval bir xil yo'nalishdagi eng yaqin yo'lovchilar
    - Yetarli bo'lmasa, yo'l ustidagi qarama-qarshi yo'nalish yo'lovchilar qo'shiladi
    """
    needed = driver_seats

    # 1-bosqich: bir xil yo'nalish
    matched = sort_passengers_by_distance(driver_lat, driver_lng, same_direction_passengers, needed)

    # 2-bosqich: yetarli emas — qarama-qarshi yo'nalish, yo'l ustida
    if len(matched) < needed:
        remaining = needed - len(matched)
        on_route = [p for p in opposite_direction_passengers if is_on_route(p['lat'], p['lng'])]
        extra = sort_passengers_by_distance(driver_lat, driver_lng, on_route, remaining)
        matched.extend(extra)

    return matched[:needed]
