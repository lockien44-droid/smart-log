import os
import random

import numpy as np
import pandas as pd

# ==================================
# CONFIG
# ==================================

OUTPUT_FILE = "data/smart_logistics_dataset.csv"
ROWS = 5000

os.makedirs("data", exist_ok=True)

np.random.seed(42)
random.seed(42)

# ==================================
# IDS
# ==================================

order_ids = [
    f"ORD{i:05d}"
    for i in range(1, ROWS + 1)
]

warehouse_ids = [
    f"WH{random.randint(1, 10):02d}"
    for _ in range(ROWS)
]

product_ids = [
    f"PRD{random.randint(1, 100):03d}"
    for _ in range(ROWS)
]

# ==================================
# INVENTORY DATA
# ==================================

inventory_quantity = np.random.randint(
    50,
    1000,
    ROWS
)

order_quantity = np.random.randint(
    1,
    300,
    ROWS
)

daily_sales = np.random.randint(
    5,
    100,
    ROWS
)

incoming_stock = np.random.randint(
    0,
    300,
    ROWS
)

lead_time = np.round(
    np.random.uniform(1, 10, ROWS),
    1
)

vehicle_capacity = np.random.choice(
    [50, 100, 150, 200, 250],
    ROWS
)

# ==================================
# NOISE
# ==================================

inventory_quantity += np.random.randint(
    -20,
    21,
    ROWS
)

daily_sales += np.random.randint(
    -5,
    6,
    ROWS
)

inventory_quantity = np.clip(
    inventory_quantity,
    0,
    None
)

daily_sales = np.clip(
    daily_sales,
    1,
    None
)

# ==================================
# FUTURE DEMAND
# ==================================

noise = np.random.normal(
    0,
    0.15,
    ROWS
)

future_demand = (
    daily_sales *
    lead_time *
    (1 + noise)
)

future_demand = np.clip(
    future_demand,
    1,
    None
).astype(int)

# ==================================
# FEATURE ENGINEERING
# ==================================

demand_ratio = (
    order_quantity /
    (inventory_quantity + 1)
)

inventory_pressure = (
    inventory_quantity /
    (future_demand + 1)
)

stock_gap = (
    incoming_stock -
    order_quantity
)

# ==================================
# DELIVERY STATUS
# ==================================

delivery_status = []

for i in range(ROWS):

    inventory = inventory_quantity[i]
    order = order_quantity[i]
    demand = future_demand[i]
    vehicle = vehicle_capacity[i]
    incoming = incoming_stock[i]

    # Hết hàng hoàn toàn
    if inventory <= 0:

        status = "Cancelled"

    # Không đủ hàng để xử lý đơn
    elif inventory < order:

        status = "Pending"

    # Nhu cầu tương lai vượt tồn kho
    elif inventory < demand:

        status = "Processing"

    # Có hàng nhưng cần bổ sung vận chuyển
    elif order > (vehicle * 0.8):

        status = "Shipping"

    # Sắp hết hàng nhưng đang có hàng nhập
    elif incoming > order:

        status = "Shipping"

    # Trường hợp bình thường
    else:

        status = "Delivered"

    delivery_status.append(status)

# ==================================
# TIMESTAMPS
# ==================================

timestamps = pd.date_range(
    start="2025-01-01",
    periods=ROWS,
    freq="h"
)

# ==================================
# DATAFRAME
# ==================================

df = pd.DataFrame({

    "timestamp": timestamps,

    "order_id": order_ids,
    "warehouse_id": warehouse_ids,
    "product_id": product_ids,

    "inventory_quantity": inventory_quantity,
    "order_quantity": order_quantity,
    "daily_sales": daily_sales,
    "incoming_stock": incoming_stock,
    "lead_time": lead_time,
    "vehicle_capacity": vehicle_capacity,

    "delivery_status": delivery_status,

    "future_demand": future_demand,

    "demand_ratio": demand_ratio,
    "inventory_pressure": inventory_pressure,
    "stock_gap": stock_gap
})

# ==================================
# FINAL CLEANUP
# ==================================

numeric_columns = df.select_dtypes(
    include=[np.number]
).columns

df[numeric_columns] = df[
    numeric_columns
].clip(lower=0)

df.replace(
    [np.inf, -np.inf],
    0,
    inplace=True
)

df.fillna(
    0,
    inplace=True
)

# ==================================
# SAVE
# ==================================
print("\n===== DELIVERY STATUS DISTRIBUTION =====")

print(
    pd.Series(delivery_status)
    .value_counts()
)

print(
    "\nPercentage:"
)

print(
    round(
        pd.Series(delivery_status)
        .value_counts(normalize=True) * 100,
        2
    )
)
df.to_csv(
    OUTPUT_FILE,
    index=False
)

# ==================================
# REPORT
# ==================================

print("=" * 60)
print("SMART LOGISTICS DATASET CREATED")
print("=" * 60)

print(
    f"Rows: {len(df)}"
)

print(
    f"Columns: {len(df.columns)}"
)

print("\nDelivery Status Distribution:")
print(
    df["delivery_status"]
    .value_counts()
)

print("\nSample:")
print(
    df.head()
)

print(
    f"\nSaved to: {OUTPUT_FILE}"
)