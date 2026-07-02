import os
import joblib
import pandas as pd

MODEL_PATH = "models/random_forest_model.pkl"

model = None

FEATURE_COLUMNS = [
    "inventory_quantity",
    "order_quantity",
    "daily_sales",
    "incoming_stock",
    "lead_time",
    "delivery_status",
    "vehicle_capacity",
    "demand_ratio",
    "inventory_pressure",
    "stock_gap"
]

# =====================================
# LOAD MODEL
# =====================================

if os.path.exists(MODEL_PATH):

    try:

        data = joblib.load(MODEL_PATH)

        if isinstance(data, dict):

            model = data.get("model")

            FEATURE_COLUMNS = data.get(
                "features",
                FEATURE_COLUMNS
            )

        else:

            model = data

        print(
            "[AI] Model Loaded Successfully"
        )

    except Exception as e:

        print(
            "[AI] Model Load Error:",
            e
        )

        model = None

else:

    print(
        "[AI] Model Not Found -> Using Fallback"
    )


# =====================================
# SAFE NUMBER
# =====================================

def safe_number(value, default=0):

    try:

        if value is None:
            return float(default)

        if isinstance(value, dict):

            if "value" in value:

                value = value["value"]

            elif len(value) > 0:

                value = list(
                    value.values()
                )[0]

            else:

                return float(default)

        return float(value)

    except Exception:

        return float(default)


# =====================================
# FEATURE BUILDER
# =====================================

def build_features(
    inventory_quantity,
    order_quantity,
    daily_sales,
    incoming_stock,
    lead_time,
    delivery_status,
    vehicle_capacity
):

    delivery_status = {
        "Pending": 0,
        "Processing": 1,
        "Shipping": 2,
        "Delivered": 3,
        "Cancelled": 4
    }.get(
        str(delivery_status),
        0
    )

    inventory_quantity = max(
        0,
        safe_number(
            inventory_quantity
        )
    )

    order_quantity = max(
        0,
        safe_number(
            order_quantity
        )
    )

    daily_sales = max(
        0,
        safe_number(
            daily_sales
        )
    )

    incoming_stock = max(
        0,
        safe_number(
            incoming_stock
        )
    )

    lead_time = max(
        0,
        safe_number(
            lead_time
        )
    )

    vehicle_capacity = max(
        0,
        safe_number(
            vehicle_capacity
        )
    )

    demand_ratio = (
        order_quantity /
        (inventory_quantity + 1)
    )

    estimated_demand = (
         daily_sales *
         lead_time
)

    inventory_pressure = (
         inventory_quantity /
         (estimated_demand + 1)
)

    stock_gap = (
        incoming_stock -
        order_quantity
    )

    return {
        "inventory_quantity":
            inventory_quantity,

        "order_quantity":
            order_quantity,

        "daily_sales":
            daily_sales,

        "incoming_stock":
            incoming_stock,

        "lead_time":
            lead_time,

        "delivery_status":
            delivery_status,

        "vehicle_capacity":
            vehicle_capacity,

        "demand_ratio":
            demand_ratio,

        "inventory_pressure":
            inventory_pressure,

        "stock_gap":
            stock_gap
    }


# =====================================
# FALLBACK
# =====================================

def fallback(
    daily_sales,
    order_quantity,
    incoming_stock
):

    daily_sales = safe_number(
        daily_sales
    )

    order_quantity = safe_number(
        order_quantity
    )

    incoming_stock = safe_number(
        incoming_stock
    )

    value = (
        daily_sales * 0.6 +
        order_quantity * 0.3 +
        incoming_stock * 0.1
    )

    return max(
        0,
        int(round(value))
    )


# =====================================
# MAIN PREDICT FUNCTION
# =====================================

def predict_demand(**kwargs):

    try:

        features = build_features(
            inventory_quantity=kwargs.get(
                "inventory_quantity",
                0
            ),

            order_quantity=kwargs.get(
                "order_quantity",
                0
            ),

            daily_sales=kwargs.get(
                "daily_sales",
                0
            ),

            incoming_stock=kwargs.get(
                "incoming_stock",
                0
            ),

            lead_time=kwargs.get(
                "lead_time",
                0
            ),

            delivery_status=kwargs.get(
                "delivery_status",
                "Pending"
            ),

            vehicle_capacity=kwargs.get(
                "vehicle_capacity",
                0
            )
        )

        # =========================
        # NO MODEL
        # =========================

        if model is None:

            return fallback(
                kwargs.get(
                    "daily_sales",
                    0
                ),

                kwargs.get(
                    "order_quantity",
                    0
                ),

                kwargs.get(
                    "incoming_stock",
                    0
                )
            )

        # =========================
        # MODEL PREDICT
        # =========================

        df = pd.DataFrame(
            [features]
        )

        df = df.reindex(
            columns=FEATURE_COLUMNS,
            fill_value=0
        )

        df = df.astype(
            float
        )

        prediction = model.predict(
            df
        )

        if prediction is None:

            return 0

        value = float(
            prediction[0]
        )

        value = int(
            round(value)
        )

        return max(
            0,
            min(
                value,
                100000
            )
        )

    except Exception as e:

        print(
            "[AI ERROR]",
            e
        )

        return fallback(
            kwargs.get(
                "daily_sales",
                0
            ),

            kwargs.get(
                "order_quantity",
                0
            ),

            kwargs.get(
                "incoming_stock",
                0
            )
        )