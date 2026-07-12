# Smart Logistics System

Hệ thống theo dõi đơn hàng, dự báo nhu cầu ngày tiếp theo và cập nhật tồn kho gần thời gian thực bằng Flask, Firebase và Random Forest.

## Cấu trúc

```text
app/                    Backend và nghiệp vụ
  server.py             Flask API
  inventory_service.py Quy tắc tồn kho
  ai/predictor.py       Load model và dự báo t+1
  firebase/             Cấu hình, truy cập Firebase
ml/                     Tải, xử lý, train và đánh giá dữ liệu
scripts/simulate.py     Mô phỏng dữ liệu
tests/                  Kiểm thử
templates/              HTML
static/css, static/js   Giao diện
data/                   Dữ liệu raw và processed
models/                 Model Random Forest
```

## Cài đặt

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

Các phiên bản pandas, NumPy, scikit-learn và joblib được khóa để model `.pkl` tương thích giữa môi trường train và deploy.

## Firebase

Local dùng `serviceAccountKey.json`. Render dùng:

```text
FIREBASE_DATABASE_URL
FIREBASE_CREDENTIAL_JSON
```

Không commit khóa Firebase lên GitHub.

## Dữ liệu và mục tiêu dự báo

Nguồn chuẩn duy nhất:

```text
data/raw/demand_forecasting.csv
```

Hợp đồng dự báo hiện tại:

```text
Dữ liệu quan sát đến hết ngày t
    -> Demand của đúng ngày lịch t+1
    -> cùng warehouse_id và product_id
```

`future_demand` không còn là cột `Demand` cùng dòng. Pipeline join target theo đúng ngày lịch tiếp theo và loại các dòng bị thiếu ngày hoặc chưa đủ lịch sử bán hàng bảy ngày.

Các feature lịch sử chính:

```text
units_sold_lag_1
units_sold_lag_7
units_sold_rolling_mean_7
```

Chạy pipeline:

```powershell
python -m ml.download_data
python -m ml.prepare_data
python -m ml.train
python -m ml.evaluate
```

Processed data hiện có 75.300 dòng hợp lệ: 60.100 train, 100 dòng gap và 15.100 test theo `forecast_date`.

Kết quả model t+1 hiện tại:

```text
MAE  : 29.07
RMSE : 37.44
R²   : 0.2798
```

Model tốt hơn baseline rolling mean 7 ngày, nhưng đây là bài toán dự báo t+1 thật nên chỉ số thấp hơn model cũ học `Demand` cùng dòng.

## Chạy web

```powershell
python -m app.server
```

Mở `http://127.0.0.1:8000`.

Dashboard yêu cầu tổng số lượng đã bán trong ngày `t`. Nếu sản phẩm chưa đủ sáu ngày lịch sử trước đó, dự báo sẽ dùng fallback và đánh dấu `cold_start`.

## Chạy mô phỏng

```powershell
python -m scripts.simulate
```

Simulator sử dụng các feature lịch sử đã được tính trong `smart_logistics_runtime.csv` và kiểm tra đơn trùng trước khi thay đổi tồn kho.

## Kiểm thử

```powershell
python -m tests.test_random_forest
```

Bộ test kiểm tra target t+1, ngày lịch bị thiếu, lag/rolling, temporal split, schema artifact, category mới và cold-start fallback.
