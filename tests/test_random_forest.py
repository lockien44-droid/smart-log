import math
from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

from ml.prepare_data import engineer_features, normalize_columns, split_by_forecast_date
from ml.schema import (
    FEATURES,
    FORECAST_HORIZON_DAYS,
    HISTORY_FEATURES,
    PROCESSED_SCHEMA_VERSION,
    TARGET,
)
from ml.train import MODEL_PATH, build_pipeline


def make_raw_dataframe(days=20, missing_dates=None):
    missing_dates = {str(value) for value in (missing_dates or [])}
    rows = []
    start = pd.Timestamp("2024-01-01")
    entities = [
        ("S001", "P0001", "Electronics", "North"),
        ("S002", "P0002", "Clothing", "South"),
    ]
    for entity_index, (store, product, category, region) in enumerate(entities):
        for offset in range(days):
            date = start + pd.Timedelta(days=offset)
            if date.date().isoformat() in missing_dates:
                continue
            rows.append({
                "Date": date.date().isoformat(),
                "Store ID": store,
                "Product ID": product,
                "Category": category,
                "Region": region,
                "Inventory Level": 200 + offset,
                "Units Sold": 10 + entity_index * 20 + offset,
                "Units Ordered": 30 + offset,
                "Price": 50 + offset / 10,
                "Discount": offset % 5,
                "Weather Condition": "Sunny",
                "Promotion": offset % 2,
                "Competitor Pricing": 48 + offset / 10,
                "Seasonality": "Winter",
                "Epidemic": 0,
                "Demand": 100 + entity_index * 50 + offset * 3,
            })
    return pd.DataFrame(rows).sample(frac=1, random_state=42).reset_index(drop=True)


class DataPreparationTests(unittest.TestCase):
    def test_demand_is_not_renamed_directly_to_future_demand(self):
        normalized = normalize_columns(make_raw_dataframe(days=2))
        self.assertIn("demand", normalized.columns)
        self.assertNotIn(TARGET, normalized.columns)

    def test_target_is_exact_next_calendar_day_per_product(self):
        raw = make_raw_dataframe(days=40)
        processed = engineer_features(raw)
        lookup = {
            (
                row["Store ID"],
                row["Product ID"],
                pd.Timestamp(row["Date"]),
            ): float(row["Demand"])
            for _, row in raw.iterrows()
        }

        for _, row in processed.iterrows():
            self.assertEqual(
                row["forecast_date"],
                row["date"] + pd.Timedelta(days=FORECAST_HORIZON_DAYS),
            )
            expected = lookup[
                (
                    row["warehouse_id"],
                    row["product_id"],
                    row["forecast_date"],
                )
            ]
            self.assertEqual(float(row[TARGET]), expected)

    def test_missing_calendar_day_is_not_used_as_next_day_target(self):
        raw = make_raw_dataframe(missing_dates={"2024-01-05"})
        processed = engineer_features(raw)
        invalid = processed[
            (processed["date"] == pd.Timestamp("2024-01-04"))
            | (processed["forecast_date"] == pd.Timestamp("2024-01-05"))
        ]
        self.assertTrue(invalid.empty)

    def test_history_features_use_exact_prior_calendar_days(self):
        raw = make_raw_dataframe(days=40)
        processed = engineer_features(raw)
        row = processed[
            (processed["warehouse_id"] == "S001")
            & (processed["product_id"] == "P0001")
        ].iloc[0]

        self.assertEqual(row["date"], pd.Timestamp("2024-01-28"))
        self.assertEqual(row["forecast_date"], pd.Timestamp("2024-01-29"))
        self.assertEqual(row["units_sold_lag_1"], 37)
        self.assertEqual(row["units_sold_lag_7"], 31)
        self.assertAlmostEqual(
            row["units_sold_rolling_mean_7"],
            np.mean([31, 32, 33, 34, 35, 36, 37]),
        )

    def test_missing_day_breaks_complete_seven_day_history(self):
        raw = make_raw_dataframe(missing_dates={"2024-01-05"})
        processed = engineer_features(raw)
        affected = processed[
            (processed["warehouse_id"] == "S001")
            & (processed["forecast_date"] <= pd.Timestamp("2024-01-11"))
        ]
        self.assertTrue(affected.empty)

    def test_temporal_split_uses_forecast_date(self):
        processed = engineer_features(make_raw_dataframe(days=40))
        train, gap, test, cutoff, gap_start = split_by_forecast_date(processed)
        self.assertLess(train["forecast_date"].max(), gap_start)
        self.assertTrue((gap["forecast_date"] < cutoff).all())
        self.assertGreaterEqual(test["forecast_date"].min(), cutoff)
        self.assertTrue(
            set(train["forecast_date"]).isdisjoint(set(test["forecast_date"]))
        )

    def test_feature_schema_has_no_target_leakage(self):
        for feature in HISTORY_FEATURES:
            self.assertIn(feature, FEATURES)
        for forbidden in (
            "demand",
            TARGET,
            "units_sold",
            "date",
            "forecast_date",
            "date_ordinal",
        ):
            self.assertNotIn(forbidden, FEATURES)
        self.assertEqual(len(FEATURES), len(set(FEATURES)))


