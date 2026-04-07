import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { shareReplay, tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import {
  InflowListResponse,
  InflowProduct,
  InflowCustomer,
  InflowVendor,
  InflowSalesOrder,
  InflowPurchaseOrder,
  InflowLocation,
  InflowCategory,
  InflowStockAdjustment,
  InflowStockTransfer,
  InflowStockCount,
  InflowManufacturingOrder,
  InflowDashboardSummary,
  FranchiseLocationCity,
  FranchiseLocationOrderRow,
  FranchiseOrderMatrixRow,
} from '../models/inflow.model';

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

export interface RoastRow {
  sku: string;
  name: string;
  stock: number;
}

export const ROAST_SKUS: Record<string, string> = {
  IF5127699: 'Light Roast',
  IF5127705: 'Medium Roast',
  IF5127683: 'Dark Roast',
};

interface CacheEntry<T> {
  observable: Observable<T>;
  expiry: number;
}

@Injectable({
  providedIn: 'root',
})
export class InflowService {
  private cache = new Map<string, CacheEntry<unknown>>();

  /** Populated by ProductInventoryComponent during its filter step. */
  readonly roastRows$ = new BehaviorSubject<RoastRow[]>([]);

  setRoastRows(rows: RoastRow[]): void {
    this.roastRows$.next(rows);
  }

  constructor(private api: ApiService) {}

  /**
   * Returns a cached observable for the given key. If no valid cache entry
   * exists, calls `factory` to create a new request, pipes it through
   * `shareReplay(1)`, and stores it with a TTL.
   */
  private cached<T>(key: string, factory: () => Observable<T>): Observable<T> {
    const entry = this.cache.get(key) as CacheEntry<T> | undefined;
    if (entry) {
      if (Date.now() < entry.expiry) {
        return entry.observable;
      }
      this.cache.delete(key);
    }
    const obs = factory().pipe(shareReplay(1));
    this.cache.set(key, { observable: obs, expiry: Date.now() + CACHE_TTL_MS });
    return obs;
  }

  /** Clear all cached data, or a single key. */
  clearCache(key?: string): void {
    if (key) {
      this.cache.delete(key);
    } else {
      this.cache.clear();
    }
  }

  // ── Incremental Update ──────────────────────────────────────────────

  /** Trigger an on-demand incremental update on the backend.
   *  Fetches only records modified after the last cached data point. */
  updateData(): Observable<{ updated: Record<string, number>; totalNewRecords: number }> {
    return this.api.get<{ updated: Record<string, number>; totalNewRecords: number }>(
      '/inflow/update'
    );
  }

  // ── Dashboard ───────────────────────────────────────────────────────

  getDashboardSummary(): Observable<InflowDashboardSummary> {
    return this.cached('dashboard-summary', () =>
      this.api.get<InflowDashboardSummary>('/inflow/dashboard-summary')
    );
  }

  // ── Products ────────────────────────────────────────────────────────

  listProducts(): Observable<InflowListResponse<InflowProduct>> {
    return this.cached('products', () =>
      this.api.get<InflowListResponse<InflowProduct>>('/inflow/products?include=inventoryLines,category,defaultPrice').pipe(
        tap(res => this._buildRoastRows(res.data || []))
      )
    );
  }

  private _buildRoastRows(products: InflowProduct[]): void {
    const rows: RoastRow[] = Object.entries(ROAST_SKUS).map(([sku, name]) => {
      const nameLower = name.toLowerCase();
      const p =
        products.find(x => (x.sku || '').trim() === sku) ??
        products.find(x => (x.name || '').toLowerCase() === nameLower);
      const stock = p ? this._computeQty(p) : 0;
      console.log(`[RoastStock] ${name}: matched=${!!p}, sku=${p?.sku}, qty=${p?.quantityOnHand}, lines=${JSON.stringify(p?.inventoryLines)}, stock=${stock}`);
      return { sku, name, stock };
    });
    this.roastRows$.next(rows);
  }

  private _computeQty(p: InflowProduct): number {
    const lines = p.inventoryLines;
    if (lines && lines.length > 0) {
      const total = lines.reduce((sum, l) => sum + (Number(l.quantityOnHand) || 0), 0);
      if (total > 0) return Math.round(total);
    }
    return Math.round(Number(p.quantityOnHand) || Number(p.totalQuantityOnHand) || 0);
  }

  getRoastStock(): Observable<{ data: { sku: string; name: string; stock: number }[] }> {
    return this.api.get('/inflow/roast-stock');
  }

  getProduct(id: number): Observable<InflowProduct> {
    return this.api.get<InflowProduct>(`/inflow/products/${id}`);
  }

  upsertProduct(body: Partial<InflowProduct>): Observable<InflowProduct> {
    return this.api.put<InflowProduct>('/inflow/products', body);
  }

  getProductSummary(body: Record<string, unknown>): Observable<unknown> {
    return this.api.post<unknown>('/inflow/products/summary', body);
  }

  // ── Customers ───────────────────────────────────────────────────────

  listCustomers(): Observable<InflowListResponse<InflowCustomer>> {
    return this.api.get<InflowListResponse<InflowCustomer>>('/inflow/customers');
  }

  getCustomer(id: number): Observable<InflowCustomer> {
    return this.api.get<InflowCustomer>(`/inflow/customers/${id}`);
  }

  upsertCustomer(body: Partial<InflowCustomer>): Observable<InflowCustomer> {
    return this.api.put<InflowCustomer>('/inflow/customers', body);
  }

  // ── Vendors ─────────────────────────────────────────────────────────

  listVendors(): Observable<InflowListResponse<InflowVendor>> {
    return this.api.get<InflowListResponse<InflowVendor>>('/inflow/vendors');
  }

  getVendor(id: number): Observable<InflowVendor> {
    return this.api.get<InflowVendor>(`/inflow/vendors/${id}`);
  }

  upsertVendor(body: Partial<InflowVendor>): Observable<InflowVendor> {
    return this.api.put<InflowVendor>('/inflow/vendors', body);
  }

  // ── Sales Orders ────────────────────────────────────────────────────

  listSalesOrders(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.api.get<InflowListResponse<InflowSalesOrder>>('/inflow/sales-orders');
  }

  listSalesOrdersWithDetails(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.cached('sales-orders-details', () =>
      this.api.get<InflowListResponse<InflowSalesOrder>>(
        '/inflow/sales-orders?include=lines.product,customer,location'
      )
    );
  }

  getSalesOrder(id: string): Observable<InflowSalesOrder> {
    return this.api.get<InflowSalesOrder>(`/inflow/sales-orders/${id}`);
  }

  upsertSalesOrder(body: Partial<InflowSalesOrder>): Observable<InflowSalesOrder> {
    return this.api.put<InflowSalesOrder>('/inflow/sales-orders', body);
  }

  // ── Purchase Orders ─────────────────────────────────────────────────

  listPurchaseOrders(): Observable<InflowListResponse<InflowPurchaseOrder>> {
    return this.api.get<InflowListResponse<InflowPurchaseOrder>>('/inflow/purchase-orders');
  }

  getPurchaseOrder(id: number): Observable<InflowPurchaseOrder> {
    return this.api.get<InflowPurchaseOrder>(`/inflow/purchase-orders/${id}`);
  }

  upsertPurchaseOrder(body: Partial<InflowPurchaseOrder>): Observable<InflowPurchaseOrder> {
    return this.api.put<InflowPurchaseOrder>('/inflow/purchase-orders', body);
  }

  // ── Locations ───────────────────────────────────────────────────────

  listLocations(): Observable<InflowListResponse<InflowLocation>> {
    return this.api.get<InflowListResponse<InflowLocation>>('/inflow/locations');
  }

  getLocation(id: number): Observable<InflowLocation> {
    return this.api.get<InflowLocation>(`/inflow/locations/${id}`);
  }

  // ── Categories ──────────────────────────────────────────────────────

  listCategories(): Observable<InflowListResponse<InflowCategory>> {
    return this.api.get<InflowListResponse<InflowCategory>>('/inflow/categories');
  }

  getCategory(id: number): Observable<InflowCategory> {
    return this.api.get<InflowCategory>(`/inflow/categories/${id}`);
  }

  // ── Stock Adjustments ───────────────────────────────────────────────

  listStockAdjustments(): Observable<InflowListResponse<InflowStockAdjustment>> {
    return this.api.get<InflowListResponse<InflowStockAdjustment>>('/inflow/stock-adjustments');
  }

  getStockAdjustment(id: number): Observable<InflowStockAdjustment> {
    return this.api.get<InflowStockAdjustment>(`/inflow/stock-adjustments/${id}`);
  }

  upsertStockAdjustment(
    body: Partial<InflowStockAdjustment>
  ): Observable<InflowStockAdjustment> {
    return this.api.put<InflowStockAdjustment>('/inflow/stock-adjustments', body);
  }

  // ── Stock Transfers ─────────────────────────────────────────────────

  listStockTransfers(): Observable<InflowListResponse<InflowStockTransfer>> {
    return this.api.get<InflowListResponse<InflowStockTransfer>>('/inflow/stock-transfers');
  }

  getStockTransfer(id: number): Observable<InflowStockTransfer> {
    return this.api.get<InflowStockTransfer>(`/inflow/stock-transfers/${id}`);
  }

  upsertStockTransfer(body: Partial<InflowStockTransfer>): Observable<InflowStockTransfer> {
    return this.api.put<InflowStockTransfer>('/inflow/stock-transfers', body);
  }

  // ── Stock Counts ────────────────────────────────────────────────────

  listStockCounts(): Observable<InflowListResponse<InflowStockCount>> {
    return this.api.get<InflowListResponse<InflowStockCount>>('/inflow/stock-counts');
  }

  getStockCount(id: number): Observable<InflowStockCount> {
    return this.api.get<InflowStockCount>(`/inflow/stock-counts/${id}`);
  }

  upsertStockCount(body: Partial<InflowStockCount>): Observable<InflowStockCount> {
    return this.api.put<InflowStockCount>('/inflow/stock-counts', body);
  }

  // ── Manufacturing Orders ────────────────────────────────────────────

  listManufacturingOrders(): Observable<InflowListResponse<InflowManufacturingOrder>> {
    return this.api.get<InflowListResponse<InflowManufacturingOrder>>(
      '/inflow/manufacturing-orders'
    );
  }

  getManufacturingOrder(id: number): Observable<InflowManufacturingOrder> {
    return this.api.get<InflowManufacturingOrder>(`/inflow/manufacturing-orders/${id}`);
  }

  upsertManufacturingOrder(
    body: Partial<InflowManufacturingOrder>
  ): Observable<InflowManufacturingOrder> {
    return this.api.put<InflowManufacturingOrder>('/inflow/manufacturing-orders', body);
  }

  // ── Reference data ──────────────────────────────────────────────────

  listCurrencies(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/currencies');
  }

  listTaxCodes(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/tax-codes');
  }

  listPaymentTerms(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/payment-terms');
  }

  listPricingSchemes(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/pricing-schemes');
  }

  listAdjustmentReasons(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/adjustment-reasons');
  }

  listOperationTypes(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/operation-types');
  }

  // ── Team / Stockroom Users ──────────────────────────────────────────

  listTeamMembers(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/team-members');
  }

  listStockroomUsers(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/stockroom-users');
  }

  // ── Webhooks ────────────────────────────────────────────────────────

  listWebhooks(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/webhooks');
  }

  upsertWebhook(body: Record<string, unknown>): Observable<unknown> {
    return this.api.put<unknown>('/inflow/webhooks', body);
  }

  deleteWebhook(id: number): Observable<unknown> {
    return this.api.delete<unknown>(`/inflow/webhooks/${id}`);
  }

  // ── Custom Fields ───────────────────────────────────────────────────

  listCustomFields(): Observable<InflowListResponse> {
    return this.api.get<InflowListResponse>('/inflow/custom-fields');
  }

  // ── Derived Order Frames ──────────────────────────────────────────

  listNaFranchiseOrders(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.cached('na-franchise-orders', () =>
      this.api.get<InflowListResponse<InflowSalesOrder>>('/inflow/na-franchise-orders')
    );
  }

  listFranchiseStoreOrders(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.cached('franchise-store-orders', () =>
      this.api.get<InflowListResponse<InflowSalesOrder>>('/inflow/franchise-store-orders')
    );
  }

  listOnlineOrders(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.cached('online-orders', () =>
      this.api.get<InflowListResponse<InflowSalesOrder>>('/inflow/online-orders')
    );
  }

  // ── Franchise Location Frames ────────────────────────────────────

  listFranchiseLocationCities(): Observable<InflowListResponse<FranchiseLocationCity>> {
    return this.cached('franchise-location-cities', () =>
      this.api.get<InflowListResponse<FranchiseLocationCity>>(
        '/inflow/franchise-location-orders/cities'
      )
    );
  }

  getFranchiseLocationOrders(citySlug: string): Observable<InflowListResponse<FranchiseLocationOrderRow>> {
    return this.cached(`franchise-location-orders:${citySlug}`, () =>
      this.api.get<InflowListResponse<FranchiseLocationOrderRow>>(
        `/inflow/franchise-location-orders/${citySlug}`
      )
    );
  }

  // ── Franchise Order Matrix ─────────────────────────────────────

  listFranchiseOrderMatrix(): Observable<InflowListResponse<FranchiseOrderMatrixRow>> {
    return this.cached('franchise-order-matrix', () =>
      this.api.get<InflowListResponse<FranchiseOrderMatrixRow>>('/inflow/franchise-order-matrix')
    );
  }

  // ── Latest Franchise Orders ──────────────────────────────────

  listLatestFranchiseOrders(): Observable<InflowListResponse<FranchiseOrderMatrixRow>> {
    return this.cached('latest-franchise-orders', () =>
      this.api.get<InflowListResponse<FranchiseOrderMatrixRow>>('/inflow/latest-franchise-orders')
    );
  }

  // ── Franchise Product Matrix ─────────────────────────────────

  listFranchiseProductMatrix(): Observable<InflowListResponse<FranchiseOrderMatrixRow>> {
    return this.cached('franchise-product-matrix', () =>
      this.api.get<InflowListResponse<FranchiseOrderMatrixRow>>('/inflow/franchise-product-matrix')
    );
  }

  // ── Latest Franchise Product Orders ──────────────────────────

  listLatestFranchiseProductOrders(): Observable<InflowListResponse<FranchiseOrderMatrixRow>> {
    return this.cached('latest-franchise-product-orders', () =>
      this.api.get<InflowListResponse<FranchiseOrderMatrixRow>>('/inflow/latest-franchise-product-orders')
    );
  }

  // ── Active Orders This Week ───────────────────────────────────

  /** This week's (Sat–Fri) sales orders that have not yet been completed.
   *  Not cached — fetched fresh on each call so fulfillment status stays current. */
  listActiveOrdersWeek(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.api.get<InflowListResponse<InflowSalesOrder>>('/inflow/active-orders-week');
  }

  /** All active (non-completed, non-terminal) sales orders.
   *  Not cached — fetched fresh on each call so fulfillment status stays current. */
  listActiveOrders(): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.api.get<InflowListResponse<InflowSalesOrder>>('/inflow/active-orders');
  }
}
