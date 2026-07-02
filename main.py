import time
import uuid
import traceback
from datetime import datetime

import pandas as pd
import socketio

from predictor import predict_demand

from inventory_manager import (
    check_inventory,
    update_inventory,
    add_stock,
    get_stock
)

from firebase_manager import (
    update_order_status,
    clear_orders
)

# ==========================================
# SAFE FUNCTIONS
# ==========================================

def safe_int(value, default=0):
    try:

        if isinstance(value, dict):

            if "value" in value:
                value = value["value"]

            elif len(value) > 0:
                value = list(value.values())[0]

            else:
                return default

        return int(float(value))

    except Exception:
        return default


def safe_float(value, default=0.0):
    try:

        if isinstance(value, dict):

            if "value" in value:
                value = value["value"]

            elif len(value) > 0:
                value = list(value.values())[0]

            else:
                return default

        return float(value)

    except Exception:
        return default


def safe_dict(obj):

    if isinstance(obj, dict):
        return obj

    return {}


# ==========================================
# MAIN
# ==========================================

def main():

    print("=" * 60)
    print("SMART LOGISTICS SYSTEM STARTED")
    print("=" * 60)

    # ======================================
    # FIREBASE RESET
    # ======================================

    try:

        clear_orders()

        print(
            "[SYSTEM] Firebase cleared"
        )

    except Exception as e:

        print(
            "[FIREBASE RESET ERROR]",
            e
        )

    # ======================================
    # SOCKET
    # ======================================

    sio = None

    try:

        sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=10,
            reconnection_delay=2
        )

        sio.connect(
            "http://127.0.0.1:8000"
        )

        print(
            "[SOCKET] Connected"
        )

    except Exception as e:

        print(
            "[SOCKET ERROR]",
            e
        )

        sio = None

    # ======================================
    # DATASET
    # ======================================

    try:

        df = pd.read_csv(
            "data/smart_logistics_dataset.csv"
        )

        df.fillna(
            0,
            inplace=True
        )

    except Exception as e:

        print(
            "[DATASET ERROR]",
            e
        )

        return

    print(
        f"[SYSTEM] Orders Loaded: {len(df)}"
    )

    progress_map = {
        "Pending": 10,
        "Processing": 30,
        "Shipping": 70,
        "Delivered": 100,
        "Cancelled": 0
    }

    # ======================================
    # PROCESS ORDERS
    # ======================================

    for row in df.to_dict("records"):

        try:

            order_id = str(
                row.get(
                    "order_id",
                    uuid.uuid4()
                )
            )

            warehouse_id = str(
                row.get(
                    "warehouse_id",
                    "WH01"
                )
            )

            product_id = str(
                row.get(
                    "product_id",
                    "PRD001"
                )
            )

            inventory_qty = safe_int(
                row.get(
                    "inventory_quantity",
                    0
                )
            )

            order_qty = safe_int(
                row.get(
                    "order_quantity",
                    0
                )
            )

            daily_sales = safe_int(
                row.get(
                    "daily_sales",
                    0
                )
            )

            incoming_stock = safe_int(
                row.get(
                    "incoming_stock",
                    0
                )
            )

            lead_time = safe_float(
                row.get(
                    "lead_time",
                    1
                )
            )

            vehicle_capacity = safe_int(
                row.get(
                    "vehicle_capacity",
                    100
                )
            )

            status = str(
                row.get(
                    "delivery_status",
                    "Pending"
                )
            )
            # ==================================
            # AI DEMAND PREDICTION
            # ==================================

            try:

                prediction = predict_demand(
                    inventory_quantity=inventory_qty,
                    order_quantity=order_qty,
                    daily_sales=daily_sales,
                    incoming_stock=incoming_stock,
                    lead_time=lead_time,
                    delivery_status=status,
                    vehicle_capacity=vehicle_capacity
                )

                if isinstance(
                    prediction,
                    dict
                ):

                    demand = safe_int(
                        prediction.get(
                            "predicted_demand",
                            prediction.get(
                                "demand",
                                prediction.get(
                                    "value",
                                    0
                                )
                            )
                        )
                    )

                else:

                    demand = safe_int(
                        prediction
                    )

            except Exception as e:

                print(
                    "[PREDICT ERROR]",
                    e
                )

                demand = 0

            # ==================================
            # INVENTORY UPDATE
            # ==================================

            try:

                update_inventory(
                    warehouse_id,
                    order_qty
                )

                add_stock(
                    warehouse_id,
                    incoming_stock
                )

                inventory_qty = get_stock(
                    warehouse_id
                )

            except Exception as e:

                print(
                    "[INVENTORY ERROR]",
                    e
                )

                inventory_qty = 0

            # ==================================
            # INVENTORY CHECK
            # ==================================

            try:

                inventory_report = (
                    check_inventory(
                        warehouse_id=warehouse_id,
                        future_demand=demand,
                        lead_time=lead_time
                    ) or {}
                )

            except Exception as e:

                print(
                    "[CHECK INVENTORY ERROR]",
                    e
                )

                inventory_report = {}

            inventory_level = str(
                inventory_report.get(
                    "inventory_level",
                    "NORMAL"
                )
            )

            reorder_required = bool(
                inventory_report.get(
                    "reorder_required",
                    False
                )
            )

            reorder_point = safe_int(
                inventory_report.get(
                    "reorder_point",
                    demand + 50
                )
            )

            reorder_quantity = safe_int(
                inventory_report.get(
                    "reorder_quantity",
                    0
                )
            )

            inventory_level_description = str(
                inventory_report.get(
                    "inventory_level_description",
                    {
                        "NORMAL": "Tồn kho an toàn",
                        "LOW": "Tồn kho thấp",
                        "CRITICAL": "Tồn kho rất thấp",
                        "OUT_OF_STOCK": "Hết hàng"
                    }.get(inventory_level, "Không xác định")
                )
            )

            # ==================================
            # INVENTORY ALERT LOGIC
            # ==================================

            alert = "NORMAL"

            if inventory_level == "OUT_OF_STOCK":

                alert = "OUT_OF_STOCK"

            elif inventory_level == "CRITICAL":

                alert = "REORDER_REQUIRED"

            elif inventory_level == "LOW":

                alert = "LOW_STOCK"

            # ==================================
            # INVENTORY STATUS RULES
            # ==================================

            if inventory_level == "OUT_OF_STOCK":

                status = "Cancelled"

            elif inventory_level == "CRITICAL":

                status = "Processing"

            elif inventory_level == "LOW":

                status = "Processing"

            # ==================================
            # PROGRESS
            # ==================================

            progress = progress_map.get(
                status,
                0
            )
            # ==================================
            # PAYLOAD
            # ==================================

            payload = {

                "event_id": str(
                    uuid.uuid4()
                ),

                "order_id": order_id,
                "warehouse_id": warehouse_id,
                "product_id": product_id,

                "status": status,
                "progress": progress,

                "inventory": inventory_qty,
                "order_quantity": order_qty,
                "demand": demand,
                "future_demand": demand,

                "inventory_level": inventory_level,
                "inventory_level_description": inventory_level_description,

                "daily_sales": daily_sales,
                "incoming_stock": incoming_stock,
                "lead_time": lead_time,
                "vehicle_capacity": vehicle_capacity,

                "alert": alert,

                "reorder_required": reorder_required,
                "reorder_point": reorder_point,
                "reorder_quantity": reorder_quantity,

                "timestamp": datetime.now().isoformat()
            }

            # ==================================
            # FIREBASE UPDATE
            # ==================================

            try:

                update_order_status(

                    order_id=order_id,
                    status=status,
                    inventory=inventory_qty,
                    demand=demand,

                    inventory_level=inventory_level,

                    warehouse_id=warehouse_id,
                    product_id=product_id,

                    alert=alert,

                    progress=progress,

                    reorder_required=reorder_required,
                    reorder_point=reorder_point,
                    reorder_quantity=reorder_quantity,
                    inventory_level_description=inventory_level_description,
                    order_quantity=order_qty,

                    event_id=payload["event_id"]
                )

            except Exception as e:

                print(
                    "[FIREBASE ERROR]",
                    e
                )

            # ==================================
            # SOCKET EMIT
            # ==================================

            try:

                if (
                    sio is not None
                    and sio.connected
                ):

                    sio.emit(
                        "status_update",
                        payload
                    )

            except Exception as e:

                print(
                    "[SOCKET ERROR]",
                    e
                )

            # ==================================
            # CONSOLE LOG
            # ==================================

            print(

                f"[{order_id}] "

                f"{status} | "

                f"Inventory={inventory_qty} | "

                f"Demand={demand} | "

                f"Alert={alert} | "

            )

            time.sleep(
                0.05
            )

        except Exception:

            print(
                "\n========== ROW ERROR =========="
            )

            traceback.print_exc()

            try:

                print(
                    "ROW DATA:",
                    row
                )

            except Exception:
                pass

            print(
                "===============================\n"
            )

    # ==================================
    # CLEANUP
    # ==================================

    try:

        if (
            sio is not None
            and sio.connected
        ):

            sio.disconnect()

    except Exception:
        pass

    print(
        "\nSYSTEM FINISHED"
    )


# ==================================
# START
# ==================================

if __name__ == "__main__":

    main()
