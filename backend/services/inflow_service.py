from __future__ import annotations

import logging
from typing import Any

from services.inflow_client import inflow_client
from schemas.inflow import (
    InflowDashboardSummary,
    InflowListResponse,
)

logger = logging.getLogger(__name__)


def _list_response(raw: Any) -> dict:
    """Normalise a raw Inflow list response into InflowListResponse shape."""
    if isinstance(raw, dict):
        return InflowListResponse(
            data=raw.get("data", raw.get("items", [])),
            hasMore=raw.get("hasMore", False),
            totalCount=raw.get("totalCount"),
        ).model_dump()
    return InflowListResponse(data=raw if isinstance(raw, list) else []).model_dump()


# ── Products ─────────────────────────────────────────────────────────

async def list_products(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("products", params=params)
    return _list_response(raw)


async def get_product(product_id: int) -> dict:
    return await inflow_client.get(f"products/{product_id}")


async def upsert_product(body: dict[str, Any]) -> dict:
    return await inflow_client.put("products", json=body)


async def get_product_summary(body: dict[str, Any]) -> dict:
    return await inflow_client.post("products/summary", json=body)


# ── Customers ────────────────────────────────────────────────────────

async def list_customers(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("customers", params=params)
    return _list_response(raw)


async def get_customer(customer_id: int) -> dict:
    return await inflow_client.get(f"customers/{customer_id}")


async def upsert_customer(body: dict[str, Any]) -> dict:
    return await inflow_client.put("customers", json=body)


# ── Vendors ──────────────────────────────────────────────────────────

async def list_vendors(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("vendors", params=params)
    return _list_response(raw)


async def get_vendor(vendor_id: int) -> dict:
    return await inflow_client.get(f"vendors/{vendor_id}")


async def upsert_vendor(body: dict[str, Any]) -> dict:
    return await inflow_client.put("vendors", json=body)


# ── Sales Orders ─────────────────────────────────────────────────────

async def list_sales_orders(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("sales-orders", params=params)
    return _list_response(raw)


async def get_sales_order(order_id: str) -> dict:
    return await inflow_client.get(f"sales-orders/{order_id}")


async def upsert_sales_order(body: dict[str, Any]) -> dict:
    return await inflow_client.put("sales-orders", json=body)


# ── Purchase Orders ──────────────────────────────────────────────────

async def list_purchase_orders(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("purchase-orders", params=params)
    return _list_response(raw)


async def get_purchase_order(order_id: int) -> dict:
    return await inflow_client.get(f"purchase-orders/{order_id}")


async def upsert_purchase_order(body: dict[str, Any]) -> dict:
    return await inflow_client.put("purchase-orders", json=body)


# ── Locations ────────────────────────────────────────────────────────

async def list_locations(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("locations", params=params)
    return _list_response(raw)


async def get_location(location_id: int) -> dict:
    return await inflow_client.get(f"locations/{location_id}")


# ── Categories ───────────────────────────────────────────────────────

async def list_categories(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("categories", params=params)
    return _list_response(raw)


async def get_category(category_id: int) -> dict:
    return await inflow_client.get(f"categories/{category_id}")


# ── Stock Adjustments ────────────────────────────────────────────────

async def list_stock_adjustments(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("stock-adjustments", params=params)
    return _list_response(raw)


async def get_stock_adjustment(adjustment_id: int) -> dict:
    return await inflow_client.get(f"stock-adjustments/{adjustment_id}")


async def upsert_stock_adjustment(body: dict[str, Any]) -> dict:
    return await inflow_client.put("stock-adjustments", json=body)


# ── Stock Transfers ──────────────────────────────────────────────────

async def list_stock_transfers(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("stock-transfers", params=params)
    return _list_response(raw)


async def get_stock_transfer(transfer_id: int) -> dict:
    return await inflow_client.get(f"stock-transfers/{transfer_id}")


async def upsert_stock_transfer(body: dict[str, Any]) -> dict:
    return await inflow_client.put("stock-transfers", json=body)


# ── Stock Counts ─────────────────────────────────────────────────────

async def list_stock_counts(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("stock-counts", params=params)
    return _list_response(raw)


async def get_stock_count(count_id: int) -> dict:
    return await inflow_client.get(f"stock-counts/{count_id}")


async def upsert_stock_count(body: dict[str, Any]) -> dict:
    return await inflow_client.put("stock-counts", json=body)


# ── Manufacturing Orders ─────────────────────────────────────────────

async def list_manufacturing_orders(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("manufacturing-orders", params=params)
    return _list_response(raw)


async def get_manufacturing_order(order_id: int) -> dict:
    return await inflow_client.get(f"manufacturing-orders/{order_id}")


async def upsert_manufacturing_order(body: dict[str, Any]) -> dict:
    return await inflow_client.put("manufacturing-orders", json=body)


# ── Reference data ───────────────────────────────────────────────────

async def list_currencies(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("currencies", params=params)
    return _list_response(raw)


async def list_tax_codes(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("tax-codes", params=params)
    return _list_response(raw)


async def list_payment_terms(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("payment-terms", params=params)
    return _list_response(raw)


async def list_pricing_schemes(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("pricing-schemes", params=params)
    return _list_response(raw)


async def list_adjustment_reasons(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("adjustment-reasons", params=params)
    return _list_response(raw)


async def list_operation_types(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("operation-types", params=params)
    return _list_response(raw)


# ── Team / Stockroom Users ───────────────────────────────────────────

async def list_team_members(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("team-members", params=params)
    return _list_response(raw)


async def list_stockroom_users(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("stockroom-users", params=params)
    return _list_response(raw)


# ── Webhooks ─────────────────────────────────────────────────────────

async def list_webhooks(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("webhooks", params=params)
    return _list_response(raw)


async def upsert_webhook(body: dict[str, Any]) -> dict:
    return await inflow_client.put("webhooks", json=body)


async def delete_webhook(webhook_id: int) -> None:
    await inflow_client.delete(f"webhooks/{webhook_id}")


# ── Custom Fields ────────────────────────────────────────────────────

async def list_custom_fields(params: dict[str, Any] | None = None) -> dict:
    raw = await inflow_client.get("custom-fields", params=params)
    return _list_response(raw)


# ── Dashboard summary ────────────────────────────────────────────────

async def get_dashboard_summary(limit: int = 5) -> dict:
    """Aggregate high-level stats from several Inflow endpoints."""
    # Use a small limit for counts and the provided `limit` for recent lists
    products = await list_products({"limit": "1"})
    customers = await list_customers({"limit": "1"})
    vendors = await list_vendors({"limit": "1"})
    sales = await list_sales_orders({"limit": str(limit)})
    purchases = await list_purchase_orders({"limit": str(limit)})

    # Ensure the returned lists are trimmed to `limit` regardless of upstream behavior
    recent_sales = (sales.get("data", []) or [])[:limit]
    recent_purchases = (purchases.get("data", []) or [])[:limit]

    return InflowDashboardSummary(
        productsCount=products.get("totalCount") or len(products.get("data", [])),
        customersCount=customers.get("totalCount") or len(customers.get("data", [])),
        vendorsCount=vendors.get("totalCount") or len(vendors.get("data", [])),
        salesOrdersCount=sales.get("totalCount") or len(sales.get("data", [])),
        purchaseOrdersCount=purchases.get("totalCount") or len(purchases.get("data", [])),
        recentSalesOrders=recent_sales,
        recentPurchaseOrders=recent_purchases,
    ).model_dump()
