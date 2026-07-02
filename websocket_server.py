from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import time
from firebase_admin import db

try:
    from firebase_manager import get_all_orders
except Exception:
    get_all_orders = None

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
connected_clients = 0
total_orders = 0
firebase_listener = None


def send_orders_snapshot(client_sid):
    """Load Firebase outside the Socket.IO handshake and reply to one client."""
    try:
        orders = get_all_orders() if get_all_orders is not None else {}
        socketio.emit("orders_snapshot", orders or {}, to=client_sid)
    except Exception as e:
        print(f"[SNAPSHOT ERROR] {e}")
        socketio.emit("orders_snapshot", {}, to=client_sid)


def handle_firebase_change(event):
    """Forward Firebase changes to every connected dashboard via WebSocket."""
    try:
        path = str(event.path or "/").strip("/")

        if not path:
            socketio.emit("orders_snapshot", event.data or {})
            return

        order_id = path.split("/")[0]
        if not order_id:
            return

        if "/" not in path and isinstance(event.data, dict):
            order = event.data
        else:
            order = db.reference(f"orders/{order_id}").get()

        if not isinstance(order, dict):
            return

        order["order_id"] = order.get("order_id", order_id)
        socketio.emit("dashboard_update", order)
    except Exception as e:
        print(f"[FIREBASE LISTENER ERROR] {e}")


def start_firebase_listener():
    global firebase_listener
    try:
        firebase_listener = db.reference("orders").listen(
            handle_firebase_change
        )
        print("[FIREBASE] Realtime listener started")
    except Exception as e:
        print(f"[FIREBASE LISTENER START ERROR] {e}")


# =========================
# DASHBOARD PAGE
# =========================
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# =========================
# HEALTH CHECK
# =========================
@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "connected_clients": connected_clients,
        "total_orders": total_orders,
        "server_time": time.time()
    })


@app.route("/api/orders")
def api_orders():
    if get_all_orders is None:
        return jsonify({})

    try:
        return jsonify(get_all_orders() or {})
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


# =========================
# CONNECT
# =========================
@socketio.on("connect")
def handle_connect():
    global connected_clients
    connected_clients += 1

    print(f"[CONNECTED] Clients: {connected_clients}")

    emit("server_message", {
        "message": "Connected",
        "connected_clients": connected_clients
    })

    # Do not block the WebSocket handshake while Firebase is loading.
    socketio.start_background_task(send_orders_snapshot, request.sid)


# =========================
# DISCONNECT
# =========================
@socketio.on("disconnect")
def handle_disconnect():
    global connected_clients
    connected_clients = max(0, connected_clients - 1)

    print(f"[DISCONNECTED] Clients: {connected_clients}")


# =========================
# STATUS UPDATE (MAIN FIX)
# =========================
@socketio.on("status_update")
def handle_status_update(data):

    global total_orders

    if not isinstance(data, dict):
        emit("error_message", {"message": "Invalid payload"})
        return

    total_orders += 1

    dashboard_data = {
        "event_id": data.get("event_id", ""),
        "order_id": data.get("order_id", ""),
        "warehouse_id": data.get("warehouse_id", ""),
        "product_id": data.get("product_id", ""),

        "status": data.get("status", "Unknown"),
        "progress": data.get("progress", 0),

        "inventory": data.get("inventory", 0),
        "order_quantity": data.get("order_quantity", 0),
        "future_demand": data.get(
            "future_demand",
            data.get("demand", 0)
        ),
        "inventory_level": data.get("inventory_level", "NORMAL"),
        "inventory_level_description": data.get(
            "inventory_level_description",
            ""
        ),

        "reorder_required": data.get("reorder_required", False),
        "reorder_point": data.get("reorder_point", 0),
        "reorder_quantity": data.get("reorder_quantity", 0),

        # Logistics
        "alert": data.get("alert", "NORMAL"),

        "timestamp": data.get("timestamp", time.time()),
        # Numeric Unix time is used by the dashboard for stable sorting.
        "last_updated": time.time(),
        "total_orders": total_orders
    }

    print(f"[ORDER] {dashboard_data['order_id']} | {dashboard_data['status']}")

    # IMPORTANT: broadcast to all clients
    socketio.emit("dashboard_update", dashboard_data)


# =========================
# INVENTORY UPDATE
# =========================
@socketio.on("inventory_update")
def handle_inventory_update(data):
    socketio.emit("inventory_dashboard_update", data)


# =========================
# START SERVER
# =========================
if __name__ == "__main__":
    print("\n=================================")
    print("SMART LOGISTICS SOCKET SERVER")
    print("http://127.0.0.1:8000")
    print("=================================\n")

    start_firebase_listener()

    socketio.run(
        app,
        host="127.0.0.1",
        port=8000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )
