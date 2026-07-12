import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ml.prepare_data import load_dataset_metadata
from ml.schema import (
    FEATURES,
    FORECAST_HORIZON_DAYS,
    PROCESSED_SCHEMA_VERSION,
    TARGET,
)
from ml.train import MODEL_PATH, load_train_test_data


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _metrics(y_true, predictions):
    return {
        "mae": float(mean_absolute_error(y_true, predictions)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, predictions))),
        "r2": float(r2_score(y_true, predictions)),
    }


def _print_metrics(label, metrics):
    print(label)
    print(f"MAE  : {metrics['mae']:.2f}")
    print(f"RMSE : {metrics['rmse']:.2f}")
    print(f"R²   : {metrics['r2']:.4f}")


def evaluate_saved_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Chưa có model tại {MODEL_PATH}. Hãy chạy python -m ml.train trước."
        )

    artifact = joblib.load(MODEL_PATH)
    if not isinstance(artifact, dict) or "model" not in artifact:
        raise ValueError("Model artifact không đúng định dạng bundle hiện tại.")
    if artifact.get("schema_version") != PROCESSED_SCHEMA_VERSION:
        raise ValueError("Model artifact dùng schema cũ; hãy train lại model.")
    if artifact.get("features") != FEATURES:
        raise ValueError("Feature schema trong model không khớp runtime hiện tại.")
    if artifact.get("target") != TARGET:
        raise ValueError("Target trong model không phải future_demand t+1 hiện tại.")
    if artifact.get("forecast_horizon_days") != FORECAST_HORIZON_DAYS:
        raise ValueError("Forecast horizon trong model không khớp cấu hình.")

    model = artifact["model"]
    _, test_data = load_train_test_data()
    missing = [
        column
        for column in [*FEATURES, TARGET, "date", "forecast_date"]
        if column not in test_data.columns
    ]
    if missing:
        raise ValueError(f"Dataset hiện tại không khớp model: {missing}")

    dataset_metadata = load_dataset_metadata()
    artifact_hash = artifact.get("source_sha256")
    current_hash = dataset_metadata.get("source_sha256")
    if not artifact_hash or not current_hash or artifact_hash != current_hash:
        raise ValueError(
            "Model được train từ raw data khác dataset hiện tại. "
            "Hãy chạy python -m ml.train để tạo lại model."
        )
    artifact_fingerprint = artifact.get("dataset_metadata", {}).get(
        "dataset_fingerprint"
    )
    if artifact_fingerprint != dataset_metadata.get("dataset_fingerprint"):
        raise ValueError("Dataset fingerprint không khớp model artifact.")

    cutoff_date = pd.Timestamp(
        artifact.get(
            "cutoff_forecast_date",
            artifact.get("cutoff_date"),
        )
    )
    current_cutoff = pd.Timestamp(test_data["forecast_date"].min())
    if cutoff_date != current_cutoff:
        raise ValueError(
            "Cutoff của model không khớp test.csv hiện tại: "
            f"model={cutoff_date.date()}, data={current_cutoff.date()}"
        )

    x_test = test_data[FEATURES]
    y_test = test_data[TARGET]

    print("===== ĐÁNH GIÁ MODEL t+1 ĐÃ HUẤN LUYỆN =====")
    print(f"Model       : {artifact.get('model_name', 'Random Forest')}")
    print(f"Version     : {artifact.get('model_version', 'Không rõ')}")
    print(f"Target      : {artifact.get('target_description', TARGET)}")
    print(f"Mốc forecast: {cutoff_date.date()}")
    print(f"Tập test    : {len(test_data):,} dòng")
    print("[TEST] Dự báo trên tập giữ lại, không huấn luyện lại...")

    predictions = model.predict(x_test)
    model_metrics = _metrics(y_test, predictions)
    lag_1_metrics = _metrics(y_test, test_data["units_sold_lag_1"])
    rolling_metrics = _metrics(
        y_test,
        test_data["units_sold_rolling_mean_7"],
    )

    print()
    _print_metrics("===== RANDOM FOREST =====", model_metrics)
    print()
    _print_metrics("===== BASELINE: SALES LAG 1 =====", lag_1_metrics)
    print()
    _print_metrics("===== BASELINE: SALES MEAN 7 =====", rolling_metrics)

    sample = test_data[
        ["date", "forecast_date", "warehouse_id", "product_id", TARGET]
    ].head(10).copy()
    sample["prediction"] = np.round(predictions[:10], 2)
    sample["absolute_error"] = np.round(
        np.abs(sample[TARGET] - sample["prediction"]),
        2,
    )
    print("\n===== 10 DÒNG DỰ BÁO MẪU =====")
    print(sample.to_string(index=False))
    return model_metrics


if __name__ == "__main__":
    evaluate_saved_model()
