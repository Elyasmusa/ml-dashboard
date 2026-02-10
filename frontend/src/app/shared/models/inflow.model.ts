export interface InflowListResponse<T = Record<string, unknown>> {
  data: T[];
  hasMore: boolean;
  totalCount: number | null;
}

export interface InflowProduct {
  id?: number;
  name?: string;
  description?: string;
  category?: string;
  barcode?: string;
  sku?: string;
  isActive?: boolean;
  quantityOnHand?: number;
  reorderPoint?: number;
  cost?: number;
  price?: number;
  weight?: number;
  dimensions?: string;
  imageUrl?: string;
  customFields?: Record<string, unknown>;
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowProductSummary {
  productId?: number;
  productName?: string;
  quantityOnHand?: number;
  quantityOnOrder?: number;
  quantityCommitted?: number;
  quantityAvailable?: number;
  locations?: Record<string, unknown>[];
}

export interface InflowCustomer {
  id?: number;
  name?: string;
  email?: string;
  phone?: string;
  company?: string;
  address?: Record<string, unknown>;
  taxingScheme?: string;
  pricingScheme?: string;
  paymentTerms?: string;
  currency?: string;
  isActive?: boolean;
  customFields?: Record<string, unknown>;
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowVendor {
  id?: number;
  name?: string;
  email?: string;
  phone?: string;
  company?: string;
  address?: Record<string, unknown>;
  taxingScheme?: string;
  paymentTerms?: string;
  currency?: string;
  isActive?: boolean;
  customFields?: Record<string, unknown>;
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowAddress {
  address1?: string;
  address2?: string;
  city?: string;
  state?: string;
  country?: string;
  postalCode?: string;
  remarks?: string;
  addressType?: string | null;
}

export interface InflowSalesOrderLineProduct {
  productId?: string;
  name?: string;
  sku?: string;
  description?: string;
}

export interface InflowSalesOrderLine {
  salesOrderLineId?: string;
  productId?: string;
  product?: InflowSalesOrderLineProduct;
  quantity?: {
    standardQuantity?: string;
    uomQuantity?: string;
    uom?: string;
  };
  unitPrice?: string | number;
  subTotal?: string | number;
  description?: string;
}

export interface InflowSalesOrderItem {
  productId?: string;
  productName?: string;
  quantity?: number;
  unitPrice?: number;
  total?: number;
  sku?: string;
  description?: string;
}

export interface InflowSalesOrder {
  // API uses salesOrderId, but we also support id for backwards compatibility
  id?: string;
  salesOrderId?: string;
  orderNumber?: string;
  customer?: string;
  customerId?: string;
  contactName?: string;
  status?: string;
  inventoryStatus?: string;
  paymentStatus?: string;
  isCompleted?: boolean;
  orderDate?: string;
  requiredDate?: string;
  completedDate?: string;
  invoicedDate?: string;
  shippedDate?: string;
  location?: string;
  locationId?: string;
  billingAddress?: InflowAddress;
  shippingAddress?: InflowAddress;
  subTotal?: number | string;
  taxTotal?: number | string;
  total?: number | string;
  remarks?: string;
  orderRemarks?: string;
  items?: InflowSalesOrderItem[];
  lines?: InflowSalesOrderLine[];
  customFields?: Record<string, unknown>;
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowPurchaseOrder {
  id?: number;
  orderNumber?: string;
  vendor?: string;
  status?: string;
  orderDate?: string;
  expectedDate?: string;
  location?: string;
  subTotal?: number;
  taxTotal?: number;
  total?: number;
  remarks?: string;
  items?: Record<string, unknown>[];
  customFields?: Record<string, unknown>;
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowLocation {
  id?: number;
  name?: string;
  description?: string;
  address?: Record<string, unknown>;
  isActive?: boolean;
}

export interface InflowCategory {
  id?: number;
  name?: string;
  parentId?: number;
  parentName?: string;
}

export interface InflowStockAdjustment {
  id?: number;
  adjustmentNumber?: string;
  date?: string;
  location?: string;
  reason?: string;
  remarks?: string;
  items?: Record<string, unknown>[];
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowStockTransfer {
  id?: number;
  transferNumber?: string;
  date?: string;
  fromLocation?: string;
  toLocation?: string;
  status?: string;
  remarks?: string;
  items?: Record<string, unknown>[];
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowStockCount {
  id?: number;
  countNumber?: string;
  date?: string;
  location?: string;
  status?: string;
  remarks?: string;
  items?: Record<string, unknown>[];
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowManufacturingOrder {
  id?: number;
  orderNumber?: string;
  product?: string;
  quantity?: number;
  status?: string;
  date?: string;
  location?: string;
  remarks?: string;
  items?: Record<string, unknown>[];
  modifiedDate?: string;
  createdDate?: string;
}

export interface InflowCurrency {
  code?: string;
  name?: string;
  symbol?: string;
  exchangeRate?: number;
}

export interface InflowTaxCode {
  id?: number;
  name?: string;
  rate?: number;
}

export interface InflowPaymentTerms {
  id?: number;
  name?: string;
  dueDays?: number;
}

export interface InflowPricingScheme {
  id?: number;
  name?: string;
  type?: string;
}

export interface InflowWebhook {
  id?: number;
  url?: string;
  event?: string;
  isActive?: boolean;
  secret?: string;
}

export interface InflowDashboardSummary {
  productsCount: number;
  customersCount: number;
  vendorsCount: number;
  salesOrdersCount: number;
  purchaseOrdersCount: number;
  recentSalesOrders: InflowSalesOrder[];
  recentPurchaseOrders: InflowPurchaseOrder[];
}
