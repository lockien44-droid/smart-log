import os
import joblib
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

from data_preprocessing import preprocess_data

# ==========================================
# CREATE MODEL DIRECTORY
# ==========================================

os.makedirs(
    "models",
    exist_ok=True
)

# ==========================================
# LOAD PREPROCESSED DATA
# ==========================================

df = preprocess_data()

if df is None:
    raise ValueError(
        "Failed to load dataset."
    )

# ==========================================
# FEATURES
# ==========================================

FEATURES = [
    "inventory_quantity",
    "order_quantity",
    "daily_sales",
    "incoming_stock",
    "lead_time",
    "vehicle_capacity",
    "delivery_status",
    "demand_ratio",
    "inventory_pressure",
    "stock_gap",
    "days_of_stock",
    "stock_after_order"
]

TARGET = "future_demand"

# Kiểm tra cột tồn tại

missing_features = [
    col
    for col in FEATURES
    if col not in df.columns
]

if missing_features:

    raise ValueError(
        f"Missing features: {missing_features}"
    )

if TARGET not in df.columns:

    raise ValueError(
        f"Target column '{TARGET}' not found"
    )

# ==========================================
# INPUT / OUTPUT
# ==========================================

X = df[FEATURES]

y = df[TARGET]

# ==========================================
# TRAIN TEST SPLIT
# ==========================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42
)

# ==========================================
# MODEL
# ==========================================

model = RandomForestRegressor(
    n_estimators=200,
    max_depth=12,
    random_state=42,
    n_jobs=-1
)

# ==========================================
# TRAINING
# ==========================================

print("\nTraining Random Forest Model...")

model.fit(
    X_train,
    y_train
)

print("Training completed.")

# ==========================================
# PREDICTION
# ==========================================

y_pred = model.predict(
    X_test
)

# ==========================================
# EVALUATION
# ==========================================

mae = mean_absolute_error(
    y_test,
    y_pred
)

rmse = np.sqrt(
    mean_squared_error(
        y_test,
        y_pred
    )
)

r2 = r2_score(
    y_test,
    y_pred
)

print("\n===== MODEL EVALUATION =====")

print(f"MAE  : {mae:.2f}")
print(f"RMSE : {rmse:.2f}")
print(f"R²   : {r2:.4f}")

# ==========================================
# DATASET INFO
# ==========================================

print("\n===== DATASET INFO =====")

print(
    f"Total Records : {len(df)}"
)

print(
    f"Train Records : {len(X_train)}"
)

print(
    f"Test Records  : {len(X_test)}"
)

# ==========================================
# FEATURE IMPORTANCE
# ==========================================

print("\n===== FEATURE IMPORTANCE =====")

importance = model.feature_importances_

for feature, score in zip(
    FEATURES,
    importance
):
    print(
        f"{feature:<20} {score:.4f}"
    )

# ==========================================
# SAVE MODEL
# ==========================================

MODEL_PATH = (
    "models/random_forest_model.pkl"
)

joblib.dump(
    {
        "model": model,
        "features": FEATURES
    },
    MODEL_PATH
)

print("\nModel saved successfully.")

print(
    "Location:",
    MODEL_PATH
)

print(
    "File Size:",
    os.path.getsize(
        MODEL_PATH
    ),
    "bytes"
)

# ==========================================
# SAMPLE TEST
# ==========================================

sample = X.iloc[[0]]

prediction = model.predict(
    sample
)[0]

print("\n===== SAMPLE PREDICTION =====")

print(
    "Predicted Future Demand:",
    round(prediction)
)

print("\nDone.")