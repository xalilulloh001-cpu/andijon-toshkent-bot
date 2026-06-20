"""
AndTaxi Bot - WebSocket Server (FIXED)
Driver heartbeat, offline detection, improved tracking
"""

import json
import logging
import asyncio
from typing import Set, Dict, Optional
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from database import db
from matching import offline_detection

logger = logging.getLogger(__name__)

app = FastAPI(title="AndTaxi Real-time Tracking")

# Connected clients
connected_drivers: Dict[int, WebSocket] = {}
connected_passengers: Dict[int, WebSocket] = {}

class LocationTracker:
    """Haydovchi lokatsiyasini kuzatish"""
    
    driver_locations = {}
    
    @classmethod
    async def update_driver_location(cls, driver_id: int, lat: float, lng: float):
        """Haydovchi lokatsiyasini yangilash + heartbeat"""
        cls.driver_locations[driver_id] = {
            'lat': lat,
            'lng': lng,
            'timestamp': datetime.now().isoformat()
        }
        
        # ===== FIX #5: Update heartbeat =====
        await db.update_driver_heartbeat(driver_id, lat, lng)
        
        # Broadcast to passengers
        await cls.broadcast_driver_location(driver_id, lat, lng)
    
    @classmethod
    async def broadcast_driver_location(cls, driver_id: int, lat: float, lng: float):
        """Haydovchi lokatsiyasini yo'lovchilarga yuborish"""
        message = {
            'type': 'driver_location',
            'driver_id': driver_id,
            'lat': lat,
            'lng': lng,
            'timestamp': datetime.now().isoformat()
        }
        
        disconnected = []
        for passenger_id, websocket in connected_passengers.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to passenger {passenger_id}: {e}")
                disconnected.append(passenger_id)
        
        for passenger_id in disconnected:
            del connected_passengers[passenger_id]
    
    @classmethod
    def get_driver_location(cls, driver_id: int) -> Optional[Dict]:
        """Haydovchi oxirgi lokatsiyasini olish"""
        return cls.driver_locations.get(driver_id)


class ConnectionManager:
    """WebSocket ulanishlarni boshqarish"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            'driver': set(),
            'passenger': set()
        }
    
    async def connect_driver(self, driver_id: int, websocket: WebSocket):
        """Haydovchi ulanish"""
        await websocket.accept()
        connected_drivers[driver_id] = websocket
        
        # ===== FIX #5: Mark online =====
        await db.mark_driver_online(driver_id)
        
        location = LocationTracker.get_driver_location(driver_id)
        if location:
            await websocket.send_json({
                'type': 'location_history',
                'location': location
            })
        
        logger.info(f"✅ Driver {driver_id} connected")
    
    async def connect_passenger(self, passenger_id: int, websocket: WebSocket):
        """Yo'lovchi ulanish"""
        await websocket.accept()
        connected_passengers[passenger_id] = websocket
        
        logger.info(f"✅ Passenger {passenger_id} connected")
    
    async def disconnect_driver(self, driver_id: int):
        """Haydovchi ulanishni tugatish"""
        if driver_id in connected_drivers:
            del connected_drivers[driver_id]
        logger.info(f"❌ Driver {driver_id} disconnected")
    
    async def disconnect_passenger(self, passenger_id: int):
        """Yo'lovchi ulanishni tugatish"""
        if passenger_id in connected_passengers:
            del connected_passengers[passenger_id]
        logger.info(f"❌ Passenger {passenger_id} disconnected")
    
    async def broadcast_to_group(self, message: dict, group_id: int):
        """Guruhning barcha a'zolariga xabar"""
        members = await db.get_group_members(group_id)
        
        for member in members:
            passenger_id = member['passenger_id']
            if passenger_id in connected_passengers:
                try:
                    await connected_passengers[passenger_id].send_json(message)
                except Exception as e:
                    logger.error(f"Error sending to passenger {passenger_id}: {e}")


manager = ConnectionManager()

# ===== WEBSOCKET ENDPOINTS =====