class ModelPipelineTests(unittest.TestCase):
    def test_pipeline_accepts_unknown_categories(self):
        processed = engineer_features(make_raw_dataframe(days=30))
        model = build_pipeline(n_estimators=3, n_jobs=1, random_state=42)
        model.fit(processed[FEATURES], processed[TARGET])
        sample = processed[FEATURES].head(1).copy()
        sample.loc[:, "warehouse_id"] = "NEW_WAREHOUSE"
        sample.loc[:, "product_id"] = "NEW_PRODUCT"
        prediction = float(model.predict(sample)[0])
        self.assertTrue(math.isfinite(prediction))

    def test_current_artifact_matches_t_plus_one_schema(self):
        self.assertTrue(MODEL_PATH.exists(), "Run python -m ml.train first")
        artifact = joblib.load(MODEL_PATH)
        self.assertEqual(artifact.get("schema_version"), PROCESSED_SCHEMA_VERSION)
        self.assertEqual(artifact.get("features"), FEATURES)
        self.assertEqual(
            artifact.get("forecast_horizon_days"),
            FORECAST_HORIZON_DAYS,
        )
        self.assertEqual(artifact.get("target"), TARGET)
        self.assertIn("next calendar day", artifact.get("target_description", ""))
        self.assertTrue(artifact.get("source_sha256"))
        for key in ("sklearn_version", "pandas_version", "numpy_version"):
            self.assertTrue(artifact.get(key))


class PredictorTests(unittest.TestCase):
    class CapturingModel:
        def __init__(self):
            self.frame = None

        def predict(self, frame):
            self.frame = frame.copy()
            return np.array([123.4])

    def setUp(self):
        from app.ai import predictor

        self.predictor = predictor
        self.original_model = predictor.model
        self.original_features = predictor.FEATURE_COLUMNS
        self.original_metadata = predictor.MODEL_METADATA.copy()
        self.stub = self.CapturingModel()
        predictor.model = self.stub
        predictor.FEATURE_COLUMNS = FEATURES.copy()
        predictor.MODEL_METADATA = {
            "schema_version": PROCESSED_SCHEMA_VERSION,
            "forecast_horizon_days": FORECAST_HORIZON_DAYS,
            "known_categories": {},
            "model_name": "Random Forest",
        }

    def tearDown(self):
        self.predictor.model = self.original_model
        self.predictor.FEATURE_COLUMNS = self.original_features
        self.predictor.MODEL_METADATA = self.original_metadata

    def prediction_kwargs(self):
        return {
            "warehouse_id": "S001",
            "product_id": "P0001",
            "category": "Electronics",
            "region": "North",
            "inventory_quantity": 200,
            "units_sold": 20,
            "units_sold_lag_1": 20,
            "units_sold_lag_7": 14,
            "units_sold_rolling_mean_7": 17,
            "actual_demand": 121,
            "demand_lag_1": 121,
            "demand_lag_7": 115,
            "demand_lag_14": 108,
            "demand_lag_28": 92,
            "demand_rolling_mean_7": 118,
            "demand_rolling_mean_28": 105,
            "demand_rolling_std_7": 2,
            "demand_rolling_std_28": 8,
            "demand_trend_7_28": 13,
            "incoming_stock": 30,
            "price": 50,
            "discount": 5,
            "weather_condition": "Sunny",
            "promotion": 1,
            "competitor_pricing": 48,
            "epidemic": 0,
            "order_date": "2024-01-07",
            "return_details": True,
        }

    def test_predictor_builds_ordered_t_plus_one_frame(self):
        result = self.predictor.predict_demand(**self.prediction_kwargs())
        self.assertEqual(result["mode"], "Random Forest")
        self.assertEqual(result["forecast_date"], "2024-01-08")
        self.assertEqual(list(self.stub.frame.columns), FEATURES)
        self.assertEqual(self.stub.frame.iloc[0]["units_sold_lag_1"], 20)
        self.assertEqual(self.stub.frame.iloc[0]["units_sold_lag_7"], 14)

    def test_predictor_falls_back_on_cold_start(self):
        kwargs = self.prediction_kwargs()
        kwargs["units_sold_lag_7"] = None
        kwargs["units_sold_rolling_mean_7"] = None
        result = self.predictor.predict_demand(**kwargs)
        self.assertEqual(result["mode"], "Fallback")
        self.assertTrue(result["cold_start"])
        self.assertEqual(
            result["fallback_reason"],
            "insufficient_demand_history",
        )
        self.assertIsNone(self.stub.frame)


if __name__ == "__main__":
    unittest.main(verbosity=2)
