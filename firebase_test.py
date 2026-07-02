from firebase_manager import update_order_status

update_order_status(
    "ORD99999",
    "Testing",
    100,
    50
)

print("Firebase Updated")