@app.websocket("/ws/driver/{driver_id}")
async def websocket_driver(websocket: WebSocket, driver_id: int):
    """
    Haydovchi WebSocket endpoint
    
    Message types:
    - heartbeat: {timestamp} (FIX #5)
    - location: {lat, lng}
    - status: "active" | "idle" | "at_destination"
    """
    await manager.connect_driver(driver_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # ===== FIX #5: Heartbeat handling =====
            if data['type'] == 'heartbeat':
                # Just acknowledge - timestamp shows driver is alive
                await websocket.send_json({'status': 'heartbeat_ack'})
            
            elif data['type'] == 'location':
                lat = data['lat']
                lng = data['lng']
                
                await LocationTracker.update_driver_location(driver_id, lat, lng)
                await websocket.send_json({'status': 'location_updated'})
            
            elif data['type'] == 'status':
                status = data['status']
                group_id = data.get('group_id')
                
                if group_id:
                    await manager.broadcast_to_group({
                        'type': 'driver_status',
                        'driver_id': driver_id,
                        'status': status
                    }, group_id)
            
            elif data['type'] == 'arrived':
                group_id = data.get('group_id')
                passenger_id = data.get('passenger_id')
                
                if group_id:
                    await manager.broadcast_to_group({
                        'type': 'driver_arrived',
                        'driver_id': driver_id,
                        'passenger_id': passenger_id
                    }, group_id)
    
    except WebSocketDisconnect:
        await manager.disconnect_driver(driver_id)
        # ===== FIX #5: Mark offline on disconnect =====
        await db.mark_driver_offline(driver_id, "WebSocket disconnected")
    except Exception as e:
        logger.error(f"Driver WebSocket error: {e}")
        await manager.disconnect_driver(driver_id)


@app.websocket("/ws/passenger/{passenger_id}")
async def websocket_passenger(websocket: WebSocket, passenger_id: int):
    """
    Yo'lovchi WebSocket endpoint
    
    Message types:
    - track_group: {group_id}
    - ready: haydovchi ko'rishga tayyor
    """
    await manager.connect_passenger(passenger_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data['type'] == 'track_group':
                group_id = data['group_id']
                group = await db.get_group(group_id)
                
                if group:
                    driver_location = LocationTracker.get_driver_location(group['driver_id'])
                    
                    if driver_location:
                        await websocket.send_json({
                            'type': 'driver_location',
                            'driver_id': group['driver_id'],
                            'lat': driver_location['lat'],
                            'lng': driver_location['lng']
                        })
            
            elif data['type'] == 'ready':
                group_id = data['group_id']
                await manager.broadcast_to_group({
                    'type': 'passenger_ready',
                    'passenger_id': passenger_id
                }, group_id)
    
    except WebSocketDisconnect:
        await manager.disconnect_passenger(passenger_id)
    except Exception as e:
        logger.error(f"Passenger WebSocket error: {e}")
        await manager.disconnect_passenger(passenger_id)


# ===== REST ENDPOINTS =====

@app.get("/api/driver-location/{driver_id}")
async def get_driver_location(driver_id: int):
    """Haydovchi lokatsiyasini olish"""
    location = LocationTracker.get_driver_location(driver_id)
    
    if location:
        return location
    
    return {"error": "Driver location not found"}


@app.post("/api/update-location")
async def update_location_rest(driver_id: int, lat: float, lng: float):
    """REST API orqali lokatsiya yangilash"""
    await LocationTracker.update_driver_location(driver_id, lat, lng)
    
    return {"status": "updated", "driver_id": driver_id}


@app.get("/api/connected-drivers")
async def get_connected_drivers():
    """Ulangan haydovchilar ro'yxati"""
    return {
        "count": len(connected_drivers),
        "driver_ids": list(connected_drivers.keys())
    }


@app.get("/api/connected-passengers")
async def get_connected_passengers():
    """Ulangan yo'lovchilar ro'yxati"""
    return {
        "count": len(connected_passengers),
        "passenger_ids": list(connected_passengers.keys())
    }


@app.get("/health")
async def health_check():
    """Sog'lik tekshiruvi"""
    return {
        "status": "healthy",
        "connected_drivers": len(connected_drivers),
        "connected_passengers": len(connected_passengers)
    }


# ===== BACKGROUND TASKS =====

@app.on_event("startup")
async def startup_event():
    """Server ishga tushayotganda background tasklar boshlash"""
    asyncio.create_task(offline_detection_loop())


async def offline_detection_loop():
    """
    FIX #5: Periodically check for offline drivers
    Har 30 sekundda tekshirish
    """
    while True:
        try:
            await asyncio.sleep(30)
            
            offline_drivers = await db.check_offline_drivers()
            
            for driver_id in offline_drivers:
                await db.mark_driver_offline(
                    driver_id,
                    "No heartbeat (5+ minutes)"
                )
                
                logger.warning(f"🔴 Driver {driver_id} marked offline (no heartbeat)")
        
        except Exception as e:
            logger.error(f"Error in offline detection loop: {e}")


# Static files
try:
    app.mount("/static", StaticFiles(directory="webapp"), name="static")
except:
    logger.warning("Static files directory not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
