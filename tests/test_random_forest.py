import argparse
from pathlib import Path

import joblib
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "random_forest_model.pkl"
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "kaggle_demand_training.csv"


def load_assets():
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Run first: python -m ml.train")
    if not DATA_PATH.exists():
        raise FileNotFoundError("Run first: python -m ml.prepare_data")

    bundle = joblib.load(MODEL_PATH)
    data = pd.read_csv(DATA_PATH, parse_dates=["date"])
    return bundle, data


def test_historical_sample(sample_index):
    bundle, data = load_assets()
    model = bundle["model"]
    features = bundle["features"]

    unique_dates = sorted(data["date"].unique())
    cutoff_date = unique_dates[int(len(unique_dates) * 0.80)]
    test_data = data[data["date"] >= cutoff_date].reset_index(drop=True)

    if sample_index < 0 or sample_index >= len(test_data):
        raise IndexError(
            f"sample must be from 0 to {len(test_data) - 1}"
        )

    row = test_data.iloc[sample_index]
    input_frame = row[features].to_frame().T.astype(float)

    predicted = float(model.predict(input_frame)[0])
    actual = float(row["future_demand"])
    absolute_error = abs(predicted - actual)
    error_percent = (
        absolute_error / actual * 100
        if actual != 0
        else 0
    )

    print("\n===== RANDOM FOREST TEST =====")
    print(f"Sample             : {sample_index}")
    print(f"Date               : {row['date'].date()}")
    print(f"Warehouse/Store    : WH{int(row['warehouse_code']):02d}")
    print(f"Product            : PRD{int(row['product_code']):03d}")
    print(f"Current daily sales: {row['daily_sales']:.0f}")
    print(f"Sales mean 7 days  : {row['sales_mean_7']:.2f}")
    print(f"Predicted next 7d  : {predicted:.2f}")
    print(f"Actual next 7d     : {actual:.2f}")
    print(f"Absolute error     : {absolute_error:.2f}")
    print(f"Error percent      : {error_percent:.2f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Test Random Forest against held-out Kaggle data."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Row index in the time-based test set (default: 0).",
    )
    args = parser.parse_args()
    test_historical_sample(args.sample)


if __name__ == "__main__":
    main()
