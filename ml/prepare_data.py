from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "kaggle_demand"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_FILE = PROCESSED_DATA_DIR / "kaggle_demand_training.csv"
RUNTIME_OUTPUT_FILE = PROCESSED_DATA_DIR / "smart_logistics_runtime.csv"
FORECAST_HORIZON_DAYS = 7
RUNTIME_SAMPLE_SIZE = 1000


def find_source_csv():
    preferred = RAW_DATA_DIR / "train.csv"
    if preferred.exists():
        return preferred

    csv_files = sorted(RAW_DATA_DIR.rglob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            "No Kaggle CSV found. Run: py download_kaggle_data.py"
        )

    return csv_files[0]


def normalize_columns(df):
    normalized = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in df.columns
    }

    aliases = {
        "date": ["date"],
        "warehouse_id": ["store_id", "store", "warehouse_id"],
        "product_id": ["product_id", "product", "item_id", "item"],
        "inventory_quantity": [
            "inventory_level",
            "inventory_quantity",
            "inventory",
        ],
        "daily_sales": ["units_sold", "sales", "quantity"],
        "incoming_stock": [
            "units_ordered",
            "incoming_stock",
            "ordered_quantity",
        ],
        "price": ["price"],
        "discount": ["discount"],
        "promotion": ["promotion", "promo"],
        "holiday": ["holiday"],
    }

    rename_map = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in normalized:
                rename_map[normalized[candidate]] = target
                break

    return df.rename(columns=rename_map)


def prepare_dataset():
    source_file = find_source_csv()
    print(f"[DATA] Reading: {source_file}")

    df = pd.read_csv(source_file)
    df = normalize_columns(df)

    required = [
        "date",
        "warehouse_id",
        "product_id",
        "daily_sales",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required Kaggle columns: {missing}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "warehouse_id", "product_id"])

    numeric_columns = [
        "inventory_quantity",
        "daily_sales",
        "incoming_stock",
        "price",
        "discount",
        "promotion",
        "holiday",
    ]
    for column in numeric_columns:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    df["warehouse_id"] = df["warehouse_id"].astype(str)
    df["product_id"] = df["product_id"].astype(str)
    df["warehouse_code"] = pd.to_numeric(
        df["warehouse_id"].str.extract(r"(\d+)")[0],
        errors="coerce",
    ).fillna(0)
    df["product_code"] = pd.to_numeric(
        df["product_id"].str.extract(r"(\d+)")[0],
        errors="coerce",
    ).fillna(0)
    df = df.sort_values(["warehouse_id", "product_id", "date"])

    group_keys = ["warehouse_id", "product_id"]
    sales_group = df.groupby(group_keys)["daily_sales"]

    df["sales_lag_1"] = sales_group.shift(1)
    df["sales_lag_7"] = sales_group.shift(7)
    df["sales_lag_14"] = sales_group.shift(14)
    df["sales_mean_7"] = sales_group.transform(
        lambda values: values.shift(1).rolling(7).mean()
    )
    df["sales_mean_30"] = sales_group.transform(
        lambda values: values.shift(1).rolling(30).mean()
    )

    # Target: total actual units sold in the next seven days.
    reversed_sales = df.groupby(group_keys)["daily_sales"].transform(
        lambda values: (
            values.iloc[::-1]
            .shift(1)
            .rolling(FORECAST_HORIZON_DAYS)
            .sum()
            .iloc[::-1]
        )
    )
    df["future_demand"] = reversed_sales

    df["day_of_week"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    model_columns = [
        "date",
        "warehouse_id",
        "product_id",
        "warehouse_code",
        "product_code",
        "inventory_quantity",
        "daily_sales",
        "incoming_stock",
        "price",
        "discount",
        "promotion",
        "holiday",
        "sales_lag_1",
        "sales_lag_7",
        "sales_lag_14",
        "sales_mean_7",
        "sales_mean_30",
        "day_of_week",
        "month",
        "is_weekend",
        "future_demand",
    ]

    df = df[model_columns].dropna()
    df = df[df["future_demand"] >= 0]

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    # A smaller operational dataset for main.py and the realtime dashboard.
    sample_positions = np.linspace(
        0,
        len(df) - 1,
        RUNTIME_SAMPLE_SIZE,
        dtype=int,
    )
    runtime = df.iloc[sample_positions].copy().reset_index(drop=True)
    runtime["timestamp"] = runtime["date"]
    runtime["order_id"] = [
        f"KAGGLE_ORD{index + 1:05d}"
        for index in range(len(runtime))
    ]
    runtime["order_quantity"] = (
        runtime["daily_sales"].mul(0.30).round().clip(lower=1).astype(int)
    )
    runtime["incoming_stock"] = (
        runtime["sales_mean_7"].round().clip(lower=0).astype(int)
    )
    reorder_bases = runtime["future_demand"].add(50)
    inventory_factors = np.resize(
        np.array([1.25, 0.75, 0.25, 0.0]),
        len(runtime),
    )
    runtime["inventory_quantity"] = (
        reorder_bases.mul(inventory_factors).round().clip(lower=0).astype(int)
    )
    runtime["lead_time"] = (
        runtime["product_code"].astype(int).mod(7).add(1)
    )
    runtime["vehicle_capacity"] = 1000
    statuses = ["Pending", "Processing", "Shipping", "Delivered"]
    runtime["delivery_status"] = [
        statuses[index % len(statuses)]
        for index in range(len(runtime))
    ]
    runtime["warehouse_id"] = (
        "WH" + runtime["warehouse_code"].astype(int).astype(str).str.zfill(2)
    )
    runtime["product_id"] = (
        "PRD" + runtime["product_code"].astype(int).astype(str).str.zfill(3)
    )

    runtime_columns = [
        "timestamp",
        "order_id",
        "warehouse_id",
        "product_id",
        "inventory_quantity",
        "order_quantity",
        "daily_sales",
        "incoming_stock",
        "lead_time",
        "vehicle_capacity",
        "delivery_status",
        "future_demand",
    ]
    runtime[runtime_columns].to_csv(RUNTIME_OUTPUT_FILE, index=False)

    print(f"[DATA] Source rows: {len(pd.read_csv(source_file)):,}")
    print(f"[DATA] Training rows: {len(df):,}")
    print(f"[DATA] Warehouses/stores: {df['warehouse_id'].nunique()}")
    print(f"[DATA] Products: {df['product_id'].nunique()}")
    print(f"[DATA] Output: {OUTPUT_FILE}")
    print(f"[DATA] Runtime demo: {RUNTIME_OUTPUT_FILE}")

    return df


if __name__ == "__main__":
    prepare_dataset()
