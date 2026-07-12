from datetime import datetime, timezone
from pathlib import Path
import os
import platform

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

from ml.prepare_data import (
    TEST_FILE,
    TRAIN_FILE,
    TRAIN_TEST_GAP_DAYS,
    load_dataset_metadata,
    prepare_dataset,
    processed_data_is_current,
)
from ml.schema import (
    CATEGORICAL_FEATURES,
    FEATURES,
    FORECAST_HORIZON_DAYS,
    HISTORY_FEATURES,
    HISTORY_WINDOW_DAYS,
    NUMERIC_FEATURES,
    PROCESSED_SCHEMA_VERSION,
    TARGET,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "random_forest_model.pkl"


def _metrics(y_true, predictions):
    return {
        "mae": float(mean_absolute_error(y_true, predictions)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, predictions))),
        "r2": float(r2_score(y_true, predictions)),
    }


def _validate_training_frame(df, label):
    required = ["date", "forecast_date", TARGET, *FEATURES]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing {label} columns: {missing}")
    if df.duplicated(["warehouse_id", "product_id", "forecast_date"]).any():
        raise ValueError(f"Duplicate warehouse/product/forecast_date rows in {label}")
    if df[FEATURES + [TARGET]].isna().any().any():
        raise ValueError(f"NaN values remain in {label} model columns")

    expected_forecast_dates = df["date"] + pd.Timedelta(
        days=FORECAST_HORIZON_DAYS
    )
    if not df["forecast_date"].equals(expected_forecast_dates):
        raise ValueError(f"Invalid t+1 forecast_date alignment in {label}")
    numeric_values = df[NUMERIC_FEATURES + [TARGET]].to_numpy(dtype=float)
    if not np.isfinite(numeric_values).all():
        raise ValueError(f"Non-finite numeric values remain in {label}")
    if (df[TARGET] < 0).any():
        raise ValueError(f"Negative target values remain in {label}")


def load_train_test_data(force_prepare=False):
    if force_prepare or not processed_data_is_current():
        prepare_dataset()
    train_df = pd.read_csv(
        TRAIN_FILE,
        parse_dates=["date", "forecast_date"],
    )
    test_df = pd.read_csv(
        TEST_FILE,
        parse_dates=["date", "forecast_date"],
    )
    _validate_training_frame(train_df, "train")
    _validate_training_frame(test_df, "test")

    sort_columns = ["forecast_date", "warehouse_id", "product_id"]
    train_df = train_df.sort_values(sort_columns).reset_index(drop=True)
    test_df = test_df.sort_values(sort_columns).reset_index(drop=True)
    if train_df["forecast_date"].max() >= test_df["forecast_date"].min():
        raise ValueError("Train and test forecast dates overlap")
    return train_df, test_df


def build_pipeline(
    n_estimators=100,
    n_jobs=1,
    random_state=42,
    model_type="random_forest",
    model_params=None,
):
    model_params = dict(model_params or {})
    is_histogram = model_type == "hist_gradient_boosting"
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=not is_histogram,
                ),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", "passthrough", NUMERIC_FEATURES),
        ],
        sparse_threshold=0.0 if is_histogram else 1.0,
    )

    if is_histogram:
        estimator = HistGradientBoostingRegressor(
            loss=model_params.pop("loss", "poisson"),
            max_iter=model_params.pop("max_iter", 300),
            learning_rate=model_params.pop("learning_rate", 0.05),
            max_leaf_nodes=model_params.pop("max_leaf_nodes", 31),
            min_samples_leaf=model_params.pop("min_samples_leaf", 20),
            l2_regularization=model_params.pop("l2_regularization", 1.0),
            random_state=random_state,
            **model_params,
        )
    else:
        estimator = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=model_params.pop("max_depth", 14),
            min_samples_leaf=model_params.pop("min_samples_leaf", 3),
            max_samples=model_params.pop("max_samples", 0.15),
            max_features=model_params.pop("max_features", 0.7),
            criterion=model_params.pop("criterion", "squared_error"),
            random_state=random_state,
            n_jobs=n_jobs,
            **model_params,
        )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", estimator),
        ]
    )


