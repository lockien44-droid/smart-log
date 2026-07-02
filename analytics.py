# analytics.py

from statistics import mean

# =====================================
# ORDER KPI
# =====================================

def delivery_rate(
    delivered_orders,
    total_orders
):
    """
    Tỷ lệ giao hàng thành công (%)
    """

    if total_orders <= 0:
        return 0.0

    return round(
        (delivered_orders / total_orders)
        * 100,
        2
    )


def cancel_rate(
    cancelled_orders,
    total_orders
):
    """
    Tỷ lệ hủy đơn (%)
    """

    if total_orders <= 0:
        return 0.0

    return round(
        (cancelled_orders / total_orders)
        * 100,
        2
    )


# =====================================
# ETA KPI
# =====================================

def average_eta(
    eta_list
):
    """
    ETA trung bình (giờ)
    """

    if not eta_list:
        return 0.0

    return round(
        mean(eta_list),
        2
    )


# =====================================
# INVENTORY KPI
# =====================================

def inventory_utilization(
    initial_inventory,
    current_inventory
):
    """
    Mức sử dụng tồn kho (%)
    """

    if initial_inventory <= 0:
        return 0.0

    used_inventory = (
        initial_inventory -
        current_inventory
    )

    return round(
        (used_inventory /
         initial_inventory) * 100,
        2
    )


def inventory_turnover(
    total_sales,
    average_inventory
):
    """
    Vòng quay tồn kho
    """

    if average_inventory <= 0:
        return 0.0

    return round(
        total_sales /
        average_inventory,
        2
    )


# =====================================
# ORDER STATUS KPI
# =====================================

def order_status_distribution(
    order_stats
):
    """
    Phân bố trạng thái đơn hàng
    """

    total = sum(
        order_stats.values()
    )

    if total == 0:
        return {}

    result = {}

    for status, count in order_stats.items():

        result[status] = round(
            (count / total) * 100,
            2
        )

    return result


# =====================================
# DASHBOARD SUMMARY
# =====================================

def build_dashboard_summary(

    total_orders,

    order_stats,

    total_inventory,

    initial_inventory,

    eta_history=None,

    total_sales=0
):
    """
    KPI tổng hợp cho Dashboard
    """

    eta_history = eta_history or []

    delivered = order_stats.get(
        "Delivered",
        0
    )

    cancelled = order_stats.get(
        "Cancelled",
        0
    )

    avg_inventory = (
        (
            initial_inventory +
            total_inventory
        ) / 2
    )

    summary = {

        "total_orders":
            total_orders,

        "delivered_orders":
            delivered,

        "cancelled_orders":
            cancelled,

        "delivery_rate":
            delivery_rate(
                delivered,
                total_orders
            ),

        "cancel_rate":
            cancel_rate(
                cancelled,
                total_orders
            ),

        "average_eta":
            average_eta(
                eta_history
            ),

        "total_inventory":
            total_inventory,

        "inventory_utilization":
            inventory_utilization(
                initial_inventory,
                total_inventory
            ),

        "inventory_turnover":
            inventory_turnover(
                total_sales,
                avg_inventory
            ),

        "order_distribution":
            order_status_distribution(
                order_stats
            )
    }

    return summary


# =====================================
# TEST
# =====================================

if __name__ == "__main__":

    order_stats = {

        "Pending": 5,

        "Processing": 8,

        "Shipping": 12,

        "Delivered": 70,

        "Cancelled": 5
    }

    result = build_dashboard_summary(

        total_orders=100,

        order_stats=order_stats,

        total_inventory=1200,

        initial_inventory=2000,

        eta_history=[
            2.5,
            3.1,
            1.8,
            4.0
        ],

        total_sales=5000
    )

    print(
        "\n===== ANALYTICS ====="
    )

    for key, value in result.items():

        print(
            f"{key}: {value}"
        )