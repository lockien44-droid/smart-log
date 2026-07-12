import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from ml.schema import (
    FEATURES,
    FORECAST_HORIZON_DAYS,
    HISTORY_WINDOW_DAYS,
    PROCESSED_SCHEMA_VERSION,
    TARGET,
    seasonality_from_month,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RAW_SOURCE_FILE = RAW_DATA_DIR / "demand_forecasting.csv"
LEGACY_RAW_SOURCE_FILE = RAW_DATA_DIR / "kaggle_original.csv"
LEGACY_RAW_DATA_DIR = RAW_DATA_DIR / "kaggle_demand"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
TRAIN_FILE = PROCESSED_DATA_DIR / "train.csv"
TEST_FILE = PROCESSED_DATA_DIR / "test.csv"
OUTPUT_FILE = PROCESSED_DATA_DIR / "kaggle_demand_training.csv"
PRESENTATION_OUTPUT_FILE = PROCESSED_DATA_DIR / "demand_forecasting_presentation.csv"
RUNTIME_OUTPUT_FILE = PROCESSED_DATA_DIR / "smart_logistics_runtime.csv"
DATASET_METADATA_FILE = PROCESSED_DATA_DIR / "dataset_metadata.json"
TRAIN_TEST_GAP_DAYS = FORECAST_HORIZON_DAYS
RUNTIME_SAMPLE_SIZE = 1000

ENTITY_COLUMNS = ["warehouse_id", "product_id"]


def canonical_column_name(column):
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(column).strip().lower(),
    ).strip("_")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_source_csv():
    if RAW_SOURCE_FILE.exists():
        return RAW_SOURCE_FILE
    if LEGACY_RAW_SOURCE_FILE.exists():
        return LEGACY_RAW_SOURCE_FILE

    legacy_preferred = LEGACY_RAW_DATA_DIR / "train.csv"
    if legacy_preferred.exists():
        return legacy_preferred

    csv_files = sorted(RAW_DATA_DIR.rglob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            "No Kaggle CSV found. Put demand_forecasting.csv in data/raw."
        )
    return csv_files[0]


def normalize_columns(df):
    normalized = {
        canonical_column_name(column): column
        for column in df.columns
    }
    aliases = {
        "date": ["date"],
        "warehouse_id": ["store_id", "store", "warehouse_id"],
        "product_id": ["product_id", "product", "item_id", "item"],
        "category": ["category"],
        "region": ["region"],
        "inventory_quantity": [
            "inventory_level",
            "inventory_quantity",
            "inventory",
        ],
        "units_sold": ["units_sold", "sales", "quantity"],
        "incoming_stock": [
            "units_ordered",
            "incoming_stock",
            "ordered_quantity",
        ],
        "price": ["price"],
        "discount": ["discount"],
        "weather_condition": ["weather_condition", "weather"],
        "promotion": ["promotion", "promo", "is_promotion"],
        "competitor_pricing": ["competitor_pricing"],
        "seasonality": ["seasonality", "season"],
        "epidemic": ["epidemic"],
        "demand": ["demand"],
    }

    rename_map = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in normalized:
                rename_map[normalized[candidate]] = target
                break
    return df.rename(columns=rename_map)


