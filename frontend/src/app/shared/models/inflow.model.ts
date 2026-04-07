export interface InflowListResponse<T = Record<string, unknown>> {
  data: T[];
  hasMore: boolean;
  totalCount: number | null;
}

export interface InflowInventoryLine {
  locationId?: string;
  locationName?: string;
  quantityOnHand?: number;
  quantityCommitted?: number;
  quantityOnOrder?: number;
  quantityAvailable?: number;
  reorderPoint?: number;
}

export interface InflowDefaultPrice {
  fixedMarkup?: number;
  [key: string]: unknown;
}

export interface InflowProductVariant {
  id?: number;
  name?: string;
  variantLabel?: string;
  sku?: string;
  barcode?: string;
  quantityOnHand?: number;
  reorderPoint?: number;
  cost?: number;
  price?: number;
  defaultPrice?: InflowDefaultPrice;
  category?: string | { name?: string };
  inventoryLines?: InflowInventoryLine[];
}

export interface InflowProduct {
  id?: number;
  name?: string;
  description?: string;
  category?: string | { name?: string };
  barcode?: string;
  sku?: string;
  isActive?: boolean;
  quantityOnHand?: number;
  totalQuantityOnHand?: number;
  reorderPoint?: number;
  cost?: number;
  price?: number;
  defaultPrice?: InflowDefaultPrice;
  weight?: number;
  dimensions?: string;
  imageUrl?: string;
  customFields?: Record<string, unknown>;
  inventoryLines?: InflowInventoryLine[];
  variants?: InflowProductVariant[];
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

export interface FranchiseLocationCity {
  citySlug: string;
  displayName: string;
}

export interface FranchiseLocationOrderRow {
  orderNumber?: string;
  contactName?: string;
  orderDate?: string;
  nextOrderDate?: string | null;
  orderSize?: number | null;
  totalQty?: number;
  orderTotal?: number | null;
  products?: Record<string, number>;
}

export interface FranchiseOrderMatrixRow {
  orderNumber?: string;
  contactName?: string;
  orderDay?: number | null;
  orderMonth?: number | null;
  orderYear?: number | null;
  nextOrderDay?: number | null;
  nextOrderMonth?: number | null;
  nextOrderYear?: number | null;
  [key: string]: unknown; // loc_* and prod_* dynamic columns
}

export interface InflowDashboardSummary {
  productsCount: number;
  customersCount: number;
  vendorsCount: number;
  salesOrdersCount: number;
  purchaseOrdersCount: number;
  recentSalesOrders: any[];
  recentPurchaseOrders: any[];
}

/** Product SKUs to exclude from all product lists. */
export const EXCLUDED_PRODUCT_SKUS = new Set([
  'IF5127635',
  'IF5127634',
  'IF5127554',
  'IF5127797',
  'IF5127553',
  'IF5127552',
]);

/** Products to exclude from all product lists (matched case-insensitively). */
export const EXCLUDED_PRODUCT_NAMES = new Set([
  '1883 apple syrup',
  '1883 blackberry syrup',
  '1883 frappe mix syrup',
  '1883 peppermint syrup',
  '1883 standard mixed case',
  '4oz single walled hot cups',
  'allspice (ground)',
  'almonds',
  'almonds (fruits and nuts)',
  'almonds(fruits and nuts)',
  'barair',
  'bayad raisins',
  'chocoline pistachio sauce',
  'cold cups deactivate',
  'dark roast coffee (ground) | 5 lbs bag',
  'date syrup',
  'evaporated milk',
  'freeze dried lemons',
  'gate of yemen | dark roast (ground)',
  'gate of yemen whol',
  'ghirardelli sauce pump',
  'ghirardelli sauce rack',
  'ghirardelli white chocolate sauce',
  'cloves (ground)',
  'ground',
  'ground (labels)',
  'ground(labels)',
  'whole',
  'whole (labels)',
  'whole(labels)',
  'light roast coffee (ground) | 5 lbs bag',
  'light roast coffee (whole) | 5 lbs bag',
  'macadamia milk',
  'macadamia nut',
  'macadmia nut',
  'm3e',
  'medium roast coffee (ground) | 5 lbs bag',
  'mediuum',
  'mount haraz | medium roast (ground)',
  'monin flavoring syrup pump',
  'monin pumpkin spice syrup (bottle)',
  'old',
  'pistachio topping (6 x 900g bottles)',
  'port of aden | special blend (fine)',
  'pumpkin powder (ground)',
  'pumpkin spice mix',
  'qamaria mix',
  'queen sheeba bundle | qishr (whole)',
  'razqi raisins',
  'shipping discount',
  'squarespacediscount',
  'sunrise socotra | light roast (ground)',
  'white chocolate sauce',
  'tea',
]);
