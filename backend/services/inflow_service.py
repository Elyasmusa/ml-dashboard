from __future__ import annotations

import logging
from typing import Any

from services.inflow_client import inflow_client
from services.cache_service import inflow_cache
from schemas.inflow import InflowDashboardSummary
import services.derived_frames_service  # noqa: F401 — registers callbacks on import
import services.location_frames_service  # noqa: F401 — registers location callbacks on import

logger = logging.getLogger(__name__)

_PAGE_COUNT = 100  # Max 100 per request per Inflow API
_MAX_PAGES = 100   # Safety limit to prevent infinite pagination loops


async def _fetch_all_pages(endpoint: str, extra_params: dict[str, Any] | None = None) -> dict:
    """Auto-paginate using Inflow API params, with DataFrame caching.

    1. Check cache → return immediately on hit
    2. Acquire per-key lock (prevents thundering herd)
    3. Re-check cache (another coroutine may have populated it)
    4. Fetch all pages from API
    5. Store in cache (only updates if data actually changed)
    6. Return response
    """
    # Fast path: cache hit
    cached = inflow_cache.get(endpoint, extra_params)
    if cached is not None:
        logger.debug("Cache hit for %s", endpoint)
        return cached

    # Acquire per-endpoint lock to prevent duplicate fetches
    lock = await inflow_cache.get_lock_for(endpoint, extra_params)
    async with lock:
        # Double-check after lock acquisition
        cached = inflow_cache.get(endpoint, extra_params)
        if cached is not None:
            logger.debug("Cache hit (post-lock) for %s", endpoint)
            return cached

        # Fetch all pages from the Inflow API
        all_data: list[Any] = []
        skip = 0
        total_count = None

        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "count": str(_PAGE_COUNT),
                "skip": str(skip),
                "includeCount": "true",
            }
            if extra_params:
                params.update(extra_params)

            raw, list_count = await inflow_client.get_paged(endpoint, params=params)

            if total_count is None and list_count is not None:
                total_count = list_count

            if isinstance(raw, list):
                page_data = raw
            elif isinstance(raw, dict):
                page_data = raw.get("data", raw.get("items", []))
            else:
                page_data = []

            all_data.extend(page_data)

            if len(page_data) != _PAGE_COUNT:
                break
            if total_count is not None and len(all_data) >= total_count:
                break
            skip += len(page_data)

        final_count = total_count if total_count is not None else len(all_data)

        # Store in DataFrame cache, then always return from cache
        inflow_cache.put(endpoint, all_data, final_count, extra_params)
        return inflow_cache.get(endpoint, extra_params)


_RECENT_ORDERS_LIMIT = 5


# ── Products ─────────────────────────────────────────────────────────

async def list_products(extra_params: dict[str, Any] | None = None) -> dict:
    return await _fetch_all_pages("products", extra_params)


async def get_product(product_id: int) -> dict:
    return await inflow_client.get(f"products/{product_id}")