def clean_source_dataframe(raw_df):
    df = normalize_columns(raw_df.copy())
    required = [
        "date",
        "warehouse_id",
        "product_id",
        "category",
        "region",
        "inventory_quantity",
        "units_sold",
        "incoming_stock",
        "price",
        "discount",
        "weather_condition",
        "promotion",
        "competitor_pricing",
        "seasonality",
        "epidemic",
        "demand",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required Kaggle columns: {missing}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date", *ENTITY_COLUMNS])
    for column in ENTITY_COLUMNS:
        df[column] = df[column].astype(str).str.strip()
        df = df[df[column] != ""]

    categorical_columns = [
        "category",
        "region",
        "weather_condition",
        "seasonality",
    ]
    numeric_columns = [
        "inventory_quantity",
        "units_sold",
        "incoming_stock",
        "price",
        "discount",
        "promotion",
        "competitor_pricing",
        "epidemic",
        "demand",
    ]

    for column in categorical_columns:
        df[column] = df[column].fillna("UNKNOWN").astype(str).str.strip()
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df.dropna(subset=numeric_columns)

    non_negative_columns = [
        "inventory_quantity",
        "units_sold",
        "incoming_stock",
        "price",
        "discount",
        "competitor_pricing",
        "demand",
    ]
    for column in non_negative_columns:
        df = df[df[column] >= 0]

    df["promotion"] = df["promotion"].clip(lower=0, upper=1).astype(int)
    df["epidemic"] = df["epidemic"].clip(lower=0, upper=1).astype(int)

    duplicate_mask = df.duplicated([*ENTITY_COLUMNS, "date"], keep=False)
    if duplicate_mask.any():
        raise ValueError(
            "Duplicate daily warehouse/product rows found: "
            f"{int(duplicate_mask.sum())}"
        )
    return df.sort_values([*ENTITY_COLUMNS, "date"]).reset_index(drop=True)


def _calendar_rolling_stat(df, value_column, window_days, statistic):
    values = pd.Series(np.nan, index=df.index, dtype=float)
    for _, group in df.groupby(ENTITY_COLUMNS, sort=False):
        ordered = group.sort_values("date")
        series = ordered.set_index("date")[value_column]
        rolling = series.rolling(
            f"{window_days}D",
            min_periods=window_days,
        )
        result = rolling.mean() if statistic == "mean" else rolling.std()
        values.loc[ordered.index] = result.to_numpy()
    return values


def _merge_exact_lag(df, source_df, value_column, lag_days, output_column):
    lookup = source_df[[*ENTITY_COLUMNS, "date", value_column]].rename(
        columns={value_column: output_column}
    )
    lookup["forecast_date"] = lookup["date"] + pd.Timedelta(days=lag_days)
    return df.merge(
        lookup.drop(columns=["date"]),
        on=[*ENTITY_COLUMNS, "forecast_date"],
        how="left",
        validate="one_to_one",
    )


def engineer_clean_dataframe(source_df):
    df = source_df.copy()
    df["forecast_date"] = df["date"] + pd.Timedelta(
        days=FORECAST_HORIZON_DAYS
    )
    target_lookup = df[[*ENTITY_COLUMNS, "date", "demand"]].rename(
        columns={"date": "forecast_date", "demand": TARGET}
    )
    df = df.merge(
        target_lookup,
        on=[*ENTITY_COLUMNS, "forecast_date"],
        how="left",
        validate="one_to_one",
    )

    df["forecast_day_of_week"] = df["forecast_date"].dt.dayofweek
    df["forecast_month"] = df["forecast_date"].dt.month
    df["forecast_is_weekend"] = (
        df["forecast_day_of_week"] >= 5
    ).astype(int)
    df["forecast_seasonality"] = df["forecast_month"].map(
        seasonality_from_month
    )

    # All history features use data available through observation day t.
    # Their lag number is relative to forecast day t+1.
    df["units_sold_lag_1"] = df["units_sold"]
    df["units_sold_rolling_mean_7"] = _calendar_rolling_stat(
        df, "units_sold", 7, "mean"
    )
    df = _merge_exact_lag(
        df, source_df, "units_sold", 7, "units_sold_lag_7"
    )

    df["demand_lag_1"] = df["demand"]
    for lag_days in (7, 14, 28):
        df = _merge_exact_lag(
            df,
            source_df,
            "demand",
            lag_days,
            f"demand_lag_{lag_days}",
        )
    for window_days in (7, 28):
        df[f"demand_rolling_mean_{window_days}"] = _calendar_rolling_stat(
            df,
            "demand",
            window_days,
            "mean",
        )
        df[f"demand_rolling_std_{window_days}"] = _calendar_rolling_stat(
            df,
            "demand",
            window_days,
            "std",
        )

    df["demand_trend_7_28"] = (
        df["demand_rolling_mean_7"] - df["demand_rolling_mean_28"]
    )
    df["inventory_to_demand_ratio"] = (
        df["inventory_quantity"] / df["demand_lag_1"].clip(lower=1)
    )
    df["price_vs_competitor_ratio"] = (
        df["price"] / df["competitor_pricing"].clip(lower=0.01)
    )

    model_columns = [
        "date",
        "forecast_date",
        "warehouse_id",
        "product_id",
        "category",
        "region",
        "weather_condition",
        "seasonality",
        "forecast_seasonality",
        "forecast_day_of_week",
        "forecast_month",
        "forecast_is_weekend",
        "inventory_quantity",
        "units_sold",
        "units_sold_lag_1",
        "units_sold_lag_7",
        "units_sold_rolling_mean_7",
        "incoming_stock",
        "price",
        "discount",
        "promotion",
        "competitor_pricing",
        "epidemic",
        "demand",
        "demand_lag_1",
        "demand_lag_7",
        "demand_lag_14",
        "demand_lag_28",
        "demand_rolling_mean_7",
        "demand_rolling_mean_28",
        "demand_rolling_std_7",
        "demand_rolling_std_28",
        "demand_trend_7_28",
        "inventory_to_demand_ratio",
        "price_vs_competitor_ratio",
        TARGET,
    ]
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df[model_columns].dropna(
        subset=["date", "forecast_date", TARGET, *FEATURES]
    )
    df = df[df[TARGET] >= 0]
    return df.sort_values(
        ["forecast_date", *ENTITY_COLUMNS]
    ).reset_index(drop=True)


def engineer_features(raw_df):
    return engineer_clean_dataframe(clean_source_dataframe(raw_df))


def split_by_forecast_date(df):
    unique_dates = np.sort(df["forecast_date"].unique())
    if len(unique_dates) < 3:
        raise ValueError("At least three forecast dates are required to split data.")
    cutoff_index = min(
        max(int(len(unique_dates) * 0.80), 1),
        len(unique_dates) - 1,
    )
    cutoff_date = pd.Timestamp(unique_dates[cutoff_index])
    gap_start_date = cutoff_date - pd.Timedelta(days=TRAIN_TEST_GAP_DAYS)
    train_df = df[df["forecast_date"] < gap_start_date].copy()
    gap_df = df[
        (df["forecast_date"] >= gap_start_date)
        & (df["forecast_date"] < cutoff_date)
    ].copy()
    test_df = df[df["forecast_date"] >= cutoff_date].copy()
    if train_df.empty or test_df.empty:
        raise ValueError("Time split produced an empty train or test dataset.")
    return train_df, gap_df, test_df, cutoff_date, gap_start_date


def save_presentation_dataset(df):
    presentation_columns = {
        "date": "Date",
        "warehouse_id": "Store ID",
        "product_id": "Product ID",
        "category": "Category",
        "region": "Region",
        "inventory_quantity": "Inventory Level",
        "units_sold": "Units Sold",
        "incoming_stock": "Units Ordered",
        "price": "Price",
        "discount": "Discount",
        "weather_condition": "Weather Condition",
        "promotion": "Promotion",
        "competitor_pricing": "Competitor Pricing",
        "seasonality": "Seasonality",
        "epidemic": "Epidemic",
        "demand": "Demand",
    }
    columns = [column for column in presentation_columns if column in df.columns]
    df[columns].rename(columns=presentation_columns).to_csv(
        PRESENTATION_OUTPUT_FILE,
        index=False,
    )


def load_dataset_metadata():
    if not DATASET_METADATA_FILE.exists():
        return {}
    try:
        return json.loads(DATASET_METADATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def dataset_fingerprint(source_hash):
    contract = {
        "source_sha256": source_hash,
        "schema_version": PROCESSED_SCHEMA_VERSION,
        "features": FEATURES,
        "target": TARGET,
        "forecast_horizon_days": FORECAST_HORIZON_DAYS,
        "history_window_days": HISTORY_WINDOW_DAYS,
        "train_test_gap_days": TRAIN_TEST_GAP_DAYS,
    }
    payload = json.dumps(contract, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def processed_data_is_current():
    required_files = [OUTPUT_FILE, TRAIN_FILE, TEST_FILE, DATASET_METADATA_FILE]
    if not all(path.exists() for path in required_files):
        return False
    try:
        source_file = find_source_csv()
        metadata = load_dataset_metadata()
        source_hash = file_sha256(source_file)
        return (
            metadata.get("schema_version") == PROCESSED_SCHEMA_VERSION
            and metadata.get("forecast_horizon_days") == FORECAST_HORIZON_DAYS
            and metadata.get("history_window_days") == HISTORY_WINDOW_DAYS
            and metadata.get("train_test_gap_days") == TRAIN_TEST_GAP_DAYS
            and metadata.get("features") == FEATURES
            and metadata.get("target") == TARGET
            and metadata.get("source_sha256") == source_hash
            and metadata.get("dataset_fingerprint")
            == dataset_fingerprint(source_hash)
            and metadata.get("output_sha256") == file_sha256(OUTPUT_FILE)
            and metadata.get("train_sha256") == file_sha256(TRAIN_FILE)
            and metadata.get("test_sha256") == file_sha256(TEST_FILE)
        )
    except (OSError, ValueError):
        return False


def prepare_dataset():
    source_file = find_source_csv()
    print(f"[DATA] Reading: {source_file}")
    raw_df = pd.read_csv(source_file)
    source_df = clean_source_dataframe(raw_df)
    df = engineer_clean_dataframe(source_df)
    train_df, gap_df, test_df, cutoff_date, gap_start_date = (
        split_by_forecast_date(df)
    )

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    save_presentation_dataset(source_df)
    train_df.to_csv(TRAIN_FILE, index=False)
    test_df.to_csv(TEST_FILE, index=False)

    sample_positions = np.linspace(
        0,
        len(df) - 1,
        min(RUNTIME_SAMPLE_SIZE, len(df)),
        dtype=int,
    )
    runtime = df.iloc[sample_positions].copy().reset_index(drop=True)
    runtime["timestamp"] = runtime["date"]
    runtime["order_id"] = [
        f"KAGGLE_ORD{index + 1:05d}"
        for index in range(len(runtime))
    ]
    runtime["order_quantity"] = (
        runtime["units_sold"].round().clip(lower=1).astype(int)
    )
    runtime["vehicle_capacity"] = 1000
    statuses = ["Pending", "Processing", "Shipping", "Delivered"]
    runtime["delivery_status"] = [
        statuses[index % len(statuses)]
        for index in range(len(runtime))
    ]

    runtime_columns = [
        "timestamp",
        "forecast_date",
        "order_id",
        "warehouse_id",
        "product_id",
        "category",
        "region",
        "inventory_quantity",
        "order_quantity",
        "units_sold",
        "units_sold_lag_1",
        "units_sold_lag_7",
        "units_sold_rolling_mean_7",
        "incoming_stock",
        "price",
        "discount",
        "weather_condition",
        "promotion",
        "competitor_pricing",
        "seasonality",
        "forecast_seasonality",
        "epidemic",
        "demand",
        "demand_lag_1",
        "demand_lag_7",
        "demand_lag_14",
        "demand_lag_28",
        "demand_rolling_mean_7",
        "demand_rolling_mean_28",
        "demand_rolling_std_7",
        "demand_rolling_std_28",
        "demand_trend_7_28",
        "inventory_to_demand_ratio",
        "price_vs_competitor_ratio",
        "vehicle_capacity",
        "delivery_status",
        TARGET,
    ]
    runtime[runtime_columns].to_csv(RUNTIME_OUTPUT_FILE, index=False)

    source_hash = file_sha256(source_file)
    metadata = {
        "schema_version": PROCESSED_SCHEMA_VERSION,
        "source_file": str(source_file),
        "source_sha256": source_hash,
        "forecast_horizon_days": FORECAST_HORIZON_DAYS,
        "history_window_days": HISTORY_WINDOW_DAYS,
        "features": FEATURES,
        "target": TARGET,
        "dataset_fingerprint": dataset_fingerprint(source_hash),
        "output_sha256": file_sha256(OUTPUT_FILE),
        "train_sha256": file_sha256(TRAIN_FILE),
        "test_sha256": file_sha256(TEST_FILE),
        "source_rows": int(len(raw_df)),
        "clean_source_rows": int(len(source_df)),
        "processed_rows": int(len(df)),
        "train_rows": int(len(train_df)),
        "gap_rows": int(len(gap_df)),
        "test_rows": int(len(test_df)),
        "observation_date_min": str(df["date"].min().date()),
        "observation_date_max": str(df["date"].max().date()),
        "forecast_date_min": str(df["forecast_date"].min().date()),
        "forecast_date_max": str(df["forecast_date"].max().date()),
        "cutoff_forecast_date": str(cutoff_date.date()),
        "gap_start_forecast_date": str(gap_start_date.date()),
        "train_test_gap_days": TRAIN_TEST_GAP_DAYS,
        "evaluation_mode": (
            "daily one-step-ahead walk-forward; each test day may use "
            "observed sales and demand from earlier test days"
        ),
    }
    DATASET_METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[DATA] Source rows: {len(raw_df):,}")
    print(f"[DATA] Valid t+1 rows: {len(df):,}")
    print(f"[DATA] 80% train rows: {len(train_df):,}")
    print(f"[DATA] Gap rows excluded: {len(gap_df):,}")
    print(
        "[DATA] Gap range: "
        f"{gap_start_date.date()} -> "
        f"{(cutoff_date - pd.Timedelta(days=1)).date()}"
    )
    print(f"[DATA] 20% test rows: {len(test_df):,}")
    print(f"[DATA] Forecast cutoff: {cutoff_date.date()}")
    print(f"[DATA] Warehouses/stores: {df['warehouse_id'].nunique()}")
    print(f"[DATA] Products: {df['product_id'].nunique()}")
    print(f"[DATA] Output: {OUTPUT_FILE}")
    print(f"[DATA] Metadata: {DATASET_METADATA_FILE}")
    return df


if __name__ == "__main__":
    prepare_dataset()
