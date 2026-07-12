import math
import os
from pathlib import Path
from datetime import datetime, timedelta

import joblib
import pandas as pd

from ml.schema import (
    FEATURES,
    FORECAST_HORIZON_DAYS,
    HISTORY_FEATURES,
    PROCESSED_SCHEMA_VERSION,
    seasonality_from_month,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models" / "random_forest_model.pkl"

model = None
MODEL_METADATA = {}
MODEL_LOAD_ERROR = None
FEATURE_COLUMNS = FEATURES.copy()


def safe_number(value, default=0):
    try:
        if value is None or value == "":
            return float(default)
        number = float(value)
        return number if math.isfinite(number) else float(default)
    except Exception:
        return float(default)


def optional_number(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def safe_text(value, default="UNKNOWN"):
    value = str(value if value is not None else "").strip()
    return value or default


def resolve_forecast_date(order_date=None, horizon_days=None):
    try:
        observation_date = pd.to_datetime(order_date).to_pydatetime()
    except Exception:
        observation_date = datetime.now()
    horizon = int(
        horizon_days
        if horizon_days is not None
        else MODEL_METADATA.get(
            "forecast_horizon_days",
            FORECAST_HORIZON_DAYS,
        )
    )
    return observation_date, observation_date + timedelta(days=max(0, horizon))


if os.path.exists(MODEL_PATH):
    try:
        artifact = joblib.load(MODEL_PATH)
        if not isinstance(artifact, dict) or "model" not in artifact:
            raise ValueError("Model artifact is not a supported bundle")
        if artifact.get("schema_version") != PROCESSED_SCHEMA_VERSION:
            raise ValueError(
                "Model artifact uses an outdated feature schema; retrain required"
            )
        model = artifact["model"]
        MODEL_METADATA = {
            key: value
            for key, value in artifact.items()
            if key != "model"
        }
        FEATURE_COLUMNS = artifact.get("features", FEATURES)
        if FEATURE_COLUMNS != FEATURES:
            raise ValueError(
                "Model feature schema differs from runtime; retrain required"
            )
        print(f"[AI] {MODEL_METADATA.get('model_name', 't+1 model')} loaded")
    except Exception as error:
        MODEL_LOAD_ERROR = str(error)
        model = None
        print("[AI] Model Load Error:", error)
else:
    print("[AI] Model Not Found -> Using Fallback")


def build_features(
    warehouse_id,
    product_id,
    category,
    region,
    inventory_quantity,
    units_sold,
    actual_demand,
    incoming_stock,
    price,
    discount,
    weather_condition,
    promotion,
    competitor_pricing,
    epidemic,
    order_date=None,
    units_sold_lag_1=None,
    units_sold_lag_7=None,
    units_sold_rolling_mean_7=None,
    demand_lag_1=None,
    demand_lag_7=None,
    demand_lag_14=None,
    demand_lag_28=None,
    demand_rolling_mean_7=None,
    demand_rolling_mean_28=None,
    demand_rolling_std_7=None,
    demand_rolling_std_28=None,
    demand_trend_7_28=None,
):
    observation_date, forecast_date = resolve_forecast_date(order_date)
    sales_lag_1 = optional_number(units_sold_lag_1)
    if sales_lag_1 is None:
        sales_lag_1 = optional_number(units_sold)
    current_demand = optional_number(demand_lag_1)
    if current_demand is None:
        current_demand = optional_number(actual_demand)

    mean_7 = optional_number(demand_rolling_mean_7)
    mean_28 = optional_number(demand_rolling_mean_28)
    trend = optional_number(demand_trend_7_28)
    if trend is None and mean_7 is not None and mean_28 is not None:
        trend = mean_7 - mean_28

    inventory = max(0, safe_number(inventory_quantity))
    product_price = max(0, safe_number(price))
    competitor_price = max(0, safe_number(competitor_pricing))
    inventory_ratio = (
        inventory / max(current_demand, 1)
        if current_demand is not None
        else None
    )
    price_ratio = product_price / max(competitor_price, 0.01)

    return {
        "warehouse_id": safe_text(warehouse_id),
        "product_id": safe_text(product_id),
        "category": safe_text(category),
        "region": safe_text(region),
        "weather_condition": safe_text(weather_condition),
        "forecast_seasonality": seasonality_from_month(forecast_date.month),
        "forecast_day_of_week": forecast_date.weekday(),
        "forecast_month": forecast_date.month,
        "forecast_is_weekend": int(forecast_date.weekday() >= 5),
        "seasonality": seasonality_from_month(observation_date.month),
        "date_ordinal": observation_date.toordinal(),
        "day_of_week": observation_date.weekday(),
        "month": observation_date.month,
        "is_weekend": int(observation_date.weekday() >= 5),
        "inventory_quantity": inventory,
        "units_sold": max(0, safe_number(units_sold)),
        "units_sold_lag_1": sales_lag_1,
        "units_sold_lag_7": optional_number(units_sold_lag_7),
        "units_sold_rolling_mean_7": optional_number(
            units_sold_rolling_mean_7
        ),
        "demand_lag_1": current_demand,
        "demand_lag_7": optional_number(demand_lag_7),
        "demand_lag_14": optional_number(demand_lag_14),
        "demand_lag_28": optional_number(demand_lag_28),
        "demand_rolling_mean_7": mean_7,
        "demand_rolling_mean_28": mean_28,
        "demand_rolling_std_7": optional_number(demand_rolling_std_7),
        "demand_rolling_std_28": optional_number(demand_rolling_std_28),
        "demand_trend_7_28": trend,
        "incoming_stock": max(0, safe_number(incoming_stock)),
        "price": product_price,
        "discount": max(0, safe_number(discount)),
        "promotion": int(max(0, min(safe_number(promotion), 1))),
        "competitor_pricing": competitor_price,
        "epidemic": int(max(0, min(safe_number(epidemic), 1))),
        "inventory_to_demand_ratio": inventory_ratio,
        "price_vs_competitor_ratio": price_ratio,
    }


def fallback(units_sold, incoming_stock, price=0, promotion=0):
    value = (
        safe_number(units_sold) * 0.75
        + safe_number(incoming_stock) * 0.15
        + safe_number(price) * 0.02
        + safe_number(promotion) * 5
    )
    return max(0, int(round(value)))


def _unknown_categories(features):
    known_categories = MODEL_METADATA.get("known_categories", {})
    unknown = []
    for column, known_values in known_categories.items():
        if column in features and str(features[column]) not in {
            str(value) for value in known_values
        }:
            unknown.append(column)
    return unknown


def predict_demand(**kwargs):
    return_details = bool(kwargs.pop("return_details", False))
    observation_date, forecast_date = resolve_forecast_date(
        kwargs.get("order_date")
    )

    def result(
        value,
        mode,
        error=None,
        cold_start=False,
        fallback_reason=None,
        missing_history=None,
        unknown_categories=None,
    ):
        normalized = max(0, min(int(round(float(value))), 100000))
        if return_details:
            return {
                "future_demand": normalized,
                "mode": mode,
                "fallback_used": mode == "Fallback",
                "error": error,
                "cold_start": bool(cold_start),
                "fallback_reason": fallback_reason,
                "missing_history": list(missing_history or []),
                "unknown_categories": list(unknown_categories or []),
                "observation_date": observation_date.date().isoformat(),
                "forecast_date": forecast_date.date().isoformat(),
            }
        return normalized

    try:
        features = build_features(
            warehouse_id=kwargs.get("warehouse_id"),
            product_id=kwargs.get("product_id"),
            category=kwargs.get("category"),
            region=kwargs.get("region"),
            inventory_quantity=kwargs.get("inventory_quantity"),
            units_sold=kwargs.get("units_sold"),
            actual_demand=kwargs.get("actual_demand"),
            incoming_stock=kwargs.get("incoming_stock"),
            price=kwargs.get("price"),
            discount=kwargs.get("discount"),
            weather_condition=kwargs.get("weather_condition"),
            promotion=kwargs.get("promotion"),
            competitor_pricing=kwargs.get("competitor_pricing"),
            epidemic=kwargs.get("epidemic"),
            order_date=kwargs.get("order_date"),
            **{
                column: kwargs.get(column)
                for column in HISTORY_FEATURES
            },
        )
        unknown = _unknown_categories(features)
        missing_history = [
            column
            for column in HISTORY_FEATURES
            if optional_number(features.get(column)) is None
        ]
        if missing_history:
            return result(
                fallback(
                    kwargs.get("units_sold"),
                    kwargs.get("incoming_stock"),
                    kwargs.get("price"),
                    kwargs.get("promotion"),
                ),
                "Fallback",
                "Chưa đủ 28 ngày lịch sử sales/demand: "
                + ", ".join(missing_history),
                cold_start=True,
                fallback_reason="insufficient_demand_history",
                missing_history=missing_history,
                unknown_categories=unknown,
            )
        if model is None:
            return result(
                fallback(
                    kwargs.get("units_sold"),
                    kwargs.get("incoming_stock"),
                    kwargs.get("price"),
                    kwargs.get("promotion"),
                ),
                "Fallback",
                MODEL_LOAD_ERROR or "Không tìm thấy model .pkl",
                fallback_reason="model_unavailable",
                unknown_categories=unknown,
            )

        runtime_df = pd.DataFrame([features])[FEATURE_COLUMNS]
        prediction = model.predict(runtime_df)
        return result(
            float(prediction[0]),
            MODEL_METADATA.get("model_name", "Forecast Model"),
            unknown_categories=unknown,
        )
    except Exception as error:
        print("[AI ERROR]", error)
        return result(
            fallback(
                kwargs.get("units_sold"),
                kwargs.get("incoming_stock"),
                kwargs.get("price"),
                kwargs.get("promotion"),
            ),
            "Fallback",
            str(error),
            fallback_reason="prediction_error",
        )


def get_model_info():
    metrics = MODEL_METADATA.get("metrics", {})
    model_name = MODEL_METADATA.get("model_name", "Demand Forecast Model")
    return {
        "name": model_name,
        "loaded": model is not None,
        "mode": model_name if model is not None else "Fallback",
        "load_error": MODEL_LOAD_ERROR,
        "schema_version": MODEL_METADATA.get("schema_version"),
        "encoding": MODEL_METADATA.get("encoding", "OneHotEncoder"),
        "train_test": MODEL_METADATA.get("split", "80% / 20%"),
        "train_rows": MODEL_METADATA.get("train_rows"),
        "test_rows": MODEL_METADATA.get("test_rows"),
        "n_estimators": MODEL_METADATA.get("n_estimators"),
        "mae": metrics.get("mae"),
        "rmse": metrics.get("rmse"),
        "r2": metrics.get("r2"),
        "baseline_metrics": MODEL_METADATA.get("baseline_metrics", {}),
        "validation_results": MODEL_METADATA.get("validation_results", []),
        "selected_candidate": MODEL_METADATA.get("selected_candidate"),
        "model_file": str(MODEL_PATH),
        "model_version": MODEL_METADATA.get(
            "model_version",
            f"forecast-{MODEL_METADATA.get('cutoff_date', 'unknown')}",
        ),
        "target": MODEL_METADATA.get("target", "future_demand"),
        "target_description": MODEL_METADATA.get(
            "target_description",
            "Demand on the exact next calendar day (t+1)",
        ),
        "prediction_contract": MODEL_METADATA.get("prediction_contract"),
        "forecast_horizon_days": MODEL_METADATA.get(
            "forecast_horizon_days",
            FORECAST_HORIZON_DAYS,
        ),
        "history_features": MODEL_METADATA.get(
            "history_features",
            HISTORY_FEATURES,
        ),
        "ignored_source_columns": MODEL_METADATA.get(
            "ignored_source_columns", []
        ),
        "source_features": MODEL_METADATA.get("source_features", []),
        "sklearn_version": MODEL_METADATA.get("sklearn_version"),
    }
