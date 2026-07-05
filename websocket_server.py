from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from werkzeug.exceptions import HTTPException
import os
import time
from datetime import datetime
from firebase_admin import db

from inventory_manager import evaluate_inventory
from predictor import get_model_info, predict_demand

FIREBASE_IMPORT_ERROR = None
try:
    from firebase_manager import (
        add_product_stock,
        deduct_product_stock,
        get_all_orders,
        get_order,
        get_product_stock,
        set_product_stock,
        update_order_status,
        update_product_inventory_analysis,
    )
except Exception as error:
    FIREBASE_IMPORT_ERROR = str(error)
    add_product_stock = None
    deduct_product_stock = None
    get_all_orders = None
    get_order = None
    get_product_stock = None
    set_product_stock = None
    update_order_status = None
    update_product_inventory_analysis = None
    print("[FIREBASE] Initialization failed:", FIREBASE_IMPORT_ERROR)

app = Flask(__name__)
app.config["SECRET_KEY"] = "smartlogistics"


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return jsonify({
            "ok": False,
            "error": error.description,
        }), error.code

    message = str(error)
    firebase_error = any(
        keyword in message.lower()
        for keyword in ("firebase", "database", "credential", "connection")
    )
    return jsonify({
        "ok": False,
        "error": (
            "Không thể kết nối hoặc ghi dữ liệu Firebase."
            if firebase_error
            else "Backend xử lý thất bại."
        ),
        "detail": message,
    }), 503 if firebase_error else 500

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


def _log(message):
    return {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": str(message),
    }


@app.route("/api/model-info")
def model_info():
    return jsonify(get_model_info())


@app.route("/api/orders/process", methods=["POST"])
def process_order():
    if FIREBASE_IMPORT_ERROR or get_product_stock is None:
        return jsonify({
            "ok": False,
            "error": "Firebase chưa khởi tạo được trên backend.",
            "detail": FIREBASE_IMPORT_ERROR,
        }), 503

    process_started = time.perf_counter()
    data = request.get_json(silent=True) or {}
    errors = {}

    order_id = str(data.get("order_id", "")).strip()
    warehouse_id = str(data.get("warehouse_id", "")).strip()
    product_id = str(data.get("product_id", "")).strip()

    try:
        order_quantity = int(data.get("order_quantity", 0))
    except (TypeError, ValueError):
        order_quantity = 0

    try:
        lead_time = float(data.get("lead_time", 0))
    except (TypeError, ValueError):
        lead_time = 0

    try:
        daily_sales = max(0, int(data.get("daily_sales", 0)))
    except (TypeError, ValueError):
        daily_sales = 0

    initial_stock_raw = data.get("initial_stock")
    try:
        initial_stock = (
            None
            if initial_stock_raw in (None, "")
            else int(initial_stock_raw)
        )
    except (TypeError, ValueError):
        initial_stock = -1

    if not order_id:
        errors["order_id"] = "Không được để trống mã đơn hàng."
    if not product_id:
        errors["product_id"] = "Không được để trống mã sản phẩm."
    if not warehouse_id:
        errors["warehouse_id"] = "Không được để trống mã kho."
    if order_quantity <= 0:
        errors["order_quantity"] = "Số lượng đặt phải lớn hơn 0."
    if lead_time <= 0:
        errors["lead_time"] = "Lead time phải lớn hơn 0."
    if initial_stock is not None and initial_stock < 0:
        errors["initial_stock"] = "Tồn kho ban đầu không được âm."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    existing_order = get_order(order_id)
    if isinstance(existing_order, dict) and existing_order.get("processed"):
        return jsonify({
            "ok": False,
            "error": "Mã đơn đã được xử lý, hệ thống không trừ kho lần hai.",
        }), 409

    logs = [_log(f"Nhận đơn hàng {order_id}")]

    stock_before = get_product_stock(warehouse_id, product_id)
    if stock_before is None:
        if initial_stock is None:
            return jsonify({
                "ok": False,
                "error": (
                    "Sản phẩm chưa tồn tại trong kho. "
                    "Hãy nhập tồn kho ban đầu."
                ),
            }), 400
        stock_before = set_product_stock(
            warehouse_id,
            product_id,
            initial_stock,
        )
        logs.append(_log(f"Khởi tạo tồn kho = {stock_before}"))

    model_details = get_model_info()
    prediction_started = time.perf_counter()
    prediction_result = predict_demand(
        warehouse_id=warehouse_id,
        product_id=product_id,
        inventory_quantity=stock_before,
        order_quantity=order_quantity,
        daily_sales=daily_sales,
        incoming_stock=0,
        lead_time=lead_time,
        delivery_status="Pending",
        vehicle_capacity=1000,
        return_details=True,
    )
    demand = max(
        0,
        round(prediction_result["future_demand"]),
    )
    prediction_latency_ms = round(
        (time.perf_counter() - prediction_started) * 1000
    )
    logs.append(_log(
        f"{prediction_result['mode']} dự báo nhu cầu = {demand} "
        f"({prediction_latency_ms} ms)"
    ))
    if prediction_result["fallback_used"]:
        logs.append(_log(
            "CẢNH BÁO: Model lỗi hoặc không tồn tại; "
            f"đang dùng fallback. {prediction_result.get('error') or ''}"
        ))

    try:
        stock_after = deduct_product_stock(
            warehouse_id,
            product_id,
            order_quantity,
            order_id=order_id,
        )
    except ValueError as exc:
        logs.append(_log(str(exc)))
        return jsonify({
            "ok": False,
            "error": str(exc),
            "logs": logs,
        }), 409

    logs.append(_log(f"Tồn kho mới = {stock_after}"))
    report = evaluate_inventory(
        stock=stock_after,
        future_demand=demand,
        lead_time=lead_time,
        warehouse_id=warehouse_id,
    )
    level = report["inventory_level"]
    alert = {
        "NORMAL": "NORMAL",
        "LOW": "LOW_STOCK",
        "CRITICAL": "REORDER_REQUIRED",
        "OUT_OF_STOCK": "OUT_OF_STOCK",
    }[level]

    update_product_inventory_analysis(
        warehouse_id=warehouse_id,
        product_id=product_id,
        future_demand=demand,
        inventory_level=level,
        reorder_point=report["reorder_point"],
        reorder_quantity=report["reorder_quantity"],
        reorder_required=report["reorder_required"],
    )

    logs.append(_log("Gửi dữ liệu lên Firebase"))
    processing_latency_ms = round(
        (time.perf_counter() - process_started) * 1000
    )
    server_completed_at_ms = round(time.time() * 1000)
    logs.append(_log(
        f"Backend hoàn tất trong {processing_latency_ms} ms"
    ))
    update_order_status(
        order_id=order_id,
        status="Processing",
        inventory=stock_after,
        inventory_before=stock_before,
        demand=demand,
        inventory_level=level,
        warehouse_id=warehouse_id,
        product_id=product_id,
        order_quantity=order_quantity,
        reorder_point=report["reorder_point"],
        reorder_quantity=report["reorder_quantity"],
        reorder_required=report["reorder_required"],
        alert=alert,
        progress=30,
        inventory_level_description=report[
            "inventory_level_description"
        ],
        processing_logs=logs,
        processing_latency_ms=processing_latency_ms,
        prediction_latency_ms=prediction_latency_ms,
        model_mode=prediction_result["mode"],
        model_version=model_details["model_version"],
        fallback_used=prediction_result["fallback_used"],
        prediction_error=prediction_result.get("error"),
        server_completed_at_ms=server_completed_at_ms,
    )

    return jsonify({
        "ok": True,
        "order": {
            "order_id": order_id,
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "inventory_before": stock_before,
            "order_quantity": order_quantity,
            "inventory": stock_after,
            "future_demand": demand,
            "inventory_level": level,
            "reorder_point": report["reorder_point"],
            "reorder_quantity": report["reorder_quantity"],
            "alert": alert,
            "model_mode": prediction_result["mode"],
            "model_version": model_details["model_version"],
            "fallback_used": prediction_result["fallback_used"],
            "prediction_error": prediction_result.get("error"),
        },
        "logs": logs,
        "model": model_details,
        "processing_latency_ms": processing_latency_ms,
    })


