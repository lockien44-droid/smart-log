"""Train the legacy same-row Demand estimator shown by the dashboard."""

from datetime import datetime, timezone
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.prepare_data import clean_source_dataframe, find_source_csv, file_sha256
from ml.schema import (
    CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES,
    PROCESSED_SCHEMA_VERSION, TARGET,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "random_forest_model.pkl"


def train_same_day_model(model_path=MODEL_PATH):
    source = find_source_csv()
    raw = pd.read_csv(source)
    df = clean_source_dataframe(raw)
    df["date_ordinal"] = df["date"].map(pd.Timestamp.toordinal)
    df["day_of_week"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df = df.sort_values(["date", "warehouse_id", "product_id"]).reset_index(drop=True)

    unique_dates = np.sort(df["date"].unique())
    cutoff = pd.Timestamp(unique_dates[int(len(unique_dates) * 0.80)])
    train_df = df[df["date"] < cutoff].copy()
    test_df = df[df["date"] >= cutoff].copy()

    preprocessor = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ("numeric", "passthrough", NUMERIC_FEATURES),
    ])
    model = Pipeline([
        ("preprocessor", preprocessor),
        ("model", RandomForestRegressor(
            n_estimators=100,
            max_depth=18,
            min_samples_leaf=2,
            max_samples=0.5,
            max_features=0.8,
            random_state=42,
            n_jobs=-1,
        )),
    ])
    model.fit(train_df[FEATURES], train_df[TARGET])
    predictions = model.predict(test_df[FEATURES])
    metrics = {
        "mae": float(mean_absolute_error(test_df[TARGET], predictions)),
        "rmse": float(np.sqrt(mean_squared_error(test_df[TARGET], predictions))),
        "r2": float(r2_score(test_df[TARGET], predictions)),
    }
    known_categories = {
        column: sorted(train_df[column].astype(str).unique().tolist())
        for column in CATEGORICAL_FEATURES
    }
    artifact = {
        "model": model,
        "schema_version": PROCESSED_SCHEMA_VERSION,
        "features": FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "history_features": [],
        "known_categories": known_categories,
        "forecast_horizon_days": 0,
        "metrics": metrics,
        "model_name": "Random Forest Regressor (Same-day)",
        "model_family": "random_forest",
        "model_version": f"same-day-v4-cutoff-{cutoff.date()}",
        "encoding": "OneHotEncoder(handle_unknown=ignore)",
        "n_estimators": 100,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "split": "80% / 20% by date",
        "target": TARGET,
        "target_description": "Demand on the same row/day; not a future forecast",
        "prediction_contract": "Estimate same-day Demand from same-day operational inputs",
        "task_type": "same_day_estimation",
        "leakage_warning": "Same-day inputs may contain information correlated with the answer.",
        "cutoff_date": str(cutoff.date()),
        "source_file": str(source),
        "source_sha256": file_sha256(source),
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path, compress=3)
    print(f"MAE={metrics['mae']:.2f} RMSE={metrics['rmse']:.2f} R2={metrics['r2']:.4f}")
    print(f"Saved: {model_path}")
    return model, metrics


if __name__ == "__main__":
    train_same_day_model()
