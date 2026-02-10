from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Body

from services.inflow_client import InflowClientError
from services import inflow_service

router = APIRouter(prefix="/inflow", tags=["inflow"])


def _handle_inflow_error(exc: InflowClientError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


# ── Dashboard ────────────────────────────────────────────────────────

@router.get("/dashboard-summary")
async def dashboard_summary(limit: int = Query(5)):
    try:
        return await inflow_service.get_dashboard_summary(limit=limit)
    except InflowClientError as exc:
        _handle_inflow_error(exc)


# ── Products ─────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_products({"limit": str(limit), "offset": str(offset)})
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
async def list_customers(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_customers({"limit": str(limit), "offset": str(offset)})
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
async def list_vendors(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_vendors({"limit": str(limit), "offset": str(offset)})
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
async def list_sales_orders(
    limit: int = Query(50),
    offset: int = Query(0),
    include: str | None = Query(None),
):
    try:
        params = {"limit": str(limit), "offset": str(offset)}
        if include:
            params["include"] = include
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
async def list_purchase_orders(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_purchase_orders({"limit": str(limit), "offset": str(offset)})
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
async def list_locations(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_locations({"limit": str(limit), "offset": str(offset)})
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
async def list_categories(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_categories({"limit": str(limit), "offset": str(offset)})
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
async def list_stock_adjustments(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_stock_adjustments({"limit": str(limit), "offset": str(offset)})
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
async def list_stock_transfers(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_stock_transfers({"limit": str(limit), "offset": str(offset)})
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
async def list_stock_counts(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_stock_counts({"limit": str(limit), "offset": str(offset)})
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
async def list_manufacturing_orders(limit: int = Query(50), offset: int = Query(0)):
    try:
        return await inflow_service.list_manufacturing_orders({"limit": str(limit), "offset": str(offset)})
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
