import math
from typing import List, Dict, Optional, Tuple

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

REGION_ALIASES = {
    "eski shahar": "andijon_eski", "andijon eski": "andijon_eski",
    "yangi shahar": "andijon_yangi", "ko'k bo'z": "toshkent_kokboz",
    "chilonzor": "toshkent_chilonzor", "yunusobod": "toshkent_yunusobod",
    "xo'jaobod": "xojaobod", "xojaobod": "xojaobod",
    "asaka": "asaka", "namangan": "namangan",
    "qo'qon": "qoqon", "farg'ona": "fargona",
}


def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def parse_region(text: str) -> str:
    t = text.lower().strip()
    for alias, region in REGION_ALIASES.items():
        if alias in t:
            return region
    return t.replace(" ", "_")[:30]


def get_seat_capacity(seat_position: str, total_seats: int) -> int:
    """Oldi → 1, Orqa → total_seats - 1"""
    return 1 if seat_position == "front" else max(1, total_seats - 1)


class SeatTracker:
    """
    Guruh tuzish jarayonida o'rindiqlarni kuzatib boradi.
    front_used: oldi o'rindiqda band joylar
    back_used:  orqa o'rindiqda band joylar
    """
    def __init__(self, total_seats: int):
        self.total = total_seats
        self.front_cap = 1
        self.back_cap = max(1, total_seats - 1)
        self.front_used = 0
        self.back_used = 0

    def can_fit(self, seat_position: str, seat_count: int) -> bool:
        if seat_position == "front":
            return self.front_used + seat_count <= self.front_cap
        return self.back_used + seat_count <= self.back_cap

    def can_fit_back(self, seat_count: int) -> bool:
        return self.back_used + seat_count <= self.back_cap

    def book(self, seat_position: str, seat_count: int):
        if seat_position == "front":
            self.front_used += seat_count
        else:
            self.back_used += seat_count

    def total_booked(self) -> int:
        return self.front_used + self.back_used

    def is_full(self) -> bool:
        return self.total_booked() >= self.total

    def front_available(self) -> int:
        return max(0, self.front_cap - self.front_used)

    def back_available(self) -> int:
        return max(0, self.back_cap - self.back_used)


def build_group_with_seat_check(
    passengers: List[Dict],
    total_seats: int,
    max_radius_km: float = 15.0
) -> Tuple[List[Dict], List[Dict]]:
    """
    O'rindiq cheklovi bilan guruh tuzadi.

    Qaytaradi:
      fitted   — guruhga qo'shilgan yo'lovchilar (seat_position belgilangan)
      overflow — oldi to'lganda orqaga o'tkazish taklif qilinadigan yo'lovchilar
                 har birida '_offered_back': True belgisi bor
    """
    if not passengers:
        return [], []

    tracker = SeatTracker(total_seats)
    fitted = []
    overflow = []

    # Avval koordinatalilari, keyin matnlilari
    with_coords = sorted(
        [p for p in passengers if p.get('lat') and p.get('lng')],
        key=lambda p: p.get('_distance', 0)
    )
    without_coords = [p for p in passengers if not (p.get('lat') and p.get('lng'))]
    ordered = with_coords + without_coords

    for p in ordered:
        if tracker.is_full():
            break

        pos = p.get('seat_position', 'back')
        cnt = p.get('seat_count', 1)

        if tracker.can_fit(pos, cnt):
            # Mos keladi — qo'shamiz
            tracker.book(pos, cnt)
            fitted.append({**p, '_final_seat': pos})

        elif pos == 'front' and tracker.can_fit_back(cnt):
            # Oldi to'lgan, lekin orqa bo'sh → overflow ga
            overflow.append({**p, '_offered_back': True, '_back_available': tracker.back_available()})

        # Orqa to'lgan yoki joy yetmasa — o'tkazib yuboramiz (keyingi guruhga tushadi)

    return fitted, overflow


