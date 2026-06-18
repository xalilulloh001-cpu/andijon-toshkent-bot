import math
from typing import List, Dict, Optional

ROUTE_POINTS = [
    {"name": "Andijon",   "lat": 40.7821, "lng": 72.3442},
    {"name": "Asaka",     "lat": 40.6397, "lng": 72.2356},
    {"name": "Namangan",  "lat": 40.9983, "lng": 71.6726},
    {"name": "Qo'qon",   "lat": 40.5283, "lng": 70.9422},
    {"name": "Marg'ilon","lat": 40.4736, "lng": 71.7225},
    {"name": "Farg'ona", "lat": 40.3842, "lng": 71.7843},
    {"name": "Sirdaryo",  "lat": 40.8393, "lng": 68.6643},
    {"name": "Guliston",  "lat": 40.4897, "lng": 68.7842},
    {"name": "Yangiyo'l","lat": 41.1097, "lng": 69.0500},
    {"name": "Ohangaron", "lat": 41.0828, "lng": 69.6397},
    {"name": "Angren",    "lat": 41.0169, "lng": 70.1444},
    {"name": "Toshkent",  "lat": 41.2995, "lng": 69.2401},
]

# Matnli joylashuv → mintaqa nomiga moslashtirish
REGION_ALIASES = {
    "eski shahar": "andijon_eski",
    "andijon eski": "andijon_eski",
    "yangi shahar": "andijon_yangi",
    "ko'k bo'z": "toshkent_kokboz",
    "chilonzor": "toshkent_chilonzor",
    "yunusobod": "toshkent_yunusobod",
    "xo'jaobod": "xojaobod",
    "xojaobod": "xojaobod",
    "asaka": "asaka",
    "namangan": "namangan",
    "qo'qon": "qoqon",
    "farg'ona": "fargona",
}


def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def parse_region(text: str) -> Optional[str]:
    """Matnli joylashuvdan mintaqa nomini aniqlaydi"""
    t = text.lower().strip()
    for alias, region in REGION_ALIASES.items():
        if alias in t:
            return region
    return t.replace(" ", "_")[:30]


def group_passengers_by_proximity(
    passengers: List[Dict],
    needed: int,
    max_group_radius_km: float = 15.0
) -> List[List[Dict]]:
    """
    Yo'lovchilarni bir-biriga yaqin guruhlarga bo'ladi.
    Har guruhda 'needed' ta yoki kamroq yo'lovchi bo'ladi.
    Guruh radiusi max_group_radius_km km dan oshmasin.

    Lokatsiyasiz yo'lovchilar (faqat matn) bir xil region bo'lsa guruhlanadi.
    """
    if not passengers:
        return []

    used = set()
    groups = []

    # 1. Lokatsiyali yo'lovchilar — koordinata bo'yicha guruhlash
    with_coords = [p for p in passengers if p.get('lat') and p.get('lng')]
    without_coords = [p for p in passengers if not (p.get('lat') and p.get('lng'))]

    # Greedy clustering
    for anchor in with_coords:
        if anchor['id'] in used:
            continue
        group = [anchor]
        used.add(anchor['id'])
        for other in with_coords:
            if other['id'] in used:
                continue
            if len(group) >= needed:
                break
            d = haversine(anchor['lat'], anchor['lng'], other['lat'], other['lng'])
            if d <= max_group_radius_km:
                group.append(other)
                used.add(other['id'])
        groups.append(group)

    # 2. Lokatsiyasiz yo'lovchilar — region bo'yicha guruhlash
    region_buckets: Dict[str, List] = {}
    for p in without_coords:
        r = p.get('region') or 'unknown'
        region_buckets.setdefault(r, []).append(p)

    for region, plist in region_buckets.items():
        for i in range(0, len(plist), needed):
            chunk = plist[i:i+needed]
            groups.append(chunk)

    return groups


def sort_passengers_for_pickup(
    driver_lat: Optional[float],
    driver_lng: Optional[float],
    passengers: List[Dict]
) -> List[Dict]:
    """
    Haydovchi turgan joydan boshlab qaysi yo'lovchini birinchi olish kerakligini aniqlaydi.
    Eng yaqindan boshlab saralaydi — TSP (Traveling Salesman) oddiy greedy versiyasi.
    Lokatsiyasiz yo'lovchilar oxiriga qo'yiladi.
    """
    if not passengers:
        return []

    with_coords = [p for p in passengers if p.get('lat') and p.get('lng')]
    without_coords = [p for p in passengers if not (p.get('lat') and p.get('lng'))]

    if not driver_lat or not driver_lng:
        # Haydovchi koordinatasi yo'q — tartibni o'zgartirmaymiz
        return passengers

    ordered = []
    remaining = list(with_coords)
    cur_lat, cur_lng = driver_lat, driver_lng

    while remaining:
        nearest = min(remaining, key=lambda p: haversine(cur_lat, cur_lng, p['lat'], p['lng']))
        nearest['_pickup_dist'] = round(haversine(cur_lat, cur_lng, nearest['lat'], nearest['lng']), 1)
        ordered.append(nearest)
        remaining.remove(nearest)
        cur_lat, cur_lng = nearest['lat'], nearest['lng']

    return ordered + without_coords


def build_yandex_navigator_url(
    driver_lat: Optional[float],
    driver_lng: Optional[float],
    passengers: List[Dict]
) -> str:
    """
    Yandex Navigator deep link — bir marshrut ichida barcha to'xtash joylari.
    Format: https://yandex.uz/maps/?rtext=lat,lng~lat,lng~lat,lng&rtt=auto
    """
    points = []

    if driver_lat and driver_lng:
        points.append(f"{driver_lat},{driver_lng}")

    for p in passengers:
        if p.get('lat') and p.get('lng'):
            points.append(f"{p['lat']},{p['lng']}")

    if len(points) < 2:
        return ""

    rtext = "~".join(points)
    return f"https://yandex.uz/maps/?rtext={rtext}&rtt=auto&mode=routes"


def build_route_text(passengers: List[Dict], lang: str = 'uz') -> str:
    """
    Haydovchiga marshrut matnini tuzib beradi.
    Masalan:
    1️⃣ Zulfiya A. — Eski shahar (2.3 km)
    2️⃣ Mansur K. — Xo'jaobod (5.1 km)
    """
    lines = []
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, p in enumerate(passengers):
        num = nums[i] if i < len(nums) else f"{i+1}."
        name = p.get('full_name', '?')
        loc = p.get('location_name') or p.get('region') or ('Lokatsiya yo\'q' if lang == 'uz' else 'Без локации')
        dist = p.get('_pickup_dist', '')
        dist_txt = f" ({dist} km)" if dist else ""
        lines.append(f"{num} {name} — {loc}{dist_txt}")
    return "\n".join(lines)


def find_best_group(
    waiting_passengers: List[Dict],
    needed: int
) -> Optional[List[Dict]]:
    """
    Kutayotgan yo'lovchilar ichidan eng yaxshi guruhni topadi.
    Eng ko'p a'zoli, bir-biriga eng yaqin guruhni qaytaradi.
    """
    groups = group_passengers_by_proximity(waiting_passengers, needed)
    if not groups:
        return None

    # Eng to'liq guruhni tanlash
    best = max(groups, key=lambda g: len(g))
    if not best:
        return None

    return best[:needed]
