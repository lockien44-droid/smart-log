import pandas as pd
import numpy as np


def preprocess_data():

    # ====================================
    # LOAD DATASET
    # ====================================
    try:

        df = pd.read_csv(
            "data/smart_logistics_dataset.csv"
        )

    except FileNotFoundError:

        print(
            "ERROR: Dataset not found"
        )

        return None

    except Exception as e:

        print(
            "ERROR Loading Dataset:",
            e
        )

        return None

    df = df.copy()

    print("\n===== DATASET INFO =====")
    print("Rows:", len(df))
    print("Columns:", len(df.columns))

    # ====================================
    # REQUIRED COLUMNS CHECK
    # ====================================
    required_columns = [
        "inventory_quantity",
        "order_quantity",
        "daily_sales",
        "incoming_stock",
        "lead_time",
        "vehicle_capacity",
        "delivery_status"
    ]

    for col in required_columns:

        if col not in df.columns:

            print(
                f"[WARNING] Missing column: {col}"
            )

            if col == "delivery_status":
                df[col] = "Pending"
            else:
                df[col] = 0

    # ====================================
    # NUMERIC CLEANING ONLY
    # ====================================
    numeric_columns = [
        "inventory_quantity",
        "order_quantity",
        "daily_sales",
        "incoming_stock",
        "lead_time",
        "vehicle_capacity",
        "future_demand"
    ]

    for col in numeric_columns:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

            df[col] = df[col].fillna(0)

    # ====================================
    # DROP UNUSED ID COLUMNS
    # ====================================
    drop_columns = [
        "order_id",
        "warehouse_id",
        "product_id"
    ]

    df.drop(
        columns=[
            c for c in drop_columns
            if c in df.columns
        ],
        inplace=True,
        errors="ignore"
    )

    # ====================================
    # ENCODE STATUS
    # ====================================
    status_map = {
        "Pending": 0,
        "Processing": 1,
        "Shipping": 2,
        "Delivered": 3,
        "Cancelled": 4
    }

    if "delivery_status" in df.columns:

        df["delivery_status"] = (
            df["delivery_status"]
            .astype(str)
            .str.strip()
            .map(status_map)
            .fillna(0)
            .astype(int)
        )

    # ====================================
    # FEATURE ENGINEERING
    # ====================================
    if (
        "order_quantity" in df.columns
        and
        "inventory_quantity" in df.columns
    ):

        df["demand_ratio"] = (
            df["order_quantity"] /
            (df["inventory_quantity"] + 1)
        )

        df["stock_after_order"] = (
            df["inventory_quantity"] -
            df["order_quantity"]
        )

    if (
        "inventory_quantity" in df.columns
        and
        "daily_sales" in df.columns
    ):

        df["inventory_pressure"] = (
            df["inventory_quantity"] /
            (df["daily_sales"] + 1)
        )

        df["days_of_stock"] = (
            df["inventory_quantity"] /
            (df["daily_sales"] + 1)
        )

    if (
        "incoming_stock" in df.columns
        and
        "order_quantity" in df.columns
    ):

        df["stock_gap"] = (
            df["incoming_stock"] -
            df["order_quantity"]
        )

    # ====================================
    # REMOVE INF
    # ====================================
    df.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True
    )

    df.fillna(
        0,
        inplace=True
    )

    # ====================================
    # TYPE SAFETY
    # ====================================
    for col in df.columns:

        if str(df[col].dtype).startswith(
            "float"
        ):

            if col != "lead_time":

                try:
                    df[col] = (
                        df[col]
                        .round()
                        .astype("int64")
                    )

                except Exception:
                    pass

    # ====================================
    # FINAL VALIDATION
    # ====================================
    print("\n===== FINAL CHECK =====")

    print(
        "Rows:",
        len(df)
    )

    print(
        "Columns:",
        len(df.columns)
    )

    print(
        "Missing Values:",
        df.isnull().sum().sum()
    )

    print(
        "\nDataset Ready For AI Model"
    )

    return df


# ====================================
# TEST
# ====================================
if __name__ == "__main__":

    data = preprocess_data()

    if data is not None:

        print(
            "\n===== FIRST 5 ROWS ====="
        )

        print(
            data.head()
        )

        feature_columns = [

            col for col in [

                "demand_ratio",
                "inventory_pressure",
                "stock_gap",
                "days_of_stock",
                "stock_after_order"

            ]

            if col in data.columns
        ]

        if feature_columns:

            print(
                "\n===== FEATURE SAMPLE ====="
            )

            print(
                data[
                    feature_columns
                ].head()
            )