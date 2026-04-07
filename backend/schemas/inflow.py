from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import Any


# ── Generic list wrapper ──────────────────────────────────────────────

class InflowListResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    data: list[dict[str, Any]] = []
    hasMore: bool = False
    totalCount: int | None = None


# ── Products ──────────────────────────────────────────────────────────

class InflowProduct(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    barcode: str | None = None
    sku: str | None = None
    isActive: bool | None = None
    quantityOnHand: float | None = None
    reorderPoint: float | None = None
    cost: float | None = None
    price: float | None = None
    weight: float | None = None
    dimensions: str | None = None
    imageUrl: str | None = None
    customFields: dict[str, Any] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


class InflowProductSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    productId: int | None = None
    productName: str | None = None
    quantityOnHand: float | None = None
    quantityOnOrder: float | None = None
    quantityCommitted: float | None = None
    quantityAvailable: float | None = None
    locations: list[dict[str, Any]] | None = None


# ── Customers ─────────────────────────────────────────────────────────

class InflowCustomer(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    address: dict[str, Any] | None = None
    taxingScheme: str | None = None
    pricingScheme: str | None = None
    paymentTerms: str | None = None
    currency: str | None = None
    isActive: bool | None = None
    customFields: dict[str, Any] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Vendors ───────────────────────────────────────────────────────────

class InflowVendor(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    address: dict[str, Any] | None = None
    taxingScheme: str | None = None
    paymentTerms: str | None = None
    currency: str | None = None
    isActive: bool | None = None
    customFields: dict[str, Any] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Sales Orders ──────────────────────────────────────────────────────

class InflowSalesOrderItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    productId: str | None = None
    productName: str | None = None
    quantity: float | None = None
    unitPrice: float | None = None
    total: float | None = None
    sku: str | None = None
    description: str | None = None


class InflowSalesOrder(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str | None = None
    orderNumber: str | None = None
    customer: str | None = None
    contactName: str | None = None
    status: str | None = None
    inventoryStatus: str | None = None
    orderDate: str | None = None
    requiredDate: str | None = None
    completedDate: str | None = None
    invoicedDate: str | None = None
    location: str | None = None
    subTotal: float | None = None
    taxTotal: float | None = None
    total: float | None = None
    remarks: str | None = None
    items: list[InflowSalesOrderItem] | None = None
    customFields: dict[str, Any] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Purchase Orders ───────────────────────────────────────────────────

class InflowPurchaseOrder(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    orderNumber: str | None = None
    vendor: str | None = None
    status: str | None = None
    orderDate: str | None = None
    expectedDate: str | None = None
    location: str | None = None
    subTotal: float | None = None
    taxTotal: float | None = None
    total: float | None = None
    remarks: str | None = None
    items: list[dict[str, Any]] | None = None
    customFields: dict[str, Any] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Locations ─────────────────────────────────────────────────────────

class InflowLocation(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    description: str | None = None
    address: dict[str, Any] | None = None
    isActive: bool | None = None


# ── Categories ────────────────────────────────────────────────────────

class InflowCategory(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    parentId: int | None = None
    parentName: str | None = None


# ── Stock Adjustments ─────────────────────────────────────────────────

class InflowStockAdjustment(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    adjustmentNumber: str | None = None
    date: str | None = None
    location: str | None = None
    reason: str | None = None
    remarks: str | None = None
    items: list[dict[str, Any]] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Stock Transfers ───────────────────────────────────────────────────

class InflowStockTransfer(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    transferNumber: str | None = None
    date: str | None = None
    fromLocation: str | None = None
    toLocation: str | None = None
    status: str | None = None
    remarks: str | None = None
    items: list[dict[str, Any]] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Stock Counts ──────────────────────────────────────────────────────

class InflowStockCount(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    countNumber: str | None = None
    date: str | None = None
    location: str | None = None
    status: str | None = None
    remarks: str | None = None
    items: list[dict[str, Any]] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Manufacturing Orders ─────────────────────────────────────────────

class InflowManufacturingOrder(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    orderNumber: str | None = None
    product: str | None = None
    quantity: float | None = None
    status: str | None = None
    date: str | None = None
    location: str | None = None
    remarks: str | None = None
    items: list[dict[str, Any]] | None = None
    modifiedDate: str | None = None
    createdDate: str | None = None


# ── Reference data ────────────────────────────────────────────────────

class InflowCurrency(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    code: str | None = None
    name: str | None = None
    symbol: str | None = None
    exchangeRate: float | None = None


class InflowTaxCode(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    rate: float | None = None


class InflowTaxingScheme(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    taxCodes: list[dict[str, Any]] | None = None


class InflowPaymentTerms(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    dueDays: int | None = None


class InflowPricingScheme(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    type: str | None = None


class InflowAdjustmentReason(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None


class InflowOperationType(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None


# ── Team / Stockroom Users ───────────────────────────────────────────

class InflowTeamMember(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    email: str | None = None
    role: str | None = None


class InflowStockroomUser(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    name: str | None = None
    email: str | None = None


# ── Webhooks ──────────────────────────────────────────────────────────

class InflowWebhook(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int | None = None
    url: str | None = None
    event: str | None = None
    isActive: bool | None = None
    secret: str | None = None


# ── Dashboard aggregate ──────────────────────────────────────────────

class InflowDashboardSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    productsCount: int = 0
    customersCount: int = 0
    vendorsCount: int = 0
    salesOrdersCount: int = 0
    purchaseOrdersCount: int = 0
    recentSalesOrders: list[dict[str, Any]] = []
    recentPurchaseOrders: list[dict[str, Any]] = []
