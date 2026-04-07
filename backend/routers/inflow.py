from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Body

from config import VARIANT_NAMES
from services.inflow_client import InflowClientError
from services import inflow_service
from services.cache_service import inflow_cache, _make_cache_key
from services.polling_service import full_refresh, _DETAILED_SO_PARAMS
import services.na_orders_service  # noqa: F401  (auto-registers callback)
import services.order_matrix_service  # noqa: F401  (auto-registers callback)

router = APIRouter(prefix="/inflow", tags=["inflow"])

_VALID_VARIANTS: frozenset[str] = frozenset(VARIANT_NAMES)


def _handle_inflow_error(exc: InflowClientError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def _validate_variant(variant: str) -> None:
    """Raise HTTP 400 if *variant* is not one of the four known training variants."""
    if variant not in _VALID_VARIANTS:
        raise HTTPException(status_code=400, detail=f"Invalid variant: {variant}")


# ── Dashboard ────────────────────────────────────────────────────────

@router.get("/dashboard-summary")
async def dashboard_summary():
    try:
        return await inflow_service.get_dashboard_summary()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Incremental Update ────────────────────────────────────────────────

@router.get("/update")
async def incremental_update():
    """Trigger an on-demand full data refresh from the Inflow API."""
    await full_refresh()
    return {"status": "ok"}


# ── Active Orders Today ───────────────────────────────────────────────

_TERMINAL_STATUSES = {"fulfilled", "completed", "cancelled", "canceled", "closed"}


def _build_active_row(row: Any) -> dict[str, Any] | None:
    """Return a cleaned row dict if the order is active, else None.

    Filters out completed orders and terminal-status orders; flattens nested
    customer/location dicts to plain name strings.
    """
    if row.get("isCompleted") == True:  # noqa: E712
        return None
    status: str = str(row.get("status") or "").lower()
    if status in _TERMINAL_STATUSES:
        return None
    row_dict = {k: inflow_cache._scrub_value(v) for k, v in row.items()}
    customer = row_dict.get("customer")
    if isinstance(customer, dict):
        row_dict["customer"] = customer.get("name") or customer.get("customerName") or ""
    location = row_dict.get("location")
    if isinstance(location, dict):
        row_dict["location"] = location.get("name") or location.get("locationName") or ""
    return row_dict


@router.get("/active-orders-week")
async def get_active_orders_week():
    """Return this week's sales orders (Saturday–Friday) that have not been completed.

    Filters the cached detailed sales orders to:
      - orderDate falls within the current Sat–Fri week
      - isCompleted is not True
      - status is not a terminal state (fulfilled/completed/cancelled/closed)

    Falls back to the plain sales-orders cache if the detailed cache is empty
    (e.g. if the detailed fetch failed due to a transient API error).
    """
    today = date.today()
    # Week runs Saturday → Friday.
    # weekday(): Mon=0 … Sat=5, Sun=6  →  days back to last Saturday = (weekday - 5) % 7
    days_since_saturday = (today.weekday() - 5) % 7
    week_start = today - timedelta(days=days_since_saturday)
    week_end = week_start + timedelta(days=6)          # the following Friday
    week_start_str = week_start.isoformat()            # e.g. "2026-02-21"
    week_end_str = week_end.isoformat()                # e.g. "2026-02-27"

    # Prefer detailed cache (includes customer/location); fall back to plain SO cache.
    so_key = _make_cache_key("sales-orders", _DETAILED_SO_PARAMS)
    entry = inflow_cache.get_entry(so_key)
    if entry is None or entry.df.empty:
        entry = inflow_cache.get_entry("sales-orders")

    if entry is None or entry.df.empty:
        return {"data": [], "hasMore": False, "totalCount": 0}

    active: list[dict[str, Any]] = []
    for _, row in entry.df.iterrows():
        # Extract the YYYY-MM-DD date portion regardless of time/timezone suffix.
        order_date_prefix: str = str(row.get("orderDate") or "")[:10]
        if not order_date_prefix or order_date_prefix < week_start_str or order_date_prefix > week_end_str:
            continue
        built = _build_active_row(row)
        if built is not None:
            active.append(built)

    active.sort(key=lambda r: str(r.get("orderDate") or ""))
    return {"data": active, "hasMore": False, "totalCount": len(active)}


# ── All Active Orders ─────────────────────────────────────────────────

@router.get("/active-orders")
async def get_active_orders():
    """Return all active (non-completed, non-terminal) sales orders regardless of date."""
    so_key = _make_cache_key("sales-orders", _DETAILED_SO_PARAMS)
    entry = inflow_cache.get_entry(so_key)
    if entry is None or entry.df.empty:
        entry = inflow_cache.get_entry("sales-orders")

    if entry is None or entry.df.empty:
        return {"data": [], "hasMore": False, "totalCount": 0}

    active: list[dict[str, Any]] = []
    for _, row in entry.df.iterrows():
        built = _build_active_row(row)
        if built is not None:
            active.append(built)

    active.sort(key=lambda r: str(r.get("orderDate") or ""), reverse=True)
    return {"data": active, "hasMore": False, "totalCount": len(active)}


# ── Roast stock ──────────────────────────────────────────────────────

_ROAST_SKUS: dict[str, str] = {
    "IF5127699": "Light Roast Coffee",
    "IF5127705": "Medium Roast Coffee",
    "IF5127683": "Dark Roast Coffee",
}

_PRODUCTS_INCLUDE = "inventoryLines,category,defaultPrice"


def _compute_qty(product: dict) -> int:
    lines = product.get("inventoryLines") or []
    if isinstance(lines, list) and lines:
        try:
            total = sum(float(l.get("quantityOnHand") or 0) for l in lines if isinstance(l, dict))
            if total > 0:
                return round(total)
        except (TypeError, ValueError):
            pass
    for field in ("quantityOnHand", "totalQuantityOnHand"):
        qty = product.get(field)
        if qty is not None:
            try:
                v = round(float(qty))
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
    return 0


@router.get("/roast-stock")
async def get_roast_stock():
    """Return current stock for the three roast products, looked up by SKU."""
    cached = inflow_cache.get("products", {"include": _PRODUCTS_INCLUDE})
    if cached is None:
        # Cache cold — fetch live and let it warm up.
        cached = await inflow_service.list_products({"include": _PRODUCTS_INCLUDE})
    products: list[dict] = (cached or {}).get("data", [])

    result = []
    for sku, name in _ROAST_SKUS.items():
        match = next(
            (p for p in products if (p.get("sku") or "").strip() == sku), None
        )
        result.append({
            "sku": sku,
            "name": name,
            "stock": _compute_qty(match) if match else 0,
        })

    return {"data": result}


# ── Products ─────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(include: str | None = None):
    try:
        params = {"include": include} if include else None
        return await inflow_service.list_products(params)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/products/{product_id}")
async def get_product(product_id: int):
    try:
        return await inflow_service.get_product(product_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/products")
async def upsert_product(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_product(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.post("/products/summary")
async def product_summary(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.get_product_summary(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Customers ────────────────────────────────────────────────────────

@router.get("/customers")
async def list_customers():
    try:
        return await inflow_service.list_customers()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: int):
    try:
        return await inflow_service.get_customer(customer_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/customers")
async def upsert_customer(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_customer(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Vendors ──────────────────────────────────────────────────────────

@router.get("/vendors")
async def list_vendors():
    try:
        return await inflow_service.list_vendors()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: int):
    try:
        return await inflow_service.get_vendor(vendor_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/vendors")
async def upsert_vendor(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_vendor(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Sales Orders ─────────────────────────────────────────────────────

@router.get("/sales-orders")
async def list_sales_orders(include: str | None = None):
    try:
        params = {"include": include} if include else None
        return await inflow_service.list_sales_orders(params)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/sales-orders/{order_id}")
async def get_sales_order(order_id: str):
    try:
        return await inflow_service.get_sales_order(order_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/sales-orders")
async def upsert_sales_order(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_sales_order(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Purchase Orders ──────────────────────────────────────────────────

@router.get("/purchase-orders")
async def list_purchase_orders():
    try:
        return await inflow_service.list_purchase_orders()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/purchase-orders/{order_id}")
async def get_purchase_order(order_id: int):
    try:
        return await inflow_service.get_purchase_order(order_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/purchase-orders")
async def upsert_purchase_order(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_purchase_order(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Locations ────────────────────────────────────────────────────────

@router.get("/locations")
async def list_locations():
    try:
        return await inflow_service.list_locations()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/locations/{location_id}")
async def get_location(location_id: int):
    try:
        return await inflow_service.get_location(location_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Categories ───────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories():
    try:
        return await inflow_service.list_categories()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/categories/{category_id}")
async def get_category(category_id: int):
    try:
        return await inflow_service.get_category(category_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Stock Adjustments ────────────────────────────────────────────────

@router.get("/stock-adjustments")
async def list_stock_adjustments():
    try:
        return await inflow_service.list_stock_adjustments()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/stock-adjustments/{adjustment_id}")
async def get_stock_adjustment(adjustment_id: int):
    try:
        return await inflow_service.get_stock_adjustment(adjustment_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/stock-adjustments")
async def upsert_stock_adjustment(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_stock_adjustment(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Stock Transfers ──────────────────────────────────────────────────

@router.get("/stock-transfers")
async def list_stock_transfers():
    try:
        return await inflow_service.list_stock_transfers()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/stock-transfers/{transfer_id}")
async def get_stock_transfer(transfer_id: int):
    try:
        return await inflow_service.get_stock_transfer(transfer_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/stock-transfers")
async def upsert_stock_transfer(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_stock_transfer(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Stock Counts ─────────────────────────────────────────────────────

@router.get("/stock-counts")
async def list_stock_counts():
    try:
        return await inflow_service.list_stock_counts()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/stock-counts/{count_id}")
async def get_stock_count(count_id: int):
    try:
        return await inflow_service.get_stock_count(count_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/stock-counts")
async def upsert_stock_count(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_stock_count(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Manufacturing Orders ─────────────────────────────────────────────

@router.get("/manufacturing-orders")
async def list_manufacturing_orders():
    try:
        return await inflow_service.list_manufacturing_orders()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/manufacturing-orders/{order_id}")
async def get_manufacturing_order(order_id: int):
    try:
        return await inflow_service.get_manufacturing_order(order_id)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/manufacturing-orders")
async def upsert_manufacturing_order(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_manufacturing_order(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Reference data ───────────────────────────────────────────────────

@router.get("/currencies")
async def list_currencies():
    try:
        return await inflow_service.list_currencies()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/tax-codes")
async def list_tax_codes():
    try:
        return await inflow_service.list_tax_codes()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/payment-terms")
async def list_payment_terms():
    try:
        return await inflow_service.list_payment_terms()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/pricing-schemes")
async def list_pricing_schemes():
    try:
        return await inflow_service.list_pricing_schemes()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/adjustment-reasons")
async def list_adjustment_reasons():
    try:
        return await inflow_service.list_adjustment_reasons()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/operation-types")
async def list_operation_types():
    try:
        return await inflow_service.list_operation_types()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Team / Stockroom Users ───────────────────────────────────────────

@router.get("/team-members")
async def list_team_members():
    try:
        return await inflow_service.list_team_members()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.get("/stockroom-users")
async def list_stockroom_users():
    try:
        return await inflow_service.list_stockroom_users()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Webhooks ─────────────────────────────────────────────────────────

@router.get("/webhooks")
async def list_webhooks():
    try:
        return await inflow_service.list_webhooks()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.put("/webhooks")
async def upsert_webhook(body: dict[str, Any] = Body(...)):
    try:
        return await inflow_service.upsert_webhook(body)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int):
    try:
        await inflow_service.delete_webhook(webhook_id)
        return {"detail": "deleted"}
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Custom Fields ────────────────────────────────────────────────────

@router.get("/custom-fields")
async def list_custom_fields():
    try:
        return await inflow_service.list_custom_fields()
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Derived Order Frames ────────────────────────────────────────────

@router.get("/franchise-store-orders")
async def list_franchise_store_orders():
    data = inflow_cache.get("franchise_store_orders")
    if data is None:
        raise HTTPException(status_code=404, detail="Franchise store orders not yet available. Fetch sales orders first.")
    return data


@router.get("/na-franchise-orders")
async def list_na_franchise_orders():
    data = inflow_cache.get("na_franchise_orders")
    if data is None:
        raise HTTPException(status_code=404, detail="North America franchise orders not yet available. Fetch sales orders first.")
    return data


@router.get("/online-orders")
async def list_online_orders():
    data = inflow_cache.get("online_orders")
    if data is None:
        raise HTTPException(status_code=404, detail="Online orders not yet available. Fetch sales orders first.")
    return data


# ── Franchise Location Frames ────────────────────────────────────────

@router.get("/franchise-location-orders/cities")
async def list_franchise_location_cities():
    """Return city list derived from the order matrix + latest franchise orders."""
    matrix = inflow_cache.get("franchise_order_matrix")
    latest = inflow_cache.get("latest_franchise_orders")
    if matrix is None and latest is None:
        raise HTTPException(
            status_code=404,
            detail="Order matrix not yet available. Fetch detailed sales orders first.",
        )

    all_rows = (matrix["data"] if matrix else []) + (latest["data"] if latest else [])
    city_set: set[str] = set()
    for row in all_rows:
        for key in row:
            if key.startswith("loc_") and row[key] == 1:
                city_set.add(key[4:])
                break

    cities = sorted(
        [{"citySlug": c, "displayName": c.replace("_", " ").title()} for c in city_set],
        key=lambda x: x["displayName"],
    )
    return {"data": cities, "hasMore": False, "totalCount": len(cities)}


@router.get("/franchise-location-orders/{city_slug}")
async def get_franchise_location_orders(city_slug: str):
    """Return orders for a city from the order matrix + latest franchise orders."""
    from services.cache_service import _make_cache_key

    matrix = inflow_cache.get("franchise_order_matrix")
    latest = inflow_cache.get("latest_franchise_orders")
    if matrix is None and latest is None:
        raise HTTPException(
            status_code=404,
            detail="Order matrix not yet available. Fetch detailed sales orders first.",
        )

    # Build order-number -> total lookup from raw sales orders
    order_totals: dict[str, float] = {}
    so_key = _make_cache_key("sales-orders", _DETAILED_SO_PARAMS)
    so_entry = inflow_cache.get_entry(so_key)
    if so_entry is not None and not so_entry.df.empty:
        for _, so_row in so_entry.df.iterrows():
            on = so_row.get("orderNumber")
            total = so_row.get("total")
            if on and total is not None:
                try:
                    order_totals[on] = float(total)
                except (ValueError, TypeError):
                    pass

    loc_key = f"loc_{city_slug}"
    all_rows = (matrix["data"] if matrix else []) + (latest["data"] if latest else [])
    city_rows = [r for r in all_rows if r.get(loc_key) == 1]

    # Build cleaned response rows
    prod_keys = sorted(k for k in (city_rows[0] if city_rows else {}) if k.startswith("prod_"))
    result = []
    for r in city_rows:
        products = {
            k[5:].replace("_", " ").title(): r[k]
            for k in prod_keys if r.get(k, 0) > 0
        }
        day = r.get("orderDay")
        month = r.get("orderMonth")
        year = r.get("orderYear")
        order_date = f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}" if year and month and day else None

        nday = r.get("nextOrderDay")
        nmonth = r.get("nextOrderMonth")
        nyear = r.get("nextOrderYear")
        next_order_date = f"{nyear}-{str(nmonth).zfill(2)}-{str(nday).zfill(2)}" if nyear and nmonth and nday else None

        total_qty = sum(r.get(k, 0) for k in prod_keys)

        # Sum totals for all order numbers (may be comma-separated from merging)
        order_nums = [s.strip() for s in (r.get("orderNumber") or "").split(",") if s.strip()]
        order_total = sum(order_totals.get(on, 0) for on in order_nums)

        result.append({
            "orderNumber": r.get("orderNumber", ""),
            "contactName": r.get("contactName", ""),
            "orderDate": order_date,
            "nextOrderDate": next_order_date,
            "orderSize": r.get("order_size"),
            "totalQty": total_qty,
            "orderTotal": round(order_total, 2) if order_total else None,
            "products": products,
        })

    # Sort by date descending
    result.sort(key=lambda x: x.get("orderDate") or "", reverse=True)
    return {"data": result, "hasMore": False, "totalCount": len(result)}


# ── Franchise Order Matrix ──────────────────────────────────────────

@router.get("/franchise-order-matrix")
async def get_franchise_order_matrix():
    data = inflow_cache.get("franchise_order_matrix")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Franchise order matrix not yet available. Fetch detailed sales orders first.",
        )
    return data


# ── Latest Franchise Orders ────────────────────────────────────────

@router.get("/latest-franchise-orders")
async def get_latest_franchise_orders():
    data = inflow_cache.get("latest_franchise_orders")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Latest franchise orders not yet available. Fetch detailed sales orders first.",
        )
    return data


# ── Franchise Product Matrix ──────────────────────────────────────────

@router.get("/franchise-product-matrix")
async def get_franchise_product_matrix():
    data = inflow_cache.get("franchise_product_matrix_base")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Franchise product matrix not yet available. Fetch detailed sales orders first.",
        )
    return data


# ── Latest Franchise Product Orders ──────────────────────────────────

@router.get("/latest-franchise-product-orders")
async def get_latest_franchise_product_orders():
    data = inflow_cache.get("latest_franchise_product_orders_base")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Latest franchise product orders not yet available. Fetch detailed sales orders first.",
        )
    return data


# ── Predicted Next Order Date ────────────────────────────────────────

@router.get("/predicted-next-order-date")
async def get_predicted_next_order_date():
    data = inflow_cache.get("predicted_next_order_date")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Predictions not yet available. Train the model first.",
        )
    return data


@router.get("/predicted-next-order-date/{variant}")
async def get_variant_predictions(variant: str):
    _validate_variant(variant)
    cache_key = f"predicted_next_order_date_{variant}"
    data = inflow_cache.get(cache_key)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Predictions for variant '{variant}' not yet available. Train the model first.",
        )
    return data


@router.get("/todays-predicted-orders")
async def get_todays_predicted_orders_base():
    data = inflow_cache.get("todays_predicted_orders_base")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Today's predicted orders not yet available. Train the model first.",
        )
    return data


@router.get("/todays-predicted-orders/{variant}")
async def get_todays_predicted_orders(variant: str):
    _validate_variant(variant)
    data = inflow_cache.get(f"todays_predicted_orders_{variant}")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Today's predicted orders for variant '{variant}' not yet available. Train the model first.",
        )
    return data


@router.get("/predicted-next-products/{variant}")
async def get_variant_product_predictions(variant: str):
    _validate_variant(variant)
    cache_key = f"predicted_next_products_{variant}"
    data = inflow_cache.get(cache_key)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product predictions for variant '{variant}' not yet available. Train the product model first.",
        )
    return data


@router.get("/predicted-orderdate-with-products/{variant}")
async def get_combined_predictions(variant: str):
    _validate_variant(variant)
    cache_key = f"predicted_orderdate_with_products_{variant}"
    data = inflow_cache.get(cache_key)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Combined predictions for variant '{variant}' not yet available. Train both order and product models first.",
        )
    return data
