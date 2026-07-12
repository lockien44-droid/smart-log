from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from werkzeug.exceptions import HTTPException
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from firebase_admin import db

from app.inventory_service import evaluate_inventory
from app.ai.predictor import get_model_info, predict_demand
from ml.schema import HISTORY_FEATURES

FIREBASE_IMPORT_ERROR = None
try:
    from app.firebase.repository import (
        add_product_stock,
        deduct_product_stock,
        get_all_orders,
        get_order,
        get_product_data,
        get_product_demand_features,
        get_product_sales_features,
        get_product_stock,
        delete_warehouse,
        record_product_daily_sales,
        record_product_daily_demand,
        rename_product_location,
        rename_warehouse,
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
    get_product_data = None
    get_product_demand_features = None
    get_product_sales_features = None
    get_product_stock = None
    delete_warehouse = None
    record_product_daily_sales = None
    record_product_daily_demand = None
    rename_product_location = None
    rename_warehouse = None
    set_product_stock = None
    update_order_status = None
    update_product_inventory_analysis = None
    print("[FIREBASE] Initialization failed:", FIREBASE_IMPORT_ERROR)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_FILE = PROJECT_ROOT / "data" / "raw" / "demand_forecasting.csv"
PROCESSING = "processing"
ACCEPTED = "accepted"
REJECTED = "rejected"
STATUS_LABELS = {
    PROCESSING: "Đang xử lý",
    ACCEPTED: "Đủ hàng – Đã nhận đơn",
    REJECTED: "Không đủ hàng – Từ chối đơn",
}
app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)
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