def _walk_forward_splits(train_df, n_splits=4):
    """Return expanding-window folds with a t+1 embargo before validation."""
    unique_dates = np.sort(train_df["forecast_date"].unique())
    minimum_train_dates = max(HISTORY_WINDOW_DAYS * 2, 30)
    available = len(unique_dates) - minimum_train_dates
    if available < n_splits:
        raise ValueError("Not enough forecast dates for walk-forward validation")

    validation_days = max(1, available // n_splits)
    folds = []
    for fold_index in range(n_splits):
        validation_start_index = minimum_train_dates + fold_index * validation_days
        validation_end_index = (
            len(unique_dates)
            if fold_index == n_splits - 1
            else min(len(unique_dates), validation_start_index + validation_days)
        )
        validation_dates = unique_dates[validation_start_index:validation_end_index]
        if not len(validation_dates):
            continue
        cutoff_date = pd.Timestamp(validation_dates[0])
        validation_end = pd.Timestamp(validation_dates[-1])
        gap_start = cutoff_date - pd.Timedelta(days=TRAIN_TEST_GAP_DAYS)
        fit_df = train_df[train_df["forecast_date"] < gap_start].copy()
        validation_df = train_df[
            (train_df["forecast_date"] >= cutoff_date)
            & (train_df["forecast_date"] <= validation_end)
        ].copy()
        if fit_df.empty or validation_df.empty:
            raise ValueError("Walk-forward fold produced an empty dataset")
        folds.append((fit_df, validation_df, cutoff_date, validation_end))
    return folds


def _candidate_specs():
    return [
        {
            "name": "random_forest_baseline",
            "model_type": "random_forest",
            "n_estimators": 100,
            "model_params": {
                "max_depth": 14,
                "min_samples_leaf": 3,
                "max_samples": 0.15,
                "max_features": 0.7,
            },
        },
        {
            "name": "random_forest_tuned",
            "model_type": "random_forest",
            "n_estimators": 80,
            "model_params": {
                "max_depth": 18,
                "min_samples_leaf": 2,
                "max_samples": 0.50,
                "max_features": 0.8,
            },
        },
        {
            "name": "hist_gradient_boosting_poisson",
            "model_type": "hist_gradient_boosting",
            "n_estimators": None,
            "model_params": {
                "loss": "poisson",
                "max_iter": 300,
                "learning_rate": 0.05,
                "max_leaf_nodes": 31,
                "min_samples_leaf": 20,
                "l2_regularization": 1.0,
            },
        },
    ]


def select_model_by_time_validation(train_df):
    folds = _walk_forward_splits(train_df)
    results = []
    for spec in _candidate_specs():
        print(f"[SELECT] Training {spec['name']}...")
        fold_results = []
        for fold_number, (fit_df, validation_df, start, end) in enumerate(
            folds, start=1
        ):
            pipeline = build_pipeline(
                n_estimators=spec["n_estimators"] or 100,
                n_jobs=1,
                random_state=42,
                model_type=spec["model_type"],
                model_params=spec["model_params"],
            )
            with threadpool_limits(limits=1):
                pipeline.fit(fit_df[FEATURES], fit_df[TARGET])
                predictions = pipeline.predict(validation_df[FEATURES])
            fold_results.append({
                "fold": fold_number,
                "fit_rows": int(len(fit_df)),
                "validation_rows": int(len(validation_df)),
                "validation_start": str(start.date()),
                "validation_end": str(end.date()),
                "metrics": _metrics(validation_df[TARGET], predictions),
            })
        metric_names = ("mae", "rmse", "r2")
        aggregate = {
            name: float(np.mean([fold["metrics"][name] for fold in fold_results]))
            for name in metric_names
        }
        result = {
            "name": spec["name"],
            "model_type": spec["model_type"],
            "n_estimators": spec["n_estimators"],
            "model_params": spec["model_params"],
            "metrics": aggregate,
            "folds": fold_results,
        }
        results.append(result)
        values = result["metrics"]
        print(
            f"[SELECT] {spec['name']}: "
            f"MAE={values['mae']:.2f}, RMSE={values['rmse']:.2f}, "
            f"R²={values['r2']:.4f}"
        )

    selected = min(results, key=lambda item: item["metrics"]["rmse"])
    return selected, results, folds


def train_model(model_path=MODEL_PATH, force_prepare=False):
    train_df, test_df = load_train_test_data(force_prepare=force_prepare)
    cutoff_date = pd.Timestamp(test_df["forecast_date"].min())
    selected, validation_results, validation_folds = (
        select_model_by_time_validation(train_df)
    )

    print(f"[AI] Selected model: {selected['name']}")
    model = build_pipeline(
        n_estimators=selected["n_estimators"] or 100,
        n_jobs=1,
        random_state=42,
        model_type=selected["model_type"],
        model_params=selected["model_params"],
    )
    with threadpool_limits(limits=1):
        model.fit(train_df[FEATURES], train_df[TARGET])
        predictions = model.predict(test_df[FEATURES])

    metrics = _metrics(test_df[TARGET], predictions)
    baseline_metrics = {
        "demand_lag_1": _metrics(test_df[TARGET], test_df["demand_lag_1"]),
        "demand_rolling_mean_7": _metrics(
            test_df[TARGET], test_df["demand_rolling_mean_7"]
        ),
        "demand_rolling_mean_28": _metrics(
            test_df[TARGET], test_df["demand_rolling_mean_28"]
        ),
        "units_sold_rolling_mean_7": _metrics(
            test_df[TARGET], test_df["units_sold_rolling_mean_7"]
        ),
    }
    best_baseline_name, best_baseline = min(
        baseline_metrics.items(), key=lambda item: item[1]["rmse"]
    )
    accepted = (
        metrics["rmse"] < best_baseline["rmse"]
        and metrics["mae"] < best_baseline["mae"]
        and metrics["r2"] > best_baseline["r2"]
    )

    print("\n===== FINAL TEST: TRUE t+1 TARGET =====")
    print(f"Selected: {selected['name']}")
    print(f"MAE  : {metrics['mae']:.2f}")
    print(f"RMSE : {metrics['rmse']:.2f}")
    print(f"R²   : {metrics['r2']:.4f}")
    print("\n===== NAIVE BASELINES =====")
    for name, values in baseline_metrics.items():
        print(
            f"{name:<32} MAE={values['mae']:.2f} "
            f"RMSE={values['rmse']:.2f} R²={values['r2']:.4f}"
        )
    print(
        f"\nMODEL GATE: {'ACCEPTED' if accepted else 'REJECTED'}; "
        f"must beat best baseline ({best_baseline_name}) on MAE, RMSE and R²"
    )

    estimator = model.named_steps["model"]
    if hasattr(estimator, "feature_importances_"):
        print("\n===== FEATURE IMPORTANCE =====")
        names = model.named_steps["preprocessor"].get_feature_names_out()
        for feature, score in sorted(
            zip(names, estimator.feature_importances_),
            key=lambda item: item[1],
            reverse=True,
        ):
            print(f"{feature:<45} {score:.4f}")

    dataset_metadata = load_dataset_metadata()
    known_categories = {
        column: sorted(train_df[column].astype(str).unique().tolist())
        for column in CATEGORICAL_FEATURES
    }
    model_display_name = {
        "random_forest": "Random Forest Regressor",
        "hist_gradient_boosting": "Histogram Gradient Boosting Regressor",
    }[selected["model_type"]]
    artifact = {
        "model": model,
        "schema_version": PROCESSED_SCHEMA_VERSION,
        "features": FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "history_features": HISTORY_FEATURES,
        "known_categories": known_categories,
        "forecast_horizon_days": FORECAST_HORIZON_DAYS,
        "history_window_days": HISTORY_WINDOW_DAYS,
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "validation_results": validation_results,
        "walk_forward_folds": len(validation_folds),
        "walk_forward_validation": True,
        "selection_metric": "mean_walk_forward_rmse",
        "selected_candidate": selected,
        "acceptance_gate": {
            "accepted": accepted,
            "best_baseline": best_baseline_name,
            "requirements": "lower MAE/RMSE and higher R2 on untouched final test",
        },
        "model_name": model_display_name,
        "model_family": selected["model_type"],
        "model_version": f"forecast-v3-tplus1-cutoff-{cutoff_date.date()}",
        "encoding": "OneHotEncoder(handle_unknown=ignore)",
        "n_estimators": selected["n_estimators"],
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "split": (
            "80% / 20% by forecast_date, "
            f"with a {TRAIN_TEST_GAP_DAYS}-day gap"
        ),
        "train_test_gap_days": TRAIN_TEST_GAP_DAYS,
        "target": TARGET,
        "target_description": (
            "Demand on the exact next calendar day (t+1) for the same "
            "warehouse_id and product_id"
        ),
        "prediction_contract": (
            "Use actual sales and actual demand available through the end of "
            "observation day t to forecast demand on calendar day t+1"
        ),
        "date_feature_reference": "forecast_date",
        "cutoff_date": str(cutoff_date.date()),
        "cutoff_forecast_date": str(cutoff_date.date()),
        "train_forecast_date_max": str(
            train_df["forecast_date"].max().date()
        ),
        "test_forecast_date_max": str(
            test_df["forecast_date"].max().date()
        ),
        "source_file": dataset_metadata.get("source_file"),
        "source_sha256": dataset_metadata.get("source_sha256"),
        "dataset_metadata": dataset_metadata,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "ignored_source_columns": [
            "date_ordinal",
            "current-row demand as a direct target",
        ],
        "source_features": [
            "Date",
            "Store ID",
            "Product ID",
            "Category",
            "Region",
            "Inventory Level",
            "Units Sold",
            "Units Ordered",
            "Price",
            "Discount",
            "Weather Condition",
            "Promotion",
            "Competitor Pricing",
            "Seasonality",
            "Epidemic",
            "historical Demand through day t",
        ],
    }

    if not accepted:
        raise RuntimeError(
            "Candidate model rejected: it did not beat the best naive baseline "
            "on MAE, RMSE and R2. Existing production artifact was preserved."
        )

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    print(f"\n[AI] Model saved: {model_path}")
    return model, metrics


if __name__ == "__main__":
    train_model()