def group_passengers_by_proximity(
    passengers: List[Dict],
    total_seats: int,
    max_radius_km: float = 15.0
) -> Optional[Tuple[List[Dict], List[Dict]]]:
    """
    Bir-biriga yaqin yo'lovchilar guruhini topib, o'rindiq tekshiruvi qiladi.

    Qaytaradi: (fitted, overflow) yoki None
    """
    if not passengers:
        return None

    # Koordinatali va koordinatasiz ajratish
    with_coords = [p for p in passengers if p.get('lat') and p.get('lng')]
    without_coords = [p for p in passengers if not (p.get('lat') and p.get('lng'))]

    best_group = None
    best_score = 0

    # Greedy clustering — har birini anchor qilib guruh quramiz
    used_ids = set()

    for anchor in with_coords:
        if anchor['id'] in used_ids:
            continue

        group = [anchor]
        for other in with_coords:
            if other['id'] == anchor['id'] or other['id'] in used_ids:
                continue
            if len(group) >= total_seats:
                break
            d = haversine(anchor['lat'], anchor['lng'], other['lat'], other['lng'])
            if d <= max_radius_km:
                group.append(other)

        # Masofani belgilab qo'yamiz
        for p in group:
            p['_distance'] = haversine(anchor['lat'], anchor['lng'], p['lat'], p['lng'])

        # O'rindiq tekshiruvi
        fitted, overflow = build_group_with_seat_check(group, total_seats, max_radius_km)
        score = len(fitted) * 10 - len(overflow)  # fitted ko'p, overflow kam bo'lsin

        if score > best_score or best_group is None:
            best_score = score
            best_group = (fitted, overflow)
            used_ids.update(p['id'] for p in fitted)

    # Koordinatasiz yo'lovchilar — region bo'yicha
    if without_coords and (best_group is None or len(best_group[0]) < total_seats):
        region_buckets: Dict[str, List] = {}
        for p in without_coords:
            r = p.get('region') or 'unknown'
            region_buckets.setdefault(r, []).append(p)

        for region, plist in region_buckets.items():
            chunk = plist[:total_seats]
            fitted, overflow = build_group_with_seat_check(chunk, total_seats)
            if best_group is None or len(fitted) > len(best_group[0]):
                best_group = (fitted, overflow)

    return best_group


def find_best_group(
    waiting_passengers: List[Dict],
    total_seats: int
) -> Optional[Tuple[List[Dict], List[Dict]]]:
    """
    Asosiy kirish nuqtasi.

    Qaytaradi:
      (fitted, overflow)
      fitted   — to'g'ridan-to'g'ri guruhga qo'shiladigan yo'lovchilar
      overflow — oldi o'rindiq to'lganda orqaga o'tkazish taklif qilinadigan yo'lovchilar
    """
    result = group_passengers_by_proximity(waiting_passengers, total_seats)
    if not result:
        return None
    fitted, overflow = result
    if not fitted:
        return None
    return fitted[:total_seats], overflow


def sort_passengers_for_pickup(
    driver_lat: Optional[float],
    driver_lng: Optional[float],
    passengers: List[Dict]
) -> List[Dict]:
    """Haydovchi joyidan boshlab greedy TSP"""
    if not passengers:
        return []

    with_coords = [p for p in passengers if p.get('lat') and p.get('lng')]
    without_coords = [p for p in passengers if not (p.get('lat') and p.get('lng'))]

    if not driver_lat or not driver_lng:
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
    points = []
    if driver_lat and driver_lng:
        points.append(f"{driver_lat},{driver_lng}")
    for p in passengers:
        if p.get('lat') and p.get('lng'):
            points.append(f"{p['lat']},{p['lng']}")
    if len(points) < 2:
        return ""
    return f"https://yandex.uz/maps/?rtext={'~'.join(points)}&rtt=auto&mode=routes"


def build_route_text(passengers: List[Dict], lang: str = 'uz') -> str:
    lines = []
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, p in enumerate(passengers):
        num = nums[i] if i < len(nums) else f"{i+1}."
        name = p.get('full_name', '?')
        loc = p.get('location_name') or p.get('region') or ('Lokatsiya yo\'q' if lang == 'uz' else 'Без адреса')
        dist = p.get('_pickup_dist', '')
        seat = p.get('_final_seat', p.get('seat_position', 'back'))
        seat_txt = ("🪑 Oldi" if lang == 'uz' else "🪑 Перед") if seat == 'front' \
                   else ("💺 Orqa" if lang == 'uz' else "💺 Зад")
        dist_txt = f" · {dist} km" if dist else ""
        lines.append(f"{num} {name} — {loc}{dist_txt} | {seat_txt}")
    return "\n".join(lines)