@app.route("/api/feature-options")
def feature_options():
    if not RAW_DATA_FILE.exists():
        return jsonify({
            "ok": False,
            "error": "Không tìm thấy data/raw/demand_forecasting.csv",
        }), 404

    df = pd.read_csv(RAW_DATA_FILE)

    def values(column):
        if column not in df.columns:
            return []
        return sorted(
            str(value)
            for value in df[column].dropna().unique()
            if str(value).strip()
        )

    return jsonify({
        "ok": True,
        "category": values("Category"),
        "region": values("Region"),
        "weather_condition": values("Weather Condition"),
        "seasonality": values("Seasonality"),
    })


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
    if not order_id:
        order_id = (
            f"ORD_AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{int(time.time() * 1000) % 1000:03d}"
        )
    warehouse_id = str(data.get("warehouse_id", "")).strip()
    product_id = str(data.get("product_id", "")).strip()
    order_date = str(data.get("order_date", "")).strip()
    observation_date = None
    forecast_date = None
    try:
        observation_date = datetime.strptime(order_date, "%Y-%m-%d").date()
        forecast_date = observation_date + timedelta(days=1)
    except (TypeError, ValueError):
        pass

    try:
        order_quantity = int(data.get("order_quantity", 0))
    except (TypeError, ValueError):
        order_quantity = 0

    try:
        incoming_stock = max(0, int(data.get("incoming_stock", 0)))
    except (TypeError, ValueError):
        incoming_stock = 0

    category = str(data.get("category", "")).strip()
    region = str(data.get("region", "")).strip()
    weather_condition = str(data.get("weather_condition", "")).strip()
    seasonality = str(data.get("seasonality", "")).strip()

    try:
        units_sold = max(0, int(data.get("units_sold", order_quantity)))
    except (TypeError, ValueError):
        units_sold = 0

    try:
        inventory_feature = max(0, int(data.get("inventory_quantity", 0)))
    except (TypeError, ValueError):
        inventory_feature = -1

    try:
        price = max(0, float(data.get("price", 0)))
    except (TypeError, ValueError):
        price = -1

    try:
        discount = max(0, float(data.get("discount", 0)))
    except (TypeError, ValueError):
        discount = -1

    try:
        promotion = int(data.get("promotion", 0))
    except (TypeError, ValueError):
        promotion = -1

    try:
        competitor_pricing = max(0, float(data.get("competitor_pricing", 0)))
    except (TypeError, ValueError):
        competitor_pricing = -1

    try:
        epidemic = int(data.get("epidemic", 0))
    except (TypeError, ValueError):
        epidemic = -1

    initial_stock_raw = data.get("initial_stock")
    try:
        initial_stock = (
            None
            if initial_stock_raw in (None, "")
            else int(initial_stock_raw)
        )
    except (TypeError, ValueError):
        initial_stock = -1

    if not product_id:
        errors["product_id"] = "Không được để trống mã sản phẩm."
    if not warehouse_id:
        errors["warehouse_id"] = "Không được để trống mã kho."
    if observation_date is None:
        errors["order_date"] = "Ngày dữ liệu phải theo định dạng YYYY-MM-DD."
    if order_quantity <= 0:
        errors["order_quantity"] = "Số lượng bán phải lớn hơn 0."
    if not category:
        errors["category"] = "Vui lòng chọn danh mục sản phẩm."
    if not region:
        errors["region"] = "Vui lòng chọn khu vực."
    if inventory_feature < 0:
        errors["inventory_quantity"] = "Tồn kho hiện tại phải là số không âm."
    if units_sold <= 0:
        errors["units_sold"] = "Units Sold phải lớn hơn 0."
    if price < 0:
        errors["price"] = "Giá sản phẩm phải là số không âm."
    if discount < 0:
        errors["discount"] = "Giảm giá phải là số không âm."
    if not weather_condition:
        errors["weather_condition"] = "Vui lòng chọn điều kiện thời tiết."
    if promotion not in (0, 1):
        errors["promotion"] = "Khuyến mãi chỉ nhận 0 hoặc 1."
    if competitor_pricing < 0:
        errors["competitor_pricing"] = "Giá đối thủ phải là số không âm."
    if not seasonality:
        errors["seasonality"] = "Vui lòng chọn mùa vụ."
    if epidemic not in (0, 1):
        errors["epidemic"] = "Dịch bệnh chỉ nhận 0 hoặc 1."
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

    history_features = get_product_sales_features(
        warehouse_id,
        product_id,
        order_date,
        units_sold,
    ) if HISTORY_FEATURES and get_product_sales_features is not None else {
        "units_sold_lag_1": units_sold,
        "units_sold_lag_7": None,
        "units_sold_rolling_mean_7": None,
        "history_complete": not HISTORY_FEATURES,
        "missing_history": [],
    }
    actual_demand = data.get("actual_demand")
    if actual_demand not in (None, ""):
        try:
            actual_demand = max(0, float(actual_demand))
        except (TypeError, ValueError):
            return jsonify({
                "ok": False,
                "errors": {"actual_demand": "Must be a non-negative number."},
            }), 400
    else:
        actual_demand = None
    demand_features = get_product_demand_features(
        warehouse_id, product_id, order_date, actual_demand
    ) if HISTORY_FEATURES and get_product_demand_features is not None else {
        "history_complete": not HISTORY_FEATURES,
        "missing_history": [],
    }
    history_features.update({
        key: value for key, value in demand_features.items()
        if key.startswith("demand_")
    })
    history_features["history_complete"] = bool(
        history_features.get("history_complete")
        and demand_features.get("history_complete")
    )
    history_features["missing_history"] = sorted(set(
        history_features.get("missing_history", [])
        + demand_features.get("missing_history", [])
    ))
    if not history_features.get("history_complete"):
        logs.append(_log(
            "Chưa đủ lịch sử bán hàng 7 ngày; dự báo sẽ dùng fallback."
        ))

    model_inventory_quantity = stock_before
    update_order_status(
        order_id=order_id,
        status=PROCESSING,
        inventory=stock_before,
        inventory_before=stock_before,
        demand=0,
        inventory_level="NORMAL",
        warehouse_id=warehouse_id,
        product_id=product_id,
        order_quantity=order_quantity,
        reorder_point=0,
        reorder_quantity=0,
        reorder_required=False,
        alert=PROCESSING.upper(),
        progress=20,
        inventory_level_description=STATUS_LABELS[PROCESSING],
        processed=False,
        processing_logs=logs + [_log(STATUS_LABELS[PROCESSING])],
        incoming_stock=incoming_stock,
        category=category,
        region=region,
        units_sold=units_sold,
        inventory_quantity=model_inventory_quantity,
        price=price,
        discount=discount,
        weather_condition=weather_condition,
        promotion=promotion,
        competitor_pricing=competitor_pricing,
        seasonality=seasonality,
        epidemic=epidemic,
        order_date=order_date,
        forecast_date=forecast_date.isoformat(),
        units_sold_lag_1=history_features.get("units_sold_lag_1"),
        units_sold_lag_7=history_features.get("units_sold_lag_7"),
        units_sold_rolling_mean_7=history_features.get(
            "units_sold_rolling_mean_7"
        ),
        cold_start=not history_features.get("history_complete"),
        missing_history=history_features.get("missing_history"),
    )

    model_details = get_model_info()
    prediction_started = time.perf_counter()
    prediction_result = predict_demand(
        warehouse_id=warehouse_id,
        product_id=product_id,
        category=category,
        region=region,
        inventory_quantity=model_inventory_quantity,
        units_sold=units_sold,
        actual_demand=actual_demand,
        units_sold_lag_1=history_features.get("units_sold_lag_1"),
        units_sold_lag_7=history_features.get("units_sold_lag_7"),
        units_sold_rolling_mean_7=history_features.get(
            "units_sold_rolling_mean_7"
        ),
        **{
            key: history_features.get(key)
            for key in (
                "demand_lag_1", "demand_lag_7", "demand_lag_14",
                "demand_lag_28", "demand_rolling_mean_7",
                "demand_rolling_mean_28", "demand_rolling_std_7",
                "demand_rolling_std_28", "demand_trend_7_28",
            )
        },
        order_quantity=order_quantity,
        incoming_stock=incoming_stock,
        price=price,
        discount=discount,
        weather_condition=weather_condition,
        promotion=promotion,
        competitor_pricing=competitor_pricing,
        seasonality=seasonality,
        epidemic=epidemic,
        order_date=order_date,
        delivery_status=PROCESSING,
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
    if prediction_result.get("unknown_categories"):
        logs.append(_log(
            "Cảnh báo category/ID chưa từng xuất hiện khi train: "
            + ", ".join(prediction_result["unknown_categories"])
        ))
    if prediction_result["fallback_used"]:
        logs.append(_log(
            "CẢNH BÁO: Không dùng được Random Forest; "
            f"đang dùng fallback. {prediction_result.get('error') or ''}"
        ))

    prediction_audit = {
        "order_date": prediction_result.get("observation_date", order_date),
        "forecast_date": prediction_result.get(
            "forecast_date",
            forecast_date.isoformat(),
        ),
        "units_sold_lag_1": history_features.get("units_sold_lag_1"),
        "units_sold_lag_7": history_features.get("units_sold_lag_7"),
        "units_sold_rolling_mean_7": history_features.get(
            "units_sold_rolling_mean_7"
        ),
        "cold_start": prediction_result.get("cold_start", False),
        "fallback_reason": prediction_result.get("fallback_reason"),
        "missing_history": history_features.get("missing_history", []),
        "unknown_categories": prediction_result.get(
            "unknown_categories",
            [],
        ),
    }

    def persist_daily_sales():
        if record_product_daily_sales is None:
            return
        try:
            record_product_daily_sales(
                warehouse_id, product_id, order_date, units_sold
            )
        except Exception as error:
            logs.append(_log(f"Không lưu được lịch sử bán hàng: {error}"))

        if actual_demand is not None and record_product_daily_demand is not None:
            try:
                record_product_daily_demand(
                    warehouse_id, product_id, order_date, actual_demand
                )
            except Exception as error:
                logs.append(_log(f"Cannot store actual demand history: {error}"))

    available_stock = stock_before + incoming_stock
    if order_quantity > available_stock:
        error_message = (
            f"Không đủ tồn kho: tồn {stock_before}, "
            f"nhập thêm {incoming_stock}, khách mua {order_quantity}"
        )
        logs.append(_log(error_message))
        cancel_report = evaluate_inventory(
            stock=stock_before,
            future_demand=demand,
            warehouse_id=warehouse_id,
        )
        update_order_status(
            order_id=order_id,
            status=REJECTED,
            inventory=stock_before,
            inventory_before=stock_before,
            demand=demand,
            inventory_level=cancel_report["inventory_level"],
            warehouse_id=warehouse_id,
            product_id=product_id,
            order_quantity=order_quantity,
            reorder_point=cancel_report["reorder_point"],
            reorder_quantity=cancel_report["reorder_quantity"],
            reorder_required=True,
            alert="OUT_OF_STOCK" if stock_before <= 0 else "INSUFFICIENT_STOCK",
            progress=0,
            inventory_level_description=cancel_report[
                "inventory_level_description"
            ],
            processed=True,
            processing_logs=logs + [_log(STATUS_LABELS[REJECTED])],
            prediction_latency_ms=prediction_latency_ms,
            model_mode=prediction_result["mode"],
            model_version=model_details["model_version"],
            fallback_used=prediction_result["fallback_used"],
            prediction_error=prediction_result.get("error"),
            server_completed_at_ms=round(time.time() * 1000),
            incoming_stock=incoming_stock,
            category=category,
            region=region,
            units_sold=units_sold,
            inventory_quantity=model_inventory_quantity,
            price=price,
            discount=discount,
            weather_condition=weather_condition,
            promotion=promotion,
            competitor_pricing=competitor_pricing,
            seasonality=seasonality,
            epidemic=epidemic,
            **prediction_audit,
        )
        persist_daily_sales()
        return jsonify({
            "ok": True,
            "accepted": False,
            "message": STATUS_LABELS[REJECTED],
            "order": {
                "order_id": order_id,
                "status": REJECTED,
                "status_label": STATUS_LABELS[REJECTED],
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "inventory_before": stock_before,
                "inventory": stock_before,
                "order_quantity": order_quantity,
                "incoming_stock": incoming_stock,
                "future_demand": demand,
                "inventory_level": cancel_report["inventory_level"],
                "reorder_point": cancel_report["reorder_point"],
                "reorder_quantity": cancel_report["reorder_quantity"],
                "alert": "OUT_OF_STOCK" if stock_before <= 0 else "INSUFFICIENT_STOCK",
                "model_mode": prediction_result["mode"],
                "model_version": model_details["model_version"],
                "fallback_used": prediction_result["fallback_used"],
                "prediction_error": prediction_result.get("error"),
                "forecast_date": prediction_audit["forecast_date"],
                "cold_start": prediction_audit["cold_start"],
                "fallback_reason": prediction_audit["fallback_reason"],
            },
            "logs": logs,
            "model": model_details,
        })

    stock_after = set_product_stock(
        warehouse_id,
        product_id,
        available_stock - order_quantity,
    )

    logs.append(_log(
        f"T?n kho m?i = {stock_after} "
        f"(t?n tr??c {stock_before} - b?n {order_quantity} + nh?p {incoming_stock})"
    ))
    report = evaluate_inventory(
        stock=stock_after,
        future_demand=demand,
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
        incoming_stock=incoming_stock,
        category=category,
        region=region,
        units_sold=units_sold,
        inventory_quantity=model_inventory_quantity,
        price=price,
        discount=discount,
        weather_condition=weather_condition,
        promotion=promotion,
        competitor_pricing=competitor_pricing,
        seasonality=seasonality,
        epidemic=epidemic,
    )

    logs.append(_log("Gửi dữ liệu lên Firebase"))
    processing_latency_ms = round(
        (time.perf_counter() - process_started) * 1000
    )
    server_completed_at_ms = round(time.time() * 1000)
    logs.append(_log(
        f"Backend hoàn tất trong {processing_latency_ms} ms"
    ))
    order_snapshot = {
        "order_id": order_id,
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "inventory_before": stock_before,
        "inventory_quantity": model_inventory_quantity,
        "order_quantity": order_quantity,
        "incoming_stock": incoming_stock,
        "inventory": stock_after,
        "future_demand": demand,
        "category": category,
        "region": region,
        "units_sold": units_sold,
        "price": price,
        "discount": discount,
        "weather_condition": weather_condition,
        "promotion": promotion,
        "competitor_pricing": competitor_pricing,
        "seasonality": seasonality,
        "epidemic": epidemic,
        "inventory_level": level,
        "inventory_level_description": report[
            "inventory_level_description"
        ],
        "reorder_point": report["reorder_point"],
        "reorder_quantity": report["reorder_quantity"],
        "reorder_required": report["reorder_required"],
        "alert": alert,
        "processing_latency_ms": processing_latency_ms,
        "prediction_latency_ms": prediction_latency_ms,
        "model_mode": prediction_result["mode"],
        "model_version": model_details["model_version"],
        "fallback_used": prediction_result["fallback_used"],
        "prediction_error": prediction_result.get("error"),
    }
    update_order_status(
        order_id=order_id,
        status=ACCEPTED,
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
        progress=100,
        inventory_level_description=report[
            "inventory_level_description"
        ],
        processed=True,
        processing_logs=logs + [_log(STATUS_LABELS[ACCEPTED])],
        processing_latency_ms=processing_latency_ms,
        prediction_latency_ms=prediction_latency_ms,
        model_mode=prediction_result["mode"],
        model_version=model_details["model_version"],
        fallback_used=prediction_result["fallback_used"],
        prediction_error=prediction_result.get("error"),
        server_completed_at_ms=server_completed_at_ms,
        incoming_stock=incoming_stock,
        category=category,
        region=region,
        units_sold=units_sold,
        inventory_quantity=model_inventory_quantity,
        price=price,
        discount=discount,
        weather_condition=weather_condition,
        promotion=promotion,
        competitor_pricing=competitor_pricing,
        seasonality=seasonality,
        epidemic=epidemic,
        **prediction_audit,
    )
    persist_daily_sales()
    return jsonify({
        "ok": True,
        "accepted": True,
        "message": STATUS_LABELS[ACCEPTED],
        "order": {
            "order_id": order_id,
            "status": ACCEPTED,
            "status_label": STATUS_LABELS[ACCEPTED],
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "inventory_before": stock_before,
            "inventory_quantity": model_inventory_quantity,
            "order_quantity": order_quantity,
            "incoming_stock": incoming_stock,
            "inventory": stock_after,
            "future_demand": demand,
            "category": category,
            "region": region,
            "units_sold": units_sold,
            "price": price,
            "discount": discount,
            "weather_condition": weather_condition,
            "promotion": promotion,
            "competitor_pricing": competitor_pricing,
            "seasonality": seasonality,
            "epidemic": epidemic,
            "inventory_level": level,
            "reorder_point": report["reorder_point"],
            "reorder_quantity": report["reorder_quantity"],
            "alert": alert,
            "model_mode": prediction_result["mode"],
            "model_version": model_details["model_version"],
            "fallback_used": prediction_result["fallback_used"],
            "prediction_error": prediction_result.get("error"),
            "forecast_date": prediction_audit["forecast_date"],
            "cold_start": prediction_audit["cold_start"],
            "fallback_reason": prediction_audit["fallback_reason"],
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


@app.route("/api/inventory/restock", methods=["POST"])
def restock_product():
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
        restock_quantity = int(data.get("restock_quantity", 0))
    except (TypeError, ValueError):
        restock_quantity = 0

    errors = {}
    if not warehouse_id:
        errors["warehouse_id"] = "Không được để trống mã kho."
    if not product_id:
        errors["product_id"] = "Không được để trống mã sản phẩm."
    if restock_quantity <= 0:
        errors["restock_quantity"] = "Số lượng nhập thêm phải lớn hơn 0."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    product_data = get_product_data(warehouse_id, product_id)
    if not product_data:
        return jsonify({
            "ok": False,
            "error": (
                f"Chưa tìm thấy SKU {product_id} trong kho {warehouse_id}. "
                "Hãy dùng chức năng Thêm sản phẩm trước."
            ),
        }), 404

    stock_before = get_product_stock(warehouse_id, product_id)
    stock_after = add_product_stock(
        warehouse_id,
        product_id,
        restock_quantity,
    )
    future_demand = int(product_data.get("future_demand") or 0)
    report = evaluate_inventory(
        stock=stock_after,
        future_demand=future_demand,
        warehouse_id=warehouse_id,
    )
    update_product_inventory_analysis(
        warehouse_id=warehouse_id,
        product_id=product_id,
        future_demand=future_demand,
        inventory_level=report["inventory_level"],
        reorder_point=report["reorder_point"],
        reorder_quantity=report["reorder_quantity"],
        reorder_required=report["reorder_required"],
    )

    return jsonify({
        "ok": True,
        "restock": {
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "stock_before": stock_before,
            "restock_quantity": restock_quantity,
            "stock_after": stock_after,
            "future_demand": future_demand,
            "inventory_level": report["inventory_level"],
            "inventory_level_description": report[
                "inventory_level_description"
            ],
            "reorder_point": report["reorder_point"],
            "reorder_quantity": report["reorder_quantity"],
        },
    })


@app.route("/api/products/rename", methods=["POST"])
def rename_product():
    if FIREBASE_IMPORT_ERROR or rename_product_location is None:
        return jsonify({
            "ok": False,
            "error": "Firebase chưa sẵn sàng để sửa thông tin kho/sản phẩm.",
            "detail": FIREBASE_IMPORT_ERROR,
        }), 503

    data = request.get_json(silent=True) or {}
    old_warehouse_id = str(data.get("old_warehouse_id", "")).strip()
    old_product_id = str(data.get("old_product_id", "")).strip()
    new_warehouse_id = str(data.get("new_warehouse_id", "")).strip()
    new_product_id = str(data.get("new_product_id", "")).strip()

    errors = {}
    if not old_warehouse_id:
        errors["old_warehouse_id"] = "Thiếu mã kho cũ."
    if not old_product_id:
        errors["old_product_id"] = "Thiếu mã sản phẩm cũ."
    if not new_warehouse_id:
        errors["new_warehouse_id"] = "Không được để trống mã kho mới."
    if not new_product_id:
        errors["new_product_id"] = "Không được để trống mã sản phẩm mới."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    try:
        result = rename_product_location(
            old_warehouse_id,
            old_product_id,
            new_warehouse_id,
            new_product_id,
        )
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception as error:
        return jsonify({
            "ok": False,
            "error": f"Backend sửa kho/sản phẩm thất bại: {error}",
        }), 500

    return jsonify({"ok": True, "product": result})


@app.route("/api/warehouses/rename", methods=["POST"])
def rename_warehouse_api():
    if FIREBASE_IMPORT_ERROR or rename_warehouse is None:
        return jsonify({
            "ok": False,
            "error": "Firebase chưa sẵn sàng để sửa tên kho.",
            "detail": FIREBASE_IMPORT_ERROR,
        }), 503

    data = request.get_json(silent=True) or {}
    old_warehouse_id = str(data.get("old_warehouse_id", "")).strip()
    new_warehouse_id = str(data.get("new_warehouse_id", "")).strip()

    errors = {}
    if not old_warehouse_id:
        errors["old_warehouse_id"] = "Thiếu tên kho hiện tại."
    if not new_warehouse_id:
        errors["new_warehouse_id"] = "Tên kho mới không được để trống."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    try:
        result = rename_warehouse(old_warehouse_id, new_warehouse_id)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception as error:
        return jsonify({
            "ok": False,
            "error": f"Backend sửa tên kho thất bại: {error}",
        }), 500

    return jsonify({"ok": True, "warehouse": result})


@app.route("/api/warehouses/delete", methods=["DELETE"])
def delete_warehouse_api():
    if FIREBASE_IMPORT_ERROR or delete_warehouse is None:
        return jsonify({
            "ok": False,
            "error": "Firebase chưa sẵn sàng để xóa kho.",
            "detail": FIREBASE_IMPORT_ERROR,
        }), 503

    data = request.get_json(silent=True) or {}
    warehouse_id = str(data.get("warehouse_id", "")).strip()
    confirmation = str(data.get("confirm", "")).strip()
    if not warehouse_id:
        return jsonify({
            "ok": False,
            "errors": {"warehouse_id": "Tên kho không được để trống."},
        }), 400
    if confirmation != warehouse_id:
        return jsonify({
            "ok": False,
            "error": "Xác nhận xóa kho không hợp lệ.",
        }), 400

    try:
        result = delete_warehouse(warehouse_id)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception as error:
        return jsonify({
            "ok": False,
            "error": f"Backend xóa kho thất bại: {error}",
        }), 500

    return jsonify({"ok": True, "warehouse": result})


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
