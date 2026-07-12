import os
import time
import traceback
from pathlib import Path

import pandas as pd
import socketio

from app.ai.predictor import get_model_info, predict_demand
from app.inventory_service import evaluate_inventory
from app.firebase.repository import (
    add_product_stock,
    deduct_product_stock,
    get_order,
    get_product_stock,
    record_product_daily_demand,
    record_product_daily_sales,
    set_product_stock,
    update_order_status,
    update_product_inventory_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILE = PROJECT_ROOT / "data" / "processed" / "smart_logistics_runtime.csv"
SERVER_URL = os.environ.get("SIMULATION_SERVER_URL", "http://127.0.0.1:8000")
ROW_DELAY_SECONDS = float(os.environ.get("SIMULATION_ROW_DELAY", "0.05"))

PROCESSING = "processing"
ACCEPTED = "accepted"
REJECTED = "rejected"


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_text(value, default="UNKNOWN"):
    value = str(value if value is not None else "").strip()
    return value or default


def connect_socket():
    try:
        client = socketio.Client(
            reconnection=True,
            reconnection_attempts=10,
            reconnection_delay=2,
        )
        client.connect(SERVER_URL)
        print(f"[SOCKET] Connected: {SERVER_URL}")
        return client
    except Exception as error:
        print("[SOCKET ERROR]", error)
        return None


def process_row(row, sio):
    order_id = safe_text(row.get("order_id"), "SIM_ORDER")
    warehouse_id = safe_text(row.get("warehouse_id"), "S001")
    product_id = safe_text(row.get("product_id"), "P0001")
    order_date = safe_text(row.get("timestamp"), "")

    # Idempotency must be checked before any stock mutation.
    existing_order = get_order(order_id)
    if isinstance(existing_order, dict) and existing_order.get("processed"):
        print(f"[SKIPPED] {order_id} was already processed")
        return

    order_quantity = max(1, safe_int(row.get("order_quantity"), 1))
    source_inventory = max(0, safe_int(row.get("inventory_quantity")))
    units_sold = max(0, safe_int(row.get("units_sold"), order_quantity))
    incoming_stock = max(0, safe_int(row.get("incoming_stock")))

    feature_values = {
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "category": safe_text(row.get("category")),
        "region": safe_text(row.get("region")),
        "inventory_quantity": source_inventory,
        "units_sold": units_sold,
        "actual_demand": row.get("demand"),
        "units_sold_lag_1": row.get("units_sold_lag_1"),
        "units_sold_lag_7": row.get("units_sold_lag_7"),
        "units_sold_rolling_mean_7": row.get(
            "units_sold_rolling_mean_7"
        ),
        "demand_lag_1": row.get("demand_lag_1"),
        "demand_lag_7": row.get("demand_lag_7"),
        "demand_lag_14": row.get("demand_lag_14"),
        "demand_lag_28": row.get("demand_lag_28"),
        "demand_rolling_mean_7": row.get("demand_rolling_mean_7"),
        "demand_rolling_mean_28": row.get("demand_rolling_mean_28"),
        "demand_rolling_std_7": row.get("demand_rolling_std_7"),
        "demand_rolling_std_28": row.get("demand_rolling_std_28"),
        "demand_trend_7_28": row.get("demand_trend_7_28"),
        "incoming_stock": incoming_stock,
        "price": max(0, safe_float(row.get("price"))),
        "discount": max(0, safe_float(row.get("discount"))),
        "weather_condition": safe_text(row.get("weather_condition")),
        "promotion": max(0, min(safe_int(row.get("promotion")), 1)),
        "competitor_pricing": max(
            0,
            safe_float(row.get("competitor_pricing")),
        ),
        "epidemic": max(0, min(safe_int(row.get("epidemic")), 1)),
        "order_date": order_date,
        "return_details": True,
    }

    prediction = predict_demand(**feature_values)
    demand = max(0, safe_int(prediction.get("future_demand")))
    model_info = get_model_info()

    current_stock = get_product_stock(warehouse_id, product_id)
    if current_stock is None:
        current_stock = set_product_stock(
            warehouse_id,
            product_id,
            source_inventory,
        )
    inventory_before = current_stock

    if incoming_stock > 0:
        current_stock = add_product_stock(
            warehouse_id,
            product_id,
            incoming_stock,
        )

    try:
        inventory_after = deduct_product_stock(
            warehouse_id,
            product_id,
            order_quantity,
            order_id=order_id,
        )
        status = ACCEPTED
        progress = 100
        insufficient_stock = False
    except ValueError:
        inventory_after = current_stock
        status = REJECTED
        progress = 0
        insufficient_stock = True

    report = evaluate_inventory(
        stock=inventory_after,
        warehouse_id=warehouse_id,
        future_demand=demand,
    )
    inventory_level = report["inventory_level"]
    alert = {
        "NORMAL": "NORMAL",
        "LOW": "LOW_STOCK",
        "CRITICAL": "REORDER_REQUIRED",
        "OUT_OF_STOCK": "OUT_OF_STOCK",
    }[inventory_level]
    if insufficient_stock:
        alert = "INSUFFICIENT_STOCK"

    update_product_inventory_analysis(
        warehouse_id=warehouse_id,
        product_id=product_id,
        future_demand=demand,
        inventory_level=inventory_level,
        reorder_point=report["reorder_point"],
        reorder_quantity=report["reorder_quantity"],
        reorder_required=report["reorder_required"],
        incoming_stock=incoming_stock,
        category=feature_values["category"],
        region=feature_values["region"],
        units_sold=units_sold,
        inventory_quantity=inventory_before,
        price=feature_values["price"],
        discount=feature_values["discount"],
        weather_condition=feature_values["weather_condition"],
        promotion=feature_values["promotion"],
        competitor_pricing=feature_values["competitor_pricing"],
        seasonality=safe_text(row.get("seasonality")),
        epidemic=feature_values["epidemic"],
    )
    record_product_daily_sales(
        warehouse_id,
        product_id,
        order_date,
        units_sold,
    )
    if pd.notna(row.get("demand")):
        record_product_daily_demand(
            warehouse_id, product_id, order_date, row.get("demand")
        )

    update_order_status(
        order_id=order_id,
        status=status,
        inventory=inventory_after,
        inventory_before=inventory_before,
        demand=demand,
        inventory_level=inventory_level,
        warehouse_id=warehouse_id,
        product_id=product_id,
        order_quantity=order_quantity,
        incoming_stock=incoming_stock,
        units_sold=units_sold,
        inventory_quantity=inventory_before,
        category=feature_values["category"],
        region=feature_values["region"],
        price=feature_values["price"],
        discount=feature_values["discount"],
        weather_condition=feature_values["weather_condition"],
        promotion=feature_values["promotion"],
        competitor_pricing=feature_values["competitor_pricing"],
        seasonality=safe_text(row.get("seasonality")),
        epidemic=feature_values["epidemic"],
        reorder_required=report["reorder_required"],
        reorder_point=report["reorder_point"],
        reorder_quantity=report["reorder_quantity"],
        inventory_level_description=report[
            "inventory_level_description"
        ],
        alert=alert,
        progress=progress,
        processed=True,
        model_mode=prediction.get("mode"),
        model_version=model_info.get("model_version"),
        fallback_used=prediction.get("fallback_used", False),
        prediction_error=prediction.get("error"),
        order_date=prediction.get("observation_date", order_date),
        forecast_date=prediction.get("forecast_date"),
        units_sold_lag_1=feature_values["units_sold_lag_1"],
        units_sold_lag_7=feature_values["units_sold_lag_7"],
        units_sold_rolling_mean_7=feature_values[
            "units_sold_rolling_mean_7"
        ],
        cold_start=prediction.get("cold_start", False),
        fallback_reason=prediction.get("fallback_reason"),
        missing_history=prediction.get("missing_history"),
        unknown_categories=prediction.get("unknown_categories"),
    )

    payload = {
        "order_id": order_id,
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "status": status,
        "progress": progress,
        "inventory": inventory_after,
        "inventory_before": inventory_before,
        "order_quantity": order_quantity,
        "future_demand": demand,
        "inventory_level": inventory_level,
        "inventory_level_description": report[
            "inventory_level_description"
        ],
        "reorder_required": report["reorder_required"],
        "reorder_point": report["reorder_point"],
        "reorder_quantity": report["reorder_quantity"],
        "alert": alert,
        "timestamp": order_date,
        "forecast_date": prediction.get("forecast_date"),
        "model_mode": prediction.get("mode"),
    }
    if sio is not None and sio.connected:
        sio.emit("status_update", payload)

    print(
        f"[{order_id}] {status} | Inventory={inventory_after} | "
        f"Demand(t+1)={demand} | Model={prediction.get('mode')}"
    )


def main():
    print("=" * 60)
    print("SMART LOGISTICS t+1 SIMULATION STARTED")
    print("=" * 60)

    if not RUNTIME_FILE.exists():
        raise FileNotFoundError(
            f"Missing {RUNTIME_FILE}. Run python -m ml.prepare_data first."
        )

    sio = connect_socket()
    df = pd.read_csv(RUNTIME_FILE)
    print(f"[SYSTEM] Orders loaded: {len(df):,}")

    for row in df.to_dict("records"):
        try:
            process_row(row, sio)
            time.sleep(max(0, ROW_DELAY_SECONDS))
        except Exception:
            print("\n========== ROW ERROR ==========")
            traceback.print_exc()
            print("ROW DATA:", row)
            print("===============================\n")

    if sio is not None and sio.connected:
        sio.disconnect()
    print("\nSYSTEM FINISHED")


if __name__ == "__main__":
    main()
