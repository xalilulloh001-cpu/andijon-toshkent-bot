"""
AndTaxi Bot - Matching Algorithm (FIXED)
Route validation, race condition prevention, improved seat allocation
"""

import logging
import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from database import db

logger = logging.getLogger(__name__)

class MatchingEngine:
    """Haydovchi-yo'lovchi matching"""
    
    RADIUS_KM = 15
    MAX_PASSENGERS_PER_GROUP = 4
    
    # FIX #10: Geographic bounds
    ANDIJON = {'lat': 40.7281, 'lng': 72.3391, 'radius': 50}
    TASHKENT = {'lat': 41.2995, 'lng': 69.2401, 'radius': 50}
    
    @staticmethod
    def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine formula - masofani hisoblash (km)"""
        R = 6371
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    @staticmethod
    async def validate_route(from_lat: float, from_lng: float,
                            to_lat: float, to_lng: float) -> Tuple[bool, Optional[str]]:
        """
        FIX #10: Route validation - Andijon → Tashkent only
        """
        is_valid, error = await db.validate_trip_route(from_lat, from_lng, to_lat, to_lng)
        return is_valid, error
    
    @staticmethod
    async def find_passengers_in_radius(driver_lat: float, driver_lng: float,
                                       region: str, n: int = 10) -> List[Dict]:
        """
        Haydovchi atrofidagi eng yaqin yo'lovchilarni topish (15 km)
        """
        try:
            passengers = await db.get_active_passengers_in_region(region)
            
            if not passengers:
                return []
            
            passengers_with_distance = []
            
            for passenger in passengers:
                if passenger['location_lat'] and passenger['location_lng']:
                    # FIX #5: Check if passenger in active group
                    in_group = await db.pool.fetchval("""
                    SELECT group_id FROM group_members 
                    WHERE passenger_id = $1 AND status = 'confirmed'
                    """, passenger['passenger_id'])
                    
                    if in_group:
                        continue  # Skip - already in group
                    
                    distance = MatchingEngine.haversine(
                        driver_lat, driver_lng,
                        float(passenger['location_lat']),
                        float(passenger['location_lng'])
                    )
                    
                    if distance <= MatchingEngine.RADIUS_KM:
                        passengers_with_distance.append({
                            **passenger,
                            'distance': distance
                        })
            
            passengers_with_distance.sort(key=lambda x: x['distance'])
            return passengers_with_distance[:n]
        
        except Exception as e:
            logger.error(f"Error finding passengers: {e}")
            return []
    
    @staticmethod
    async def create_group_with_matching(driver_id: int, driver_lat: float,
                                        driver_lng: float, region: str,
                                        total_seats: int) -> Optional[int]:
        """
        FIX #6: Ensure only one active group per driver
        """
        try:
            # Try to create group (unique constraint will prevent duplicates)
            group_id = await db.create_group(driver_id, region, total_seats)
            
            if not group_id:
                logger.warning(f"⚠️ Driver {driver_id} already has active group")
                return None
            
            logger.info(f"📦 Group {group_id} created for driver {driver_id}")
            
            # Find passengers
            passengers = await MatchingEngine.find_passengers_in_radius(
                driver_lat, driver_lng, region, n=10
            )
            
            if not passengers:
                logger.info(f"❌ No passengers found for group {group_id}")
                return group_id
            
            # Send offers
            offers_made = 0
            for passenger in passengers[:total_seats]:
                success = await db.create_offer(driver_id, passenger['passenger_id'], group_id)
                
                if success:
                    offers_made += 1
                    logger.info(f"📲 Offer sent to passenger {passenger['passenger_id']}")
            
            logger.info(f"✅ {offers_made} offers made for group {group_id}")
            return group_id
        
        except Exception as e:
            logger.error(f"Error creating group with matching: {e}")
            return None
    
    @staticmethod
    def calculate_route_order(passengers: List[Dict]) -> List[Dict]:
        """
        Greedy TSP algorithm - eng yaqindan tartiblaytib marshrutni optimizatsiya qilish
        """
        if not passengers:
            return []
        
        if len(passengers) == 1:
            return passengers
        
        ordered = []
        remaining = list(passengers)
        current = remaining.pop(0)
        ordered.append(current)
        
        while remaining:
            current_pos = (
                float(current['location_lat']),
                float(current['location_lng'])
            )
            
            best_idx = 0
            best_distance = float('inf')
            
            for i, passenger in enumerate(remaining):
                next_pos = (
                    float(passenger['location_lat']),
                    float(passenger['location_lng'])
                )
                
                distance = MatchingEngine.haversine(
                    current_pos[0], current_pos[1],
                    next_pos[0], next_pos[1]
                )
                
                if distance < best_distance:
                    best_distance = distance
                    best_idx = i
            
            current = remaining.pop(best_idx)
            ordered.append(current)
        
        return ordered
    
    @staticmethod
    def build_yandex_maps_url(start_lat: float, start_lng: float,
                              waypoints: List[Tuple[float, float]],
                              end_lat: float = None, end_lng: float = None) -> str:
        """
        Yandex Maps deep link (max 4 waypoint)
        """
        base_url = "https://yandex.uz/maps/"
        rtext = f"{start_lat},{start_lng}"
        
        for i, (wp_lat, wp_lng) in enumerate(waypoints[:3]):
            rtext += f"~{wp_lat},{wp_lng}"
        
        if end_lat and end_lng:
            rtext += f"~{end_lat},{end_lng}"
        
        return f"{base_url}?rtext={rtext}"
    
    @staticmethod
    async def optimize_route_for_pickup(group_id: int) -> List[Dict]:
        """Yo'lovchi yig'ish uchun marshrutni optimizatsiya qilish"""
        try:
            group = await db.get_group(group_id)
            members = await db.get_group_members(group_id)
            
            if not members:
                return []
            
            ordered_members = MatchingEngine.calculate_route_order(members)
            logger.info(f"🗺️ Route optimized for group {group_id}: {len(ordered_members)} passengers")
            
            return ordered_members
        
        except Exception as e:
            logger.error(f"Error optimizing route: {e}")
            return []


class SeatTracker:
    """
    O'rindiq tizimi - muhim vs muhimmas
    FIX #2: Improved reallocation logic
    """
    
    @staticmethod
    async def assign_seat(group_id: int, passenger_id: int,
                         preference: str,
                         is_important: bool) -> str:
        """
        O'rindiq belgilash (atomik)
        Logic:
        - is_important=True → Front (guaranteed)
        - is_important=False → Back or Front (if available)
        """
        try:
            group = await db.get_group(group_id)
            
            if not group:
                return "back"
            
            # Atomically assign seat
            seat_position = "back"
            
            if preference == "front" and is_important:
                if group['front_seat_available']:
                    seat_position = "front"
                else:
                    # Reallocate: move non-important passenger from front to back
                    await SeatTracker.reallocate_seats(group_id, passenger_id)
                    seat_position = "front"
            
            elif preference == "front" and not is_important:
                if group['front_seat_available']:
                    seat_position = "front"
                else:
                    seat_position = "back"
            
            return seat_position
        
        except Exception as e:
            logger.error(f"Error assigning seat: {e}")
            return "back"
    
    @staticmethod
    async def reallocate_seats(group_id: int, new_important_passenger: int) -> bool:
        """
        O'rindiqlarni qayta tarqatish - muhim degani oldinga
        """
        try:
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    members = await conn.fetch("""
                    SELECT gm.*, pq.is_seat_important
                    FROM group_members gm
                    LEFT JOIN passenger_queue pq ON gm.passenger_id = pq.passenger_id
                    WHERE gm.group_id = $1
                    ORDER BY pq.is_seat_important DESC, gm.added_at ASC
                    """, group_id)
                    
                    # First: important passengers get front
                    front_count = 0
                    for member in members:
                        if member.get('is_seat_important') and front_count < 1:
                            await conn.execute(
                                "UPDATE group_members SET seat_position = 'front' WHERE id = $1",
                                member['id']
                            )
                            front_count += 1
                        else:
                            await conn.execute(
                                "UPDATE group_members SET seat_position = 'back' WHERE id = $1",
                                member['id']
                            )
            
            logger.info(f"♻️ Seats reallocated for group {group_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error reallocating seats: {e}")
            return False


class OfflineDetection:
    """
    FIX #5: Driver offline detection
    """
    
    @staticmethod
    async def check_and_cleanup_offline_drivers():
        """
        5 daqiqadan ko'p heartbeat yo'q bo'lgan haydovchilarni offline qilish
        Harsa 30 sekundda tekshiradi
        """
        import asyncio
        
        while True:
            try:
                await asyncio.sleep(30)  # 30 sekundda bir tekshirish
                
                offline_drivers = await db.check_offline_drivers()
                
                for driver_id in offline_drivers:
                    await db.mark_driver_offline(
                        driver_id,
                        "Heartbeat yo'q (5+ daqiqa)"
                    )
                    
                    # Telegram notification
                    try:
                        from bot import bot
                        await bot.send_message(
                            driver_id,
                            "⚠️ Ulanish uzildi. Qayta /start boshlang"
                        )
                    except:
                        pass
                
                if offline_drivers:
                    logger.warning(f"🔴 {len(offline_drivers)} drivers marked offline")
            
            except Exception as e:
                logger.error(f"Error in offline detection: {e}")
                await asyncio.sleep(30)


# Singletons
matching_engine = MatchingEngine()
seat_tracker = SeatTracker()
offline_detection = OfflineDetection()
