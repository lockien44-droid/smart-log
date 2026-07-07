# Smart Logistics System

Hệ thống theo dõi trạng thái đơn hàng, dự báo nhu cầu và cập nhật tồn kho theo thời gian thực.

## Cấu trúc

```text
app/                    Backend và nghiệp vụ
  server.py             Flask API
  inventory_service.py Quy tắc tồn kho
  ai/predictor.py       Load model và dự báo
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

## Firebase

Local dùng `serviceAccountKey.json`. Render dùng:

```text
FIREBASE_DATABASE_URL
FIREBASE_CREDENTIAL_JSON
```

Không commit khóa Firebase lên GitHub.

## Dữ liệu và Random Forest

```powershell
python -m ml.download_data
python -m ml.prepare_data
python -m ml.train
python -m ml.evaluate
```

## Chạy web

```powershell
python -m app.server
```

Mở `http://127.0.0.1:8000`.

## Chạy mô phỏng

```powershell
python -m scripts.simulate
```

## Kiểm thử

```powershell
python -m tests.test_random_forest
```
