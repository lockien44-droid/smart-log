import time
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, db

# ==============================
# CONFIG
# ==============================
FIREBASE_CREDENTIAL = "smart-logistics-system-75a42-a699f876beef.json"

DATABASE_URL = "https://smart-logistics-system-75a42-default-rtdb.asia-southeast1.firebasedatabase.app"

MAX_HISTORY = 20
MAX_GPS_HISTORY = 50
MAX_EVENTS = 100

# ==============================
# INIT FIREBASE SAFE
# ==============================
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(FIREBASE_CREDENTIAL)
        firebase_admin.initialize_app(cred, {
            "databaseURL": DATABASE_URL
        })
        print("[FIREBASE] Initialized successfully")

    except Exception as e:
        print("[FIREBASE INIT ERROR]", e)


# ==============================
# SAFE CONVERT
# ==============================
def safe_int(v, default=0):
    try:
        return int(float(v))
    except:
        return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default


# ==============================
# UPDATE ORDER STATUS (SAFE)
# ==============================
def update_order_status(
    order_id,
    status,
    inventory,
    demand,
    inventory_level=None,

    warehouse_id=None,
    product_id=None,

    latitude=None,
    longitude=None,

    speed=None,
    fuel_level=None,
    vehicle_status=None,

    temperature=None,
    humidity=None,

    vibration=None,
    battery=None,

    eta=None,
    alert=None,
    progress=None,

    reorder_required=None,
    reorder_point=None,
    reorder_quantity=None,
    inventory_level_description=None,
    order_quantity=None,

    event_id=None
):

    try:
        ref = db.reference(f"orders/{order_id}")
        existing = ref.get() or {}

        timestamp = time.time()
        readable_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        inventory = safe_int(inventory)
        demand = safe_int(demand)

        # =========================
        # STATUS HISTORY
        # =========================
        status_history = existing.get("status_history", [])
        if not isinstance(status_history, list):
            status_history = []

        if not status_history or status_history[-1].get("status") != status:
            status_history.append({
                "status": status,
                "time": timestamp,
                "time_text": readable_time
            })

        status_history = status_history[-MAX_HISTORY:]

        # =========================
        # GPS HISTORY
        # =========================
        gps_history = existing.get("gps_history", [])
        if not isinstance(gps_history, list):
            gps_history = []

        if latitude is not None and longitude is not None:
            gps_history.append({
                "latitude": safe_float(latitude),
                "longitude": safe_float(longitude),
                "time": readable_time
            })

        gps_history = gps_history[-MAX_GPS_HISTORY:]

        # =========================
        # EVENTS
        # =========================
        events = existing.get("events", [])
        if not isinstance(events, list):
            events = []

        events.append({
            "time": readable_time,
            "order_id": str(order_id),
            "status": str(status),
            "inventory": inventory,
            "order_quantity": safe_int(order_quantity),
            "future_demand": demand,
            "event": f"Order changed to {status}"
        })

        events = events[-MAX_EVENTS:]

         # =========================
          # BUSINESS LOGIC
         # =========================

        inventory_level = str(
         inventory_level or "NORMAL"
    )

        reorder_point = safe_int(
            reorder_point,
            demand + 50
        )

        if not inventory_level_description:
            inventory_level_description = {
                "NORMAL": "Tồn kho an toàn",
                "LOW": "Tồn kho thấp",
                "CRITICAL": "Tồn kho rất thấp",
                "OUT_OF_STOCK": "Hết hàng"
            }.get(inventory_level, "Không xác định")

        stock_alert = (
            inventory_level in [
                "LOW",
                "CRITICAL",
                "OUT_OF_STOCK"
            ]
        )

        reorder_required = (
            stock_alert
            if reorder_required is None
            else bool(reorder_required)
        )
        prediction = (
             "Restock Required"
         if stock_alert
         else "Stock Sufficient"
         )


        if reorder_required:

         reorder_quantity = max(
            reorder_point - inventory,
            0
         )

        else:

          reorder_quantity = 0

        # =========================
        # MAIN DATA
        # =========================
        data = {
            "order_id": str(order_id),
            "status": str(status),
            "inventory": inventory,
            "order_quantity": safe_int(order_quantity),
            "future_demand": demand,

            "inventory_level": inventory_level,
            "inventory_level_description": str(inventory_level_description),
            "stock_alert": stock_alert,
            "prediction": prediction,

            "reorder_required": reorder_required,
            "reorder_point": reorder_point,
            "reorder_quantity": reorder_quantity,

            "last_updated": timestamp,
            "last_updated_text": readable_time,

            "status_history": status_history,
            "gps_history": gps_history,
            "events": events
        }

        # =========================
        # OPTIONAL FIELDS SAFE
        # =========================
        if warehouse_id:
            data["warehouse_id"] = str(warehouse_id)

        if product_id:
            data["product_id"] = str(product_id)

        if latitude is not None:
            data["latitude"] = safe_float(latitude)

        if longitude is not None:
            data["longitude"] = safe_float(longitude)

        if speed is not None:
            data["speed"] = safe_float(speed)

        if fuel_level is not None:
            data["fuel_level"] = safe_float(fuel_level)

        if vehicle_status:
            data["vehicle_status"] = str(vehicle_status)

        if temperature is not None:
            data["temperature"] = safe_float(temperature)

        if humidity is not None:
            data["humidity"] = safe_float(humidity)
        
        if vibration is not None:
            data["vibration"] = safe_float(vibration)

        if battery is not None:
            data["battery"] = safe_float(battery)

        if eta is not None:
            data["eta"] = safe_int(eta)

        if alert:
            data["alert"] = str(alert)

        if progress is not None:
            data["progress"] = safe_int(progress)

        if event_id:
            data["event_id"] = str(event_id)

        # =========================
        # UPDATE FIREBASE
        # =========================
        ref.update(data)

        print(f"[FIREBASE] Updated {order_id}")

    except Exception as e:
        print("[FIREBASE ERROR]", e)


# ==============================
# GET FUNCTIONS
# ==============================
def get_order(order_id):
    try:
        return db.reference(f"orders/{order_id}").get()
    except:
        return None


def get_all_orders():
    try:
        return db.reference("orders").get()
    except:
        return {}


def clear_orders():
    try:
        db.reference("orders").delete()
        print("[FIREBASE] All orders deleted.")
    except Exception as e:
        print("[FIREBASE ERROR]", e)


# ==============================
# TEST
# ==============================
if __name__ == "__main__":

    clear_orders()

    update_order_status(
        order_id="ORD00001",
        status="Shipping",
        inventory=250,
        demand=600,
        inventory_level="LOW",
        warehouse_id="WH01",
        product_id="PRD001",
        latitude=10.762622,
        longitude=106.660172,
        speed=55.5,
        fuel_level=87.4,
        vehicle_status="Moving",
        temperature=29.5,
        humidity=68.0,
        eta=15,
        alert="NORMAL",
        progress=70,
        event_id="TEST_EVENT_001"
    )

    print(get_order("ORD00001"))
    print("DONE")
