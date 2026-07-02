import os
import joblib
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

from data_preprocessing import preprocess_data

# ====================================
# CREATE MODEL FOLDER
# ====================================

os.makedirs(
    "models",
    exist_ok=True
)

# ====================================
# LOAD DATA
# ====================================

df = preprocess_data()

# ====================================
# ENCODE DELIVERY STATUS
# ====================================

status_map = {
    "Pending": 0,
    "Processing": 1,
    "Shipping": 2,
    "Delivered": 3,
    "Cancelled": 4
}

if df["delivery_status"].dtype == "object":
    df["delivery_status"] = (
        df["delivery_status"]
        .map(status_map)
        .fillna(0)
    )

# ====================================
# FEATURES
# ====================================

feature_columns = [
    "inventory_quantity",
    "order_quantity",
    "daily_sales",
    "incoming_stock",
    "lead_time",
    "delivery_status",
    "vehicle_capacity"
]

X = df[feature_columns]

# ====================================
# TARGET
# ====================================

y = df["future_demand"]

# ====================================
# TRAIN TEST SPLIT
# ====================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# ====================================
# RANDOM FOREST MODEL
# ====================================

model = RandomForestRegressor(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    n_jobs=-1
)

# ====================================
# TRAIN MODEL
# ====================================

model.fit(
    X_train,
    y_train
)

# ====================================
# PREDICT
# ====================================

y_pred = model.predict(
    X_test
)

# ====================================
# METRICS
# ====================================

mae = mean_absolute_error(
    y_test,
    y_pred
)

rmse = (
    mean_squared_error(
        y_test,
        y_pred
    ) ** 0.5
)

r2 = r2_score(
    y_test,
    y_pred
)

print("\n===== MODEL EVALUATION =====")
print(f"MAE  : {mae:.2f}")
print(f"RMSE : {rmse:.2f}")
print(f"R²   : {r2:.4f}")

# ====================================
# FEATURE IMPORTANCE
# ====================================

print("\n===== FEATURE IMPORTANCE =====")

importance = model.feature_importances_

for feature, score in zip(
    feature_columns,
    importance
):
    print(
        f"{feature}: {score:.4f}"
    )

# ====================================
# SAVE MODEL
# ====================================

model_path = "models/random_forest_model.pkl"

joblib.dump(
    {
        "model": model,
        "features": feature_columns
    },
    model_path
)

print("\nModel saved successfully.")

print(
    "File size:",
    os.path.getsize(model_path),
    "bytes"
)

# ====================================
# METRICS CHART
# ====================================

metrics = {
    "MAE": mae,
    "RMSE": rmse,
    "R2": r2
}

plt.figure(
    figsize=(8, 5)
)

plt.bar(
    list(metrics.keys()),
    list(metrics.values())
)

plt.title(
    f"Model Evaluation ({len(df)} Records)"
)

plt.ylabel(
    "Metric Value"
)

plt.grid(
    axis="y",
    linestyle="--",
    alpha=0.5
)

plt.savefig(
    "metrics_chart.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()

print(
    "\nmetrics_chart.png saved successfully."
)

# ====================================
# ACTUAL VS PREDICTED
# ====================================

plt.figure(
    figsize=(8, 6)
)

plt.scatter(
    y_test,
    y_pred,
    alpha=0.6
)

plt.xlabel(
    "Actual Demand"
)

plt.ylabel(
    "Predicted Demand"
)

plt.title(
    "Actual vs Predicted Demand"
)

plt.grid(
    linestyle="--",
    alpha=0.5
)

plt.savefig(
    "prediction_comparison.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()

print(
    "prediction_comparison.png saved successfully."
)