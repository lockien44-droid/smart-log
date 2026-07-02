from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from datetime import datetime
import threading
import time

from inventory_manager import (
    get_inventory,
    get_stock,
    update_inventory,
    add_stock,
    check_inventory,
    total_inventory
)

from predictor import predict_demand
from gps_tracking import GPSTracker
from iot_sensor import IoTSensor
from analytics import build_dashboard_summary
from firebase_manager import (
    update_order_status,
    get_all_orders
)

# =========================
# FLASK SETUP
# =========================
app = Flask(__name__)
app.config["SECRET_KEY"] = "smartlogistics"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False
)

# =========================
# GLOBAL STATE
# =========================
data_lock = threading.Lock()

known_orders = set()
total_orders = 0

order_stats = {
    "Pending": 0,
    "Processing": 0,
    "Shipping": 0,
    "Delivered": 0,
    "Cancelled": 0
}

eta_history = []

gps_trackers = {}
iot_sensors = {}
order_status_map = {}

# =========================
# HELPERS
# =========================
def safe_int(v, d=0):
    try:
        return int(v)
    except Exception:
        return d


def safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def safe_dict(obj, fallback):
    return obj if isinstance(obj, dict) else fallback


def calculate_eta(distance, traffic):
    factor = {
        "Low": 1.0,
        "Medium": 1.3,
        "High": 1.7
    }

    return round(
        (distance / 50) * factor.get(traffic, 1.3),
        2
    )

# =========================
# ROUTES
# =========================
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "total_orders": total_orders,
        "total_inventory": total_inventory(),
        "order_stats": order_stats,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/stats")
def stats():
    return jsonify(
        build_dashboard_summary(
            total_orders,
            order_stats,
            total_inventory(),
            1500,
            eta_history
        )
    )


@app.route("/api/orders")
def orders():
    return jsonify(
        get_all_orders() or {}
    )

# =========================
# SOCKET EVENTS
# =========================
@socketio.on("connect")
def handle_connect():

    print("[SOCKET] Client Connected")

    socketio.emit(
        "initial_data",
        {
            "total_orders": total_orders,
            "total_inventory": total_inventory(),
            "order_stats": order_stats
        }
    )


@socketio.on("disconnect")
def handle_disconnect():
    print("[SOCKET] Client Disconnected")


@socketio.on("status_update")
def handle_status(data):

    global total_orders

    try:

        if not isinstance(data, dict):
            return

        order_id = str(
            data.get("order_id", "")
        ).strip()

        if not order_id:
            return

        warehouse_id = str(
            data.get("warehouse_id", "WH01")
        )

        vehicle_id = str(
            data.get("vehicle_id", "TRUCK001")
        )

        status = str(
            data.get("status", "Pending")
        )

        quantity = safe_int(
            data.get("quantity")
        )

        daily_sales = safe_int(
            data.get("daily_sales", 50)
        )

        incoming_stock = safe_int(
            data.get("incoming_stock")
        )

        lead_time = safe_float(
            data.get("lead_time", 2)
        )

        transport_distance = safe_float(
            data.get("transport_distance", 50)
        )

        traffic_level = str(
            data.get("traffic_level", "Medium")
        )

        vehicle_capacity = safe_int(
            data.get("vehicle_capacity", 1000)
        )

        # =====================
        # ORDER STATS
        # =====================
        with data_lock:

            if order_id not in known_orders:
                known_orders.add(order_id)
                total_orders += 1

            old_status = order_status_map.get(order_id)

            if old_status:
                order_stats[old_status] = max(
                    0,
                    order_stats.get(old_status, 0) - 1
                )

            order_stats[status] = (
                order_stats.get(status, 0) + 1
            )

            order_status_map[order_id] = status

        # =====================
        # INVENTORY
        # =====================
        current_stock = get_stock(
            warehouse_id
        )
        predicted_demand = predict_demand(
            inventory_quantity=current_stock,
            order_quantity=quantity,
            daily_sales=daily_sales,
            incoming_stock=incoming_stock,
            lead_time=lead_time,
            delivery_status=status,
            vehicle_capacity=vehicle_capacity
)

        inventory_status = check_inventory(
            warehouse_id=warehouse_id,
            future_demand=predicted_demand,
            lead_time=lead_time
)
        # =====================
        # GPS TRACKER
        # =====================
        tracker = gps_trackers.get(vehicle_id)

        if tracker is None:
            tracker = GPSTracker(vehicle_id)
            gps_trackers[vehicle_id] = tracker

        gps_data = tracker.move()
        # =====================
        # IOT SENSOR
        # =====================

        sensor = iot_sensors.get(vehicle_id)

        if sensor is None:
           sensor = IoTSensor(
                sensor_id=f"IOT_{vehicle_id}",
                vehicle_id=vehicle_id
        )

        iot_sensors[vehicle_id] = sensor

        iot_data = sensor.read_all()

        # =====================
        # INVENTORY UPDATE
        # =====================
        if status == "Delivered":
             current_stock = update_inventory(
                  warehouse_id,
                  quantity
         )

        if incoming_stock > 0:
             current_stock = add_stock(
                  warehouse_id,
                  incoming_stock
         )
        inventory_status = check_inventory(
             warehouse_id=warehouse_id,
             future_demand=predicted_demand,
              lead_time=lead_time
         )
        update_order_status(
             order_id=order_id,
             status=status,

        inventory=current_stock,
        demand=predicted_demand,

        inventory_level=inventory_status[
              "inventory_level"
         ],

        warehouse_id=warehouse_id,

             latitude=gps_data["latitude"],
             longitude=gps_data["longitude"],

        speed=gps_data["speed"],
        fuel_level=gps_data["fuel_level"],
        vehicle_status=gps_data["vehicle_status"],

        temperature=iot_data["temperature"],
        humidity=iot_data["humidity"],

        eta=calculate_eta(
            transport_distance,
            traffic_level
         ),

        alert=iot_data["alert"]
    )

        print(
              f"[ORDER] {order_id} | "
              f"{status} | "
              f"Stock={current_stock}"
             )
    except Exception as e:
        print("[ERROR]", e)