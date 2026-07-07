import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ml.train import FEATURES, MODEL_PATH, TARGET, load_training_data


def evaluate_saved_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Chưa có model tại {MODEL_PATH}. Hãy chạy python -m ml.train trước."
        )

    artifact = joblib.load(MODEL_PATH)
    model = artifact["model"]
    cutoff_date = pd.Timestamp(artifact["cutoff_date"])

    data = load_training_data()
    test_data = data[data["date"] >= cutoff_date].copy()
    x_test = test_data[FEATURES]
    y_test = test_data[TARGET]

    print("===== ĐÁNH GIÁ MODEL ĐÃ HUẤN LUYỆN =====")
    print(f"Model       : {artifact.get('model_name', 'Random Forest')}")
    print(f"Encoding    : {artifact.get('encoding', 'Không rõ')}")
    print(f"Mốc chia    : {cutoff_date.date()}")
    print(f"Tập test 20%: {len(test_data):,} dòng")
    print("[TEST] Đang dự báo trên tập 20%, không huấn luyện lại...")

    predictions = model.predict(x_test)
    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    r2 = r2_score(y_test, predictions)

    print("\n===== KẾT QUẢ TEST 20% =====")
    print(f"MAE  : {mae:.2f}")
    print(f"RMSE : {rmse:.2f}")
    print(f"R²   : {r2:.4f}")

    sample = test_data[
        ["date", "warehouse_id", "product_id", TARGET]
    ].head(10).copy()
    sample["prediction"] = np.round(predictions[:10], 2)
    sample["absolute_error"] = np.round(
        np.abs(sample[TARGET] - sample["prediction"]),
        2,
    )
    print("\n===== 10 DÒNG DỰ BÁO MẪU =====")
    print(sample.to_string(index=False))


if __name__ == "__main__":
    evaluate_saved_model()