async def upsert_product(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("products", json=body)
    inflow_cache.invalidate("products")
    return result


async def get_product_summary(body: dict[str, Any]) -> dict:
    return await inflow_client.post("products/summary", json=body)


# ── Customers ────────────────────────────────────────────────────────

async def list_customers() -> dict:
    return await _fetch_all_pages("customers")


async def get_customer(customer_id: int) -> dict:
    return await inflow_client.get(f"customers/{customer_id}")


async def upsert_customer(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("customers", json=body)
    inflow_cache.invalidate("customers")
    return result


# ── Vendors ──────────────────────────────────────────────────────────

async def list_vendors() -> dict:
    return await _fetch_all_pages("vendors")


async def get_vendor(vendor_id: int) -> dict:
    return await inflow_client.get(f"vendors/{vendor_id}")


async def upsert_vendor(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("vendors", json=body)
    inflow_cache.invalidate("vendors")
    return result


# ── Sales Orders ─────────────────────────────────────────────────────

async def list_sales_orders(extra_params: dict[str, Any] | None = None) -> dict:
    return await _fetch_all_pages("sales-orders", extra_params)


async def get_sales_order(order_id: str) -> dict:
    return await inflow_client.get(f"sales-orders/{order_id}")


async def upsert_sales_order(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("sales-orders", json=body)
    inflow_cache.invalidate("sales-orders")
    return result


# ── Purchase Orders ──────────────────────────────────────────────────

async def list_purchase_orders() -> dict:
    return await _fetch_all_pages("purchase-orders")


async def get_purchase_order(order_id: int) -> dict:
    return await inflow_client.get(f"purchase-orders/{order_id}")


async def upsert_purchase_order(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("purchase-orders", json=body)
    inflow_cache.invalidate("purchase-orders")
    return result


# ── Locations ────────────────────────────────────────────────────────

async def list_locations() -> dict:
    return await _fetch_all_pages("locations")


async def get_location(location_id: int) -> dict:
    return await inflow_client.get(f"locations/{location_id}")


# ── Categories ───────────────────────────────────────────────────────

async def list_categories() -> dict:
    return await _fetch_all_pages("categories")


async def get_category(category_id: int) -> dict:
    return await inflow_client.get(f"categories/{category_id}")


# ── Stock Adjustments ────────────────────────────────────────────────

async def list_stock_adjustments() -> dict:
    return await _fetch_all_pages("stock-adjustments")


async def get_stock_adjustment(adjustment_id: int) -> dict:
    return await inflow_client.get(f"stock-adjustments/{adjustment_id}")


async def upsert_stock_adjustment(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("stock-adjustments", json=body)
    inflow_cache.invalidate("stock-adjustments")
    return result


# ── Stock Transfers ──────────────────────────────────────────────────

async def list_stock_transfers() -> dict:
    return await _fetch_all_pages("stock-transfers")


async def get_stock_transfer(transfer_id: int) -> dict:
    return await inflow_client.get(f"stock-transfers/{transfer_id}")


async def upsert_stock_transfer(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("stock-transfers", json=body)
    inflow_cache.invalidate("stock-transfers")
    return result


# ── Stock Counts ─────────────────────────────────────────────────────

async def list_stock_counts() -> dict:
    return await _fetch_all_pages("stock-counts")


async def get_stock_count(count_id: int) -> dict:
    return await inflow_client.get(f"stock-counts/{count_id}")


async def upsert_stock_count(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("stock-counts", json=body)
    inflow_cache.invalidate("stock-counts")
    return result


# ── Manufacturing Orders ─────────────────────────────────────────────

async def list_manufacturing_orders() -> dict:
    return await _fetch_all_pages("manufacturing-orders")


async def get_manufacturing_order(order_id: int) -> dict:
    return await inflow_client.get(f"manufacturing-orders/{order_id}")


async def upsert_manufacturing_order(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("manufacturing-orders", json=body)
    inflow_cache.invalidate("manufacturing-orders")
    return result


# ── Reference data ───────────────────────────────────────────────────

async def list_currencies() -> dict:
    return await _fetch_all_pages("currencies")


async def list_tax_codes() -> dict:
    return await _fetch_all_pages("tax-codes")


async def list_payment_terms() -> dict:
    return await _fetch_all_pages("payment-terms")


async def list_pricing_schemes() -> dict:
    return await _fetch_all_pages("pricing-schemes")


async def list_adjustment_reasons() -> dict:
    return await _fetch_all_pages("adjustment-reasons")


async def list_operation_types() -> dict:
    return await _fetch_all_pages("operation-types")


# ── Team / Stockroom Users ───────────────────────────────────────────

async def list_team_members() -> dict:
    return await _fetch_all_pages("team-members")


async def list_stockroom_users() -> dict:
    return await _fetch_all_pages("stockroom-users")


# ── Webhooks ─────────────────────────────────────────────────────────

async def list_webhooks() -> dict:
    return await _fetch_all_pages("webhooks")


async def upsert_webhook(body: dict[str, Any]) -> dict:
    result = await inflow_client.put("webhooks", json=body)
    inflow_cache.invalidate("webhooks")
    return result


async def delete_webhook(webhook_id: int) -> None:
    await inflow_client.delete(f"webhooks/{webhook_id}")
    inflow_cache.invalidate("webhooks")


# ── Custom Fields ────────────────────────────────────────────────────

async def list_custom_fields() -> dict:
    return await _fetch_all_pages("custom-fields")


# ── Dashboard summary ────────────────────────────────────────────────

async def get_dashboard_summary() -> dict:
    """Aggregate high-level stats from several Inflow endpoints.

    All data is served from the DataFrame cache. If a cache entry is
    missing, _fetch_all_pages populates it first (API → DataFrame → cache).
    """
    # Ensure every endpoint is in the cache (no-op if already cached)
    products = await _fetch_all_pages("products")
    customers = await _fetch_all_pages("customers")
    vendors = await _fetch_all_pages("vendors")
    sales = await _fetch_all_pages("sales-orders")
    purchases = await _fetch_all_pages("purchase-orders")

    return InflowDashboardSummary(
        productsCount=products["totalCount"],
        customersCount=customers["totalCount"],
        vendorsCount=vendors["totalCount"],
        salesOrdersCount=sales["totalCount"],
        purchaseOrdersCount=purchases["totalCount"],
        recentSalesOrders=(sales["data"] or [])[:_RECENT_ORDERS_LIMIT],
        recentPurchaseOrders=(purchases["data"] or [])[:_RECENT_ORDERS_LIMIT],
    ).model_dump()
