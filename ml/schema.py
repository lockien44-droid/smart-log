"""Shared schema for same-day demand estimation."""

FORECAST_HORIZON_DAYS = 0
HISTORY_WINDOW_DAYS = 0
PROCESSED_SCHEMA_VERSION = 4
TARGET = "demand"

CATEGORICAL_FEATURES = [
    "warehouse_id", "product_id", "category", "region",
    "weather_condition", "seasonality",
]

HISTORY_FEATURES = []

NUMERIC_FEATURES = [
    "date_ordinal", "day_of_week", "month", "is_weekend",
    "inventory_quantity", "units_sold", "incoming_stock", "price",
    "discount", "promotion", "competitor_pricing", "epidemic",
]

FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def seasonality_from_month(month):
    month = int(month)
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    return "Autumn"
