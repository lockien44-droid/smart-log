from threading import Lock

inventory_lock = Lock()

warehouses = {
    "WH01": 500,
    "WH02": 300,
    "WH03": 700
}


# =========================
# SAFE GET ALL
# =========================
def get_inventory():
    return warehouses.copy()


def get_stock(warehouse_id):
    return warehouses.get(str(warehouse_id), 0)


def set_stock(warehouse_id, quantity):
    with inventory_lock:
        warehouses[str(warehouse_id)] = safe_int(quantity)
        return warehouses[str(warehouse_id)]


# =========================
# SAFE CONVERT
# =========================
def safe_int(v):
    try:
        return max(0, int(float(v)))
    except Exception:
        return 0


# =========================
# UPDATE INVENTORY (OUTBOUND)
# =========================
def update_inventory(warehouse_id, order_quantity):

    with inventory_lock:

        warehouse_id = str(warehouse_id)

        if warehouse_id not in warehouses:
            warehouses[warehouse_id] = 0

        qty = safe_int(order_quantity)

        warehouses[warehouse_id] = max(
            0,
            warehouses[warehouse_id] - qty
        )

        return warehouses[warehouse_id]


# =========================
# ADD STOCK (INBOUND)
# =========================
def add_stock(warehouse_id, incoming_stock):

    with inventory_lock:

        warehouse_id = str(warehouse_id)

        if warehouse_id not in warehouses:
            warehouses[warehouse_id] = 0

        qty = safe_int(incoming_stock)

        warehouses[warehouse_id] += qty

        return warehouses[warehouse_id]


# =========================
# REORDER POINT
# =========================
def calculate_reorder_point(
    future_demand,
    lead_time,
    safety_stock=50
):
    """
    future_demand đã là nhu cầu dự báo.
    Không nhân thêm lead_time nữa.
    """

    future_demand = safe_int(
        future_demand
    )

    return (
        future_demand +
        safety_stock
    )


# =========================
# INVENTORY CHECK
# =========================
def check_inventory(
    warehouse_id,
    future_demand,
    lead_time=1
):

    stock = get_stock(
        warehouse_id
    )

    return evaluate_inventory(
        stock=stock,
        future_demand=future_demand,
        lead_time=lead_time,
        warehouse_id=warehouse_id
    )


def evaluate_inventory(
    stock,
    future_demand,
    lead_time=1,
    warehouse_id=None
):
    """Evaluate an explicit stock value, including stock stored in Firebase."""

    stock = safe_int(stock)

    future_demand = safe_int(
        future_demand
    )

    lead_time = max(
        1,
        float(lead_time)
    )

    reorder_point = calculate_reorder_point(
        future_demand=future_demand,
        lead_time=lead_time,
        safety_stock=50
    )

    # =====================
    # INVENTORY LEVEL
    # =====================

    if stock <= 0:

        level = "OUT_OF_STOCK"
        level_description = "Hết hàng"

    elif stock < reorder_point * 0.50:

        level = "CRITICAL"
        level_description = "Tồn kho rất thấp"

    elif stock < reorder_point:

        level = "LOW"
        level_description = "Tồn kho thấp"

    else:

        level = "NORMAL"
        level_description = "Tồn kho an toàn"

    # =====================
    # REORDER LOGIC
    # =====================

    reorder_required = (
        level in [
            "LOW",
            "CRITICAL",
            "OUT_OF_STOCK"
        ]
    )

    reorder_quantity = max(
        reorder_point - stock,
        0
    )

    # =====================
    # RESPONSE
    # =====================

    return {

        "warehouse_id": str(warehouse_id or ""),

        "current_stock": int(
            stock
        ),

        "future_demand": int(
            future_demand
        ),

        "lead_time": float(
            lead_time
        ),

        "reorder_point": int(
            reorder_point
        ),

        "inventory_level": level,

        "inventory_level_description": level_description,

        "reorder_required": bool(
            reorder_required
        ),

        "reorder_quantity": int(
            reorder_quantity
        )
    }


# =========================
# TOTAL INVENTORY
# =========================
def total_inventory():
    return sum(
        warehouses.values()
    )


# =========================
# TEST
# =========================
if __name__ == "__main__":

    print("TEST CHECK")

    result = check_inventory(
        warehouse_id="WH01",
        future_demand=500,
        lead_time=2
    )

    print(result)

    print(
        "TOTAL:",
        total_inventory()
    )
