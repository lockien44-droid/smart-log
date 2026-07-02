import random
import time
from datetime import datetime


class GPSTracker:
    """
    GPS Tracker Simulation - PRODUCTION SAFE VERSION
    """

    def __init__(
        self,
        vehicle_id="TRUCK001",
        start_lat=10.762622,
        start_lng=106.660172,
        route="Ho Chi Minh City -> Bien Hoa"
    ):
        self.vehicle_id = str(vehicle_id)

        self.latitude = float(start_lat)
        self.longitude = float(start_lng)

        self.route = str(route)

        self.speed = 0.0
        self.fuel_level = 100.0
        self.total_distance = 0.0

        self.status_history = []

    # =====================================
    # MOVE VEHICLE (SAFE - NO CRASH EVER)
    # =====================================
    def move(self):
        try:
            # simulate movement
            delta_lat = random.uniform(-0.003, 0.003)
            delta_lng = random.uniform(-0.003, 0.003)

            self.latitude += delta_lat
            self.longitude += delta_lng

            self.speed = round(random.uniform(15, 85), 1)

            distance_step = (abs(delta_lat) + abs(delta_lng)) * 111
            self.total_distance += distance_step

            fuel_consumed = random.uniform(0.08, 0.45)
            if self.speed > 60:
                fuel_consumed *= 1.3

            self.fuel_level = max(0.0, self.fuel_level - fuel_consumed)
            self.fuel_level = round(self.fuel_level, 1)

            # =========================
            # STATUS LOGIC
            # =========================
            if self.fuel_level < 15:
                vehicle_status = "Low Fuel"
            elif self.speed < 10:
                vehicle_status = "Stopped"
            elif self.speed < 40:
                vehicle_status = "Slow Moving"
            elif self.speed > 70:
                vehicle_status = "High Speed"
            else:
                vehicle_status = "Moving"

            readable_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # history safe
            self.status_history.append({
                "time": readable_time,
                "status": vehicle_status,
                "speed": self.speed
            })

            self.status_history = self.status_history[-10:]

            # =========================
            # FINAL SAFE OUTPUT
            # =========================
            return {
                "vehicle_id": self.vehicle_id,

                # 🔥 ALWAYS SAFE (FIX ROOT ERROR)
                "latitude": float(round(self.latitude, 6)),
                "longitude": float(round(self.longitude, 6)),

                "speed": float(self.speed),
                "vehicle_status": str(vehicle_status),
                "fuel_level": float(self.fuel_level),

                "distance_traveled": float(round(self.total_distance, 2)),

                "route": self.route,
                "timestamp": time.time(),
                "time_text": readable_time,

                "status_history": self.status_history[-5:]
            }

        except Exception as e:
            # NEVER BREAK PIPELINE
            return {
                "vehicle_id": self.vehicle_id,
                "latitude": 0.0,
                "longitude": 0.0,
                "speed": 0.0,
                "vehicle_status": "ERROR",
                "fuel_level": 0.0,
                "distance_traveled": 0.0,
                "route": self.route,
                "timestamp": time.time(),
                "time_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status_history": [],
                "error": str(e)
            }

    # =====================================
    # REFUEL SAFE
    # =====================================
    def refuel(self, amount=100):
        try:
            amount = max(0, float(amount))
            self.fuel_level = min(100.0, self.fuel_level + amount)

            print(f"[GPS] Vehicle {self.vehicle_id} refueled -> {self.fuel_level}%")

        except:
            pass

    # =====================================
    # STATUS SAFE
    # =====================================
    def get_status(self):
        try:
            current_status = (
                self.status_history[-1]["status"]
                if self.status_history else "Unknown"
            )

            return {
                "vehicle_id": self.vehicle_id,
                "latitude": float(round(self.latitude, 6)),
                "longitude": float(round(self.longitude, 6)),
                "speed": float(self.speed),
                "fuel_level": float(self.fuel_level),
                "status": current_status,
                "total_distance": float(round(self.total_distance, 2))
            }

        except:
            return {
                "vehicle_id": self.vehicle_id,
                "latitude": 0.0,
                "longitude": 0.0,
                "speed": 0.0,
                "fuel_level": 0.0,
                "status": "ERROR",
                "total_distance": 0.0
            }


# =====================================
# TEST
# =====================================
if __name__ == "__main__":

    tracker = GPSTracker("TRUCK001")

    print("Starting GPS simulation...\n")

    for _ in range(10):
        gps = tracker.move()

        print(f"[{gps.get('time_text')}] {gps.get('vehicle_id')}")
        print(f"Location : {gps.get('latitude')}, {gps.get('longitude')}")
        print(f"Speed    : {gps.get('speed')} km/h")
        print(f"Status   : {gps.get('vehicle_status')}")
        print(f"Fuel     : {gps.get('fuel_level')}%")
        print(f"Distance : {gps.get('distance_traveled')} km")
        print("-" * 40)

        time.sleep(0.5)

    tracker.refuel(40)

    print("\nCurrent Status:")
    print(tracker.get_status())