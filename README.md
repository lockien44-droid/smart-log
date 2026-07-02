# Smart Logistics System

Hệ thống theo dõi trạng thái đơn hàng, dự báo nhu cầu và cập nhật tồn kho gần thời gian thực.

## Chức năng chính

- Theo dõi trạng thái: Pending, Processing, Shipping, Delivered và Cancelled.
- Dự báo nhu cầu bằng Random Forest Regression.
- Tính Reorder Point và số lượng cần nhập.
- Phân loại tồn kho: NORMAL, LOW, CRITICAL và OUT_OF_STOCK.
- Lưu dữ liệu trên Firebase Realtime Database.
- Hiển thị kết quả trên Dashboard bằng Server Sync.

## Cài đặt

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

## Cấu hình Firebase

Tải khóa Firebase Admin của dự án và đặt trong thư mục mã nguồn. Mặc định chương trình tìm:

```text
smart-logistics-system-75a42-a699f876beef.json
```

Không commit hoặc chia sẻ khóa Firebase lên GitHub.

## Chạy chương trình

Terminal 1:

```powershell
py websocket_server.py
```

Mở `http://127.0.0.1:8000`.

Terminal 2:

```powershell
py main.py
```

## Đóng góp

1. Fork repository.
2. Tạo branch mới.
3. Commit thay đổi.
4. Mở Pull Request để cùng review và chỉnh sửa.
