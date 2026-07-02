import random
import time
from datetime import datetime


class IoTSensor:
    """
    IoT Sensor Simulation - PRODUCTION SAFE VERSION
    """

    def __init__(self, sensor_id="IOT001", vehicle_id="TRUCK001"):

        self.sensor_id = str(sensor_id)
        self.vehicle_id = str(vehicle_id)

        self.base_temp = 26.5
        self.base_humidity = 62.0
        self.vibration_level = 0.2
        self.battery = 100.0

        self.last_maintenance = datetime.now()

    # =========================
    # SENSOR READ SAFE
    # =========================
    def read_temperature(self):
        self.base_temp += random.uniform(-1.2, 1.5)
        self.base_temp = max(15.0, min(self.base_temp, 48.0))
        return round(self.base_temp, 1)

    def read_humidity(self):
        self.base_humidity += random.uniform(-2.5, 2.5)
        self.base_humidity = max(25.0, min(self.base_humidity, 98.0))
        return round(self.base_humidity, 1)

    def read_vibration(self):
        self.vibration_level = random.uniform(0.1, 2.5)
        return round(self.vibration_level, 2)

    def read_battery(self):
        self.battery -= random.uniform(0.03, 0.15)
        self.battery = max(0.0, self.battery)
        return round(self.battery, 1)

    # =========================
    # CONDITION SAFE
    # =========================
    def evaluate_condition(self, temp, humidity, vibration):

        if temp > 35 or vibration > 3.0 or humidity > 88:
            return "CRITICAL"

        if temp > 30 or vibration > 2.0 or humidity > 78:
            return "WARNING"

        if temp < 18 or humidity < 35:
            return "LOW_CONDITION"

        return "NORMAL"

    # =========================
    # ALERT SAFE (NEVER EMPTY)
    # =========================
    def generate_alert(self, temp, humidity, vibration):

        alerts = []

        if temp > 35:
            alerts.append("HIGH_TEMPERATURE")
        elif temp > 30:
            alerts.append("ELEVATED_TEMPERATURE")

        if humidity > 85:
            alerts.append("HIGH_HUMIDITY")
        elif humidity > 75:
            alerts.append("ELEVATED_HUMIDITY")

        if vibration > 3.0:
            alerts.append("HIGH_VIBRATION")
        elif vibration > 2.0:
            alerts.append("MEDIUM_VIBRATION")

        if self.battery < 20:
            alerts.append("LOW_BATTERY")

        # 🔥 IMPORTANT FIX: ALWAYS HAVE VALUE
        return alerts if alerts else ["NORMAL"]

    # =========================
    # MAIN READ (SAFE OUTPUT)
    # =========================
    def read_all(self):

        try:
            temperature = self.read_temperature()
            humidity = self.read_humidity()
            vibration = self.read_vibration()
            battery = self.read_battery()

            condition = self.evaluate_condition(
                temperature, humidity, vibration
            )

            alerts = self.generate_alert(
                temperature, humidity, vibration
            )

            return {
                "sensor_id": self.sensor_id,
                "vehicle_id": self.vehicle_id,

                "temperature": float(temperature),
                "humidity": float(humidity),
                "vibration": float(vibration),
                "battery": float(battery),

                "condition": str(condition),

                # SAFE FIX (NO KEY ERROR EVER)
                "alerts": alerts,
                "alert": alerts[0],

                "timestamp": time.time(),
                "time_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            return {
                "sensor_id": self.sensor_id,
                "vehicle_id": self.vehicle_id,

                "temperature": 0.0,
                "humidity": 0.0,
                "vibration": 0.0,
                "battery": 0.0,

                "condition": "ERROR",

                "alerts": ["ERROR"],
                "alert": "ERROR",

                "timestamp": time.time(),
                "time_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e)
            }

    # =========================
    # BATTERY CONTROL SAFE
    # =========================
    def recharge_battery(self, amount=30):
        try:
            amount = max(0, float(amount))
            self.battery = min(100.0, self.battery + amount)
        except:
            pass

    # =========================
    # STATUS SAFE
    # =========================
    def get_status(self):

        try:
            return {
                "sensor_id": self.sensor_id,
                "vehicle_id": self.vehicle_id,
                "battery": round(self.battery, 1),
                "last_maintenance": self.last_maintenance.strftime("%Y-%m-%d %H:%M:%S")
            }
        except:
            return {
                "sensor_id": self.sensor_id,
                "vehicle_id": self.vehicle_id,
                "battery": 0.0,
                "last_maintenance": "UNKNOWN"
            }