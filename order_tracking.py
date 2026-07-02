# order_tracking.py

from datetime import datetime


# =================================
# UPDATE ORDER STATUS
# =================================

def update_status(status):

    workflow = {

        "Pending":
            "Processing",

        "Processing":
            "Shipping",

        "Shipping":
            "Delivered",

        "Delivered":
            "Delivered",

        "Cancelled":
            "Cancelled"
    }

    return workflow.get(
        status,
        status
    )


# =================================
# TRACK ORDER
# =================================

def track_order(
    order_id,
    status
):

    tracking_info = {

        "order_id":
            str(order_id),

        "status":
            str(status),

        "last_updated":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    }

    print("\n===== ORDER TRACKING =====")

    print(
        f"Order ID: {tracking_info['order_id']}"
    )

    print(
        f"Status: {tracking_info['status']}"
    )

    print(
        f"Updated: {tracking_info['last_updated']}"
    )

    return tracking_info


# =================================
# TEST
# =================================

if __name__ == "__main__":

    current_status = "Pending"

    print(
        f"Current Status: {current_status}"
    )

    new_status = update_status(
        current_status
    )

    print(
        f"Next Status: {new_status}"
    )

    track_order(
        "ORD00001",
        new_status
    )