import time
import math
from datetime import date, datetime, timedelta

from app.firebase.config import database as db

MAX_HISTORY = 20
MAX_GPS_HISTORY = 50
MAX_EVENTS = 100
SALES_HISTORY_RETENTION_DAYS = 60
DEMAND_HISTORY_RETENTION_DAYS = 120

# ==============================
# SAFE CONVERT
# ==============================
def safe_int(v, default=0):
    try:
        return int(float(v))
    except:
        return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default


def _normalize_iso_date(value, field_name="date"):
    if isinstance(value, datetime):
        normalized = value.date()
    elif isinstance(value, date):
        normalized = value
    else:
        text = str(value or "").strip()
        try:
            normalized = date.fromisoformat(text)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name} must use ISO format YYYY-MM-DD"
            ) from error
        if normalized.isoformat() != text:
            raise ValueError(
                f"{field_name} must use ISO format YYYY-MM-DD"
            )

    return normalized


def _sales_value(value):
    """Read current or legacy sales-history values without masking gaps as zero."""
    if isinstance(value, dict):
        for key in (
            "units_sold",
            "daily_sales",
            "sales",
            "quantity",
            "value",
        ):
            if key in value:
                normalized = _sales_value(value.get(key))
                if normalized is not None:
                    return normalized

        if len(value) == 1:
            return _sales_value(next(iter(value.values())))
        return None

    if value is None or isinstance(value, bool):
        return None

    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(normalized) or normalized < 0:
        return None
    if normalized.is_integer():
        return int(normalized)
    return normalized


def _required_sales_value(value, field_name="units_sold"):
    normalized = _sales_value(value)
    if normalized is None:
        raise ValueError(f"{field_name} must be a non-negative number")
    return normalized


def _normalize_missing_history(value):
    if isinstance(value, (str, date, datetime)):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError as error:
            raise ValueError("missing_history must be a list") from error
    return [str(item) for item in values]


def _normalize_unknown_categories(value):
    if isinstance(value, dict):
        return {
            str(key): str(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]

# ==============================
# PRODUCT INVENTORY
# ==============================
def _product_ref(warehouse_id, product_id):
    return db.reference(
        f"warehouses/{str(warehouse_id)}/products/{str(product_id)}"
    )


def _warehouse_ref(warehouse_id):
    return db.reference(f"warehouses/{str(warehouse_id)}")


def get_product_stock(warehouse_id, product_id):
    value = _product_ref(
        warehouse_id,
        product_id
    ).child("stock").get()

    if value is None:
        return None

    return safe_int(value)


def get_product_data(warehouse_id, product_id):
    value = _product_ref(
        warehouse_id,
        product_id
    ).get()

    return value if isinstance(value, dict) else None


def record_product_daily_sales(
    warehouse_id,
    product_id,
    observation_date,
    units_sold,
):
    """Store one idempotent daily-sales total for a warehouse/product."""
    day = _normalize_iso_date(observation_date, "observation_date")
    sales = _required_sales_value(units_sold)
    history_ref = _product_ref(
        warehouse_id,
        product_id,
    ).child("sales_history")
    history_ref.child(day.isoformat()).set({
        "units_sold": sales,
        "updated_at": time.time(),
        "updated_at_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    history = history_ref.get() or {}
    if isinstance(history, dict):
        dated_keys = []
        for key in history:
            try:
                dated_keys.append((_normalize_iso_date(key), str(key)))
            except ValueError:
                continue
        dated_keys.sort()
        cutoff = day - timedelta(days=SALES_HISTORY_RETENTION_DAYS - 1)
        keys_to_delete = [key for item_date, key in dated_keys if item_date < cutoff]
        remaining = [item for item in dated_keys if item[1] not in keys_to_delete]
        if len(remaining) > SALES_HISTORY_RETENTION_DAYS:
            keys_to_delete.extend(
                key
                for _, key in remaining[:-SALES_HISTORY_RETENTION_DAYS]
            )
        for key in dict.fromkeys(keys_to_delete):
            history_ref.child(key).delete()

    return {
        "observation_date": day.isoformat(),
        "units_sold": sales,
    }


def get_product_sales_features(
    warehouse_id,
    product_id,
    observation_date,
    current_units_sold,
):
    """Build exact calendar sales features for forecast day t+1."""
    day = _normalize_iso_date(observation_date, "observation_date")
    current_sales = _required_sales_value(
        current_units_sold,
        "current_units_sold",
    )
    product = get_product_data(warehouse_id, product_id) or {}
    raw_history = product.get("sales_history", {})
    history = {}
    if isinstance(raw_history, dict):
        for key, value in raw_history.items():
            try:
                history[_normalize_iso_date(key)] = _sales_value(value)
            except ValueError:
                continue

    window_dates = [day - timedelta(days=offset) for offset in range(6, 0, -1)]
    previous_values = [history.get(item) for item in window_dates]
    missing_dates = [
        item.isoformat()
        for item, value in zip(window_dates, previous_values)
        if value is None
    ]
    window_values = previous_values + [current_sales]
    history_complete = not missing_dates

    return {
        "units_sold_lag_1": current_sales,
        "units_sold_lag_7": previous_values[0] if previous_values[0] is not None else None,
        "units_sold_rolling_mean_7": (
            sum(window_values) / len(window_values)
            if history_complete
            else None
        ),
        "history_complete": history_complete,
        "missing_history": missing_dates,
    }


def record_product_daily_demand(
    warehouse_id,
    product_id,
    observation_date,
    actual_demand,
):
    """Store actual daily demand separately from the model forecast."""
    day = _normalize_iso_date(observation_date, "observation_date")
    demand = _required_sales_value(actual_demand, "actual_demand")
    history_ref = _product_ref(
        warehouse_id, product_id
    ).child("demand_history")
    history_ref.child(day.isoformat()).set({
        "actual_demand": demand,
        "updated_at": time.time(),
        "updated_at_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    cutoff = day - timedelta(days=DEMAND_HISTORY_RETENTION_DAYS - 1)
    history = history_ref.get() or {}
    if isinstance(history, dict):
        for key in list(history):
            try:
                if _normalize_iso_date(key) < cutoff:
                    history_ref.child(str(key)).delete()
            except ValueError:
                continue
    return {"observation_date": day.isoformat(), "actual_demand": demand}


def get_product_demand_features(
    warehouse_id,
    product_id,
    observation_date,
    current_actual_demand=None,
):
    """Build leak-free demand lags/rolling statistics through day t."""
    day = _normalize_iso_date(observation_date, "observation_date")
    product = get_product_data(warehouse_id, product_id) or {}
    raw_history = product.get("demand_history", {})
    history = {}
    if isinstance(raw_history, dict):
        for key, value in raw_history.items():
            try:
                history[_normalize_iso_date(key)] = _sales_value(
                    value.get("actual_demand") if isinstance(value, dict) else value
                )
            except ValueError:
                continue
    current = _sales_value(current_actual_demand)
    if current is not None:
        history[day] = current

    def exact_lag(days):
        return history.get(day - timedelta(days=days - 1))

    def window(days):
        dates = [day - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
        values = [history.get(item) for item in dates]
        if any(value is None for value in values):
            return None, None, [
                item.isoformat() for item, value in zip(dates, values) if value is None
            ]
        mean = sum(values) / days
        variance = sum((value - mean) ** 2 for value in values) / max(days - 1, 1)
        return mean, math.sqrt(variance), []

    mean_7, std_7, missing_7 = window(7)
    mean_28, std_28, missing_28 = window(28)
    features = {
        "demand_lag_1": exact_lag(1),
        "demand_lag_7": exact_lag(7),
        "demand_lag_14": exact_lag(14),
        "demand_lag_28": exact_lag(28),
        "demand_rolling_mean_7": mean_7,
        "demand_rolling_mean_28": mean_28,
        "demand_rolling_std_7": std_7,
        "demand_rolling_std_28": std_28,
        "demand_trend_7_28": (
            mean_7 - mean_28 if mean_7 is not None and mean_28 is not None else None
        ),
    }
    missing = sorted(set(missing_7 + missing_28))
    features.update({
        "history_complete": not missing,
        "missing_history": missing,
    })
    return features


def set_product_stock(warehouse_id, product_id, quantity):
    quantity = max(0, safe_int(quantity))
    timestamp = time.time()

    _product_ref(warehouse_id, product_id).update({
        "warehouse_id": str(warehouse_id),
        "product_id": str(product_id),
        "stock": quantity,
        "last_updated": timestamp,
        "last_updated_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    return quantity


def deduct_product_stock(
    warehouse_id,
    product_id,
    order_quantity,
    order_id=None,
):
    quantity = max(0, safe_int(order_quantity))
    product_ref = _product_ref(warehouse_id, product_id)
    stock_ref = product_ref.child("stock")

    def deduct(current_stock):
        stock = safe_int(current_stock)
        if quantity > stock:
            raise ValueError(
                f"Không đủ tồn kho: còn {stock}, khách đặt {quantity}"
            )
        return stock - quantity

    new_stock = stock_ref.transaction(deduct)
    product_ref.update({
        "last_updated": time.time(),
        "last_updated_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    product_ref.child("inventory_movements").push({
        "type": "ORDER_DEDUCTION",
        "order_id": str(order_id or ""),
        "quantity": quantity,
        "stock_before": safe_int(new_stock) + quantity,
        "stock_after": safe_int(new_stock),
        "timestamp": time.time(),
        "time_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return safe_int(new_stock)


def add_product_stock(warehouse_id, product_id, incoming_quantity):
    quantity = max(0, safe_int(incoming_quantity))
    product_ref = _product_ref(warehouse_id, product_id)
    stock_ref = product_ref.child("stock")

    new_stock = stock_ref.transaction(
        lambda current_stock: safe_int(current_stock) + quantity
    )
    product_ref.update({
        "last_updated": time.time(),
        "last_updated_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    return safe_int(new_stock)


def rename_product_location(old_warehouse_id, old_product_id, new_warehouse_id, new_product_id):
    old_warehouse_id = str(old_warehouse_id).strip()
    old_product_id = str(old_product_id).strip()
    new_warehouse_id = str(new_warehouse_id).strip()
    new_product_id = str(new_product_id).strip()

    old_ref = _product_ref(old_warehouse_id, old_product_id)
    product_data = old_ref.get()
    if not isinstance(product_data, dict):
        raise ValueError(
            f"Không tìm thấy sản phẩm {old_product_id} trong kho {old_warehouse_id}."
        )

    same_path = (
        old_warehouse_id == new_warehouse_id and
        old_product_id == new_product_id
    )
    new_ref = _product_ref(new_warehouse_id, new_product_id)
    if not same_path and new_ref.get() is not None:
        raise ValueError(
            f"Sản phẩm {new_product_id} đã tồn tại trong kho {new_warehouse_id}."
        )

    timestamp = time.time()
    product_data.update({
        "warehouse_id": new_warehouse_id,
        "product_id": new_product_id,
        "last_updated": timestamp,
        "last_updated_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    new_ref.set(product_data)
    if not same_path:
        old_ref.delete()

    orders_ref = db.reference("orders")
    orders = orders_ref.get() or {}
    updated_orders = 0
    if isinstance(orders, dict):
        for order_id, order in orders.items():
            if not isinstance(order, dict):
                continue
            if (
                str(order.get("warehouse_id", "")) == old_warehouse_id and
                str(order.get("product_id", "")) == old_product_id
            ):
                orders_ref.child(str(order_id)).update({
                    "warehouse_id": new_warehouse_id,
                    "product_id": new_product_id,
                    "last_updated": timestamp,
                    "last_updated_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                updated_orders += 1

    return {
        "old_warehouse_id": old_warehouse_id,
        "old_product_id": old_product_id,
        "warehouse_id": new_warehouse_id,
        "product_id": new_product_id,
        "updated_orders": updated_orders,
    }


def rename_warehouse(old_warehouse_id, new_warehouse_id):
    old_warehouse_id = str(old_warehouse_id).strip()
    new_warehouse_id = str(new_warehouse_id).strip()

    if not old_warehouse_id or not new_warehouse_id:
        raise ValueError("Tên kho cũ và tên kho mới không được để trống.")

    old_ref = _warehouse_ref(old_warehouse_id)
    warehouse_data = old_ref.get()
    if not isinstance(warehouse_data, dict):
        raise ValueError(f"Không tìm thấy kho {old_warehouse_id}.")

    if old_warehouse_id == new_warehouse_id:
        return {
            "old_warehouse_id": old_warehouse_id,
            "warehouse_id": new_warehouse_id,
            "updated_products": len(warehouse_data.get("products", {})),
            "updated_orders": 0,
        }

    new_ref = _warehouse_ref(new_warehouse_id)
    if new_ref.get() is not None:
        raise ValueError(f"Kho {new_warehouse_id} đã tồn tại.")

    timestamp = time.time()
    timestamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    products = warehouse_data.get("products", {})
    if isinstance(products, dict):
        for product_id, product in products.items():
            if not isinstance(product, dict):
                continue
            product.update({
                "warehouse_id": new_warehouse_id,
                "product_id": str(product_id),
                "last_updated": timestamp,
                "last_updated_text": timestamp_text,
            })

    new_ref.set(warehouse_data)
    old_ref.delete()

    orders_ref = db.reference("orders")
    orders = orders_ref.get() or {}
    updated_orders = 0
    if isinstance(orders, dict):
        for order_id, order in orders.items():
            if not isinstance(order, dict):
                continue
            if str(order.get("warehouse_id", "")) == old_warehouse_id:
                orders_ref.child(str(order_id)).update({
                    "warehouse_id": new_warehouse_id,
                    "last_updated": timestamp,
                    "last_updated_text": timestamp_text,
                })
                updated_orders += 1

    return {
        "old_warehouse_id": old_warehouse_id,
        "warehouse_id": new_warehouse_id,
        "updated_products": len(products) if isinstance(products, dict) else 0,
        "updated_orders": updated_orders,
    }


def delete_warehouse(warehouse_id):
    warehouse_id = str(warehouse_id).strip()
    if not warehouse_id:
        raise ValueError("Tên kho không được để trống.")

    warehouse_ref = _warehouse_ref(warehouse_id)
    warehouse_data = warehouse_ref.get()
    if not isinstance(warehouse_data, dict):
        raise ValueError(f"Không tìm thấy kho {warehouse_id}.")

    products = warehouse_data.get("products", {})
    product_count = len(products) if isinstance(products, dict) else 0
    warehouse_ref.delete()

    return {
        "warehouse_id": warehouse_id,
        "deleted_products": product_count,
        "orders_preserved": True,
    }


def update_product_inventory_analysis(
    warehouse_id,
    product_id,
    future_demand,
    inventory_level,
    reorder_point,
    reorder_quantity,
    reorder_required,
    daily_sales=None,
    incoming_stock=None,
    category=None,
    region=None,
    units_sold=None,
    inventory_quantity=None,
    price=None,
    discount=None,
    weather_condition=None,
    promotion=None,
    competitor_pricing=None,
    seasonality=None,
    epidemic=None
):
    data = {
        "future_demand": safe_int(future_demand),
        "inventory_level": str(inventory_level),
        "reorder_point": safe_int(reorder_point),
        "reorder_quantity": safe_int(reorder_quantity),
        "reorder_required": bool(reorder_required),
        "last_updated": time.time(),
        "last_updated_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if daily_sales is not None:
        data["daily_sales"] = safe_int(daily_sales)
    if incoming_stock is not None:
        data["incoming_stock"] = safe_int(incoming_stock)
    if units_sold is not None:
        data["units_sold"] = safe_int(units_sold)
    if inventory_quantity is not None:
        data["inventory_quantity"] = safe_int(inventory_quantity)
    for key, value in {
        "category": category,
        "region": region,
        "weather_condition": weather_condition,
        "seasonality": seasonality,
    }.items():
        if value is not None:
            data[key] = str(value)
    for key, value in {
        "price": price,
        "discount": discount,
        "promotion": promotion,
        "competitor_pricing": competitor_pricing,
        "epidemic": epidemic,
    }.items():
        if value is not None:
            data[key] = safe_float(value)

    _product_ref(warehouse_id, product_id).update(data)


# ==============================
# UPDATE ORDER STATUS (SAFE)
# ==============================
def update_order_status(
    order_id,
    status,
    inventory,
    demand,
    inventory_level=None,

    warehouse_id=None,
    product_id=None,

    latitude=None,
    longitude=None,

    speed=None,
    fuel_level=None,
    vehicle_status=None,

    temperature=None,
    humidity=None,

    vibration=None,
    battery=None,

    eta=None,
    alert=None,
    progress=None,

    reorder_required=None,
    reorder_point=None,
    reorder_quantity=None,
    inventory_level_description=None,
    order_quantity=None,
    inventory_before=None,
    processed=True,
    processing_logs=None,
    processing_latency_ms=None,
    prediction_latency_ms=None,
    model_mode=None,
    model_version=None,
    fallback_used=False,
    prediction_error=None,
    server_completed_at_ms=None,
    daily_sales=None,
    incoming_stock=None,
    category=None,
    region=None,
    units_sold=None,
    inventory_quantity=None,
    price=None,
    discount=None,
    weather_condition=None,
    promotion=None,
    competitor_pricing=None,
    seasonality=None,
    epidemic=None,
    order_date=None,
    forecast_date=None,
    units_sold_lag_1=None,
    units_sold_lag_7=None,
    units_sold_rolling_mean_7=None,
    cold_start=False,
    fallback_reason=None,
    missing_history=None,
    unknown_categories=None,
    event_id=None
):

    try:
        ref = db.reference(f"orders/{order_id}")
        existing = ref.get() or {}

        timestamp = time.time()
        readable_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        inventory = safe_int(inventory)
        demand = safe_int(demand)

        # =========================
        # STATUS HISTORY
        # =========================
        status_history = existing.get("status_history", [])
        if not isinstance(status_history, list):
            status_history = []

        if not status_history or status_history[-1].get("status") != status:
            status_history.append({
                "status": status,
                "time": timestamp,
                "time_text": readable_time
            })

        status_history = status_history[-MAX_HISTORY:]

        # =========================
        # GPS HISTORY
        # =========================
        gps_history = existing.get("gps_history", [])
        if not isinstance(gps_history, list):
            gps_history = []

        if latitude is not None and longitude is not None:
            gps_history.append({
                "latitude": safe_float(latitude),
                "longitude": safe_float(longitude),
                "time": readable_time
            })

        gps_history = gps_history[-MAX_GPS_HISTORY:]

        # =========================
        # EVENTS
        # =========================
        events = existing.get("events", [])
        if not isinstance(events, list):
            events = []

        event_data = {
            "time": readable_time,
            "order_id": str(order_id),
            "status": str(status),
            "inventory": inventory,
            "inventory_before": safe_int(inventory_before, inventory),
            "order_quantity": safe_int(order_quantity),
            "incoming_stock": safe_int(incoming_stock),
            "units_sold": safe_int(units_sold),
            "inventory_quantity": safe_int(inventory_quantity),
            "processed": bool(processed),
            "future_demand": demand,
            "daily_sales": safe_int(daily_sales),
            "event": f"Order changed to {status}"
        }
        if order_date is not None:
            event_data["order_date"] = _normalize_iso_date(
                order_date, "order_date"
            ).isoformat()
        if forecast_date is not None:
            event_data["forecast_date"] = _normalize_iso_date(
                forecast_date, "forecast_date"
            ).isoformat()
        event_data["cold_start"] = bool(cold_start)
        events.append(event_data)

        events = events[-MAX_EVENTS:]

         # =========================
          # BUSINESS LOGIC
         # =========================

        inventory_level = str(
         inventory_level or "NORMAL"
    )

        reorder_point = safe_int(
            reorder_point,
            demand + 50
        )

        if not inventory_level_description:
            inventory_level_description = {
                "NORMAL": "Tồn kho an toàn",
                "LOW": "Tồn kho thấp",
                "CRITICAL": "Tồn kho rất thấp",
                "OUT_OF_STOCK": "Hết hàng"
            }.get(inventory_level, "Không xác định")

        stock_alert = (
            inventory_level in [
                "LOW",
                "CRITICAL",
                "OUT_OF_STOCK"
            ]
        )

        reorder_required = (
            stock_alert
            if reorder_required is None
            else bool(reorder_required)
        )
        prediction = (
             "Restock Required"
         if stock_alert
         else "Stock Sufficient"
         )


        if reorder_required:

         reorder_quantity = max(
            reorder_point - inventory,
            0
         )

        else:

          reorder_quantity = 0

        # =========================
        # MAIN DATA
        # =========================
        data = {
            "order_id": str(order_id),
            "status": str(status),
            "inventory": inventory,
            "inventory_before": safe_int(inventory_before, inventory),
            "order_quantity": safe_int(order_quantity),
            "incoming_stock": safe_int(incoming_stock),
            "units_sold": safe_int(units_sold),
            "inventory_quantity": safe_int(inventory_quantity),
            "processed": bool(processed),
            "future_demand": demand,
            "daily_sales": safe_int(daily_sales),

            "inventory_level": inventory_level,
            "inventory_level_description": str(inventory_level_description),
            "stock_alert": stock_alert,
            "prediction": prediction,

            "reorder_required": reorder_required,
            "reorder_point": reorder_point,
            "reorder_quantity": reorder_quantity,

            "last_updated": timestamp,
            "last_updated_text": readable_time,

            "status_history": status_history,
            "gps_history": gps_history,
            "events": events
        }

        if processing_logs is not None:
            data["processing_logs"] = list(processing_logs)
        if processing_latency_ms is not None:
            data["processing_latency_ms"] = safe_int(processing_latency_ms)
        if prediction_latency_ms is not None:
            data["prediction_latency_ms"] = safe_int(prediction_latency_ms)
        if model_mode:
            data["model_mode"] = str(model_mode)
        if model_version:
            data["model_version"] = str(model_version)
        data["fallback_used"] = bool(fallback_used)
        if prediction_error:
            data["prediction_error"] = str(prediction_error)
        if server_completed_at_ms is not None:
            data["server_completed_at_ms"] = safe_int(server_completed_at_ms)
        if order_date is not None:
            data["order_date"] = _normalize_iso_date(
                order_date, "order_date"
            ).isoformat()
        if forecast_date is not None:
            data["forecast_date"] = _normalize_iso_date(
                forecast_date, "forecast_date"
            ).isoformat()
        for key, value in {
            "units_sold_lag_1": units_sold_lag_1,
            "units_sold_lag_7": units_sold_lag_7,
            "units_sold_rolling_mean_7": units_sold_rolling_mean_7,
        }.items():
            normalized = _sales_value(value)
            if normalized is not None:
                data[key] = normalized
        data["cold_start"] = bool(cold_start)
        if fallback_reason:
            data["fallback_reason"] = str(fallback_reason)
        if missing_history is not None:
            data["missing_history"] = _normalize_missing_history(
                missing_history
            )
        if unknown_categories is not None:
            data["unknown_categories"] = _normalize_unknown_categories(
                unknown_categories
            )

        # =========================
        # OPTIONAL FIELDS SAFE
        # =========================
        if warehouse_id:
            data["warehouse_id"] = str(warehouse_id)

        if product_id:
            data["product_id"] = str(product_id)

        optional_text_fields = {
            "category": category,
            "region": region,
            "weather_condition": weather_condition,
            "seasonality": seasonality,
        }
        for key, value in optional_text_fields.items():
            if value is not None:
                data[key] = str(value)

        optional_number_fields = {
            "price": price,
            "discount": discount,
            "promotion": promotion,
            "competitor_pricing": competitor_pricing,
            "epidemic": epidemic,
        }
        for key, value in optional_number_fields.items():
            if value is not None:
                data[key] = safe_float(value)

        if latitude is not None:
            data["latitude"] = safe_float(latitude)

        if longitude is not None:
            data["longitude"] = safe_float(longitude)

        if speed is not None:
            data["speed"] = safe_float(speed)

        if fuel_level is not None:
            data["fuel_level"] = safe_float(fuel_level)

        if vehicle_status:
            data["vehicle_status"] = str(vehicle_status)

        if temperature is not None:
            data["temperature"] = safe_float(temperature)

        if humidity is not None:
            data["humidity"] = safe_float(humidity)
        
        if vibration is not None:
            data["vibration"] = safe_float(vibration)

        if battery is not None:
            data["battery"] = safe_float(battery)

        if eta is not None:
            data["eta"] = safe_int(eta)

        if alert:
            data["alert"] = str(alert)

        if progress is not None:
            data["progress"] = safe_int(progress)

        if event_id:
            data["event_id"] = str(event_id)

        # =========================
        # UPDATE FIREBASE
        # =========================
        ref.update(data)

        print(f"[FIREBASE] Updated {order_id}")

    except Exception as e:
        print("[FIREBASE ERROR]", e)


# ==============================
# GET FUNCTIONS
# ==============================
def get_order(order_id):
    try:
        return db.reference(f"orders/{order_id}").get()
    except:
        return None


def get_all_orders():
    try:
        return db.reference("orders").get()
    except:
        return {}


def clear_orders():
    try:
        db.reference("orders").delete()
        print("[FIREBASE] All orders deleted.")
    except Exception as e:
        print("[FIREBASE ERROR]", e)


# ==============================
# TEST
# ==============================
if __name__ == "__main__":

    clear_orders()

    update_order_status(
        order_id="ORD00001",
        status="accepted",
        inventory=250,
        demand=600,
        inventory_level="LOW",
        warehouse_id="WH01",
        product_id="PRD001",
        latitude=10.762622,
        longitude=106.660172,
        speed=55.5,
        fuel_level=87.4,
        vehicle_status="Moving",
        temperature=29.5,
        humidity=68.0,
        eta=15,
        alert="NORMAL",
        progress=70,
        event_id="TEST_EVENT_001"
    )

    print(get_order("ORD00001"))
    print("DONE")