@app.route("/api/products", methods=["POST"])
def create_product():
    if FIREBASE_IMPORT_ERROR or get_product_stock is None:
        return jsonify({
            "ok": False,
            "error": "Firebase chưa khởi tạo được trên backend.",
            "detail": FIREBASE_IMPORT_ERROR,
        }), 503

    data = request.get_json(silent=True) or {}
    warehouse_id = str(data.get("warehouse_id", "")).strip()
    product_id = str(data.get("product_id", "")).strip()

    try:
        stock = int(data.get("stock", -1))
    except (TypeError, ValueError):
        stock = -1

    errors = {}
    if not warehouse_id:
        errors["warehouse_id"] = "Không được để trống mã kho."
    if not product_id:
        errors["product_id"] = "Không được để trống mã sản phẩm."
    if stock < 0:
        errors["stock"] = "Tồn kho không được âm."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    existing_stock = get_product_stock(warehouse_id, product_id)
    if existing_stock is not None:
        return jsonify({
            "ok": False,
            "error": (
                f"Sản phẩm {product_id} đã tồn tại trong kho "
                f"{warehouse_id} với tồn kho {existing_stock}."
            ),
        }), 409

    set_product_stock(warehouse_id, product_id, stock)
    report = evaluate_inventory(
        stock=stock,
        future_demand=0,
        warehouse_id=warehouse_id,
    )
    update_product_inventory_analysis(
        warehouse_id=warehouse_id,
        product_id=product_id,
        future_demand=0,
        inventory_level=report["inventory_level"],
        reorder_point=report["reorder_point"],
        reorder_quantity=report["reorder_quantity"],
        reorder_required=report["reorder_required"],
    )
    return jsonify({
        "ok": True,
        "product": {
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "stock": stock,
            "inventory_level": report["inventory_level"],
        },
    })


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
    port = int(os.environ.get("PORT", "8000"))
    print(f"http://0.0.0.0:{port}")
    print("=================================\n")

    start_firebase_listener()

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )
