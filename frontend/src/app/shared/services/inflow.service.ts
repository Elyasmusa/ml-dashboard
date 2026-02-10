import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
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
} from '../models/inflow.model';

@Injectable({
  providedIn: 'root',
})
export class InflowService {
  constructor(private api: ApiService) {}

  // ── Dashboard ───────────────────────────────────────────────────────

  getDashboardSummary(limit = 5): Observable<InflowDashboardSummary> {
    return this.api.get<InflowDashboardSummary>(`/inflow/dashboard-summary?limit=${limit}`);
  }

  // ── Products ────────────────────────────────────────────────────────

  listProducts(limit = 50, offset = 0): Observable<InflowListResponse<InflowProduct>> {
    return this.api.get<InflowListResponse<InflowProduct>>(
      `/inflow/products?limit=${limit}&offset=${offset}`
    );
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

  listCustomers(limit = 50, offset = 0): Observable<InflowListResponse<InflowCustomer>> {
    return this.api.get<InflowListResponse<InflowCustomer>>(
      `/inflow/customers?limit=${limit}&offset=${offset}`
    );
  }

  getCustomer(id: number): Observable<InflowCustomer> {
    return this.api.get<InflowCustomer>(`/inflow/customers/${id}`);
  }

  upsertCustomer(body: Partial<InflowCustomer>): Observable<InflowCustomer> {
    return this.api.put<InflowCustomer>('/inflow/customers', body);
  }

  // ── Vendors ─────────────────────────────────────────────────────────

  listVendors(limit = 50, offset = 0): Observable<InflowListResponse<InflowVendor>> {
    return this.api.get<InflowListResponse<InflowVendor>>(
      `/inflow/vendors?limit=${limit}&offset=${offset}`
    );
  }

  getVendor(id: number): Observable<InflowVendor> {
    return this.api.get<InflowVendor>(`/inflow/vendors/${id}`);
  }

  upsertVendor(body: Partial<InflowVendor>): Observable<InflowVendor> {
    return this.api.put<InflowVendor>('/inflow/vendors', body);
  }

  // ── Sales Orders ────────────────────────────────────────────────────

  listSalesOrders(limit = 50, offset = 0): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.api.get<InflowListResponse<InflowSalesOrder>>(
      `/inflow/sales-orders?limit=${limit}&offset=${offset}`
    );
  }

  listSalesOrdersWithDetails(limit = 50, offset = 0): Observable<InflowListResponse<InflowSalesOrder>> {
    return this.api.get<InflowListResponse<InflowSalesOrder>>(
      `/inflow/sales-orders?limit=${limit}&offset=${offset}&include=lines.product,customer,location`
    );
  }

  getSalesOrder(id: string): Observable<InflowSalesOrder> {
    return this.api.get<InflowSalesOrder>(`/inflow/sales-orders/${id}`);
  }

  upsertSalesOrder(body: Partial<InflowSalesOrder>): Observable<InflowSalesOrder> {
    return this.api.put<InflowSalesOrder>('/inflow/sales-orders', body);
  }

  // ── Purchase Orders ─────────────────────────────────────────────────

  listPurchaseOrders(
    limit = 50,
    offset = 0
  ): Observable<InflowListResponse<InflowPurchaseOrder>> {
    return this.api.get<InflowListResponse<InflowPurchaseOrder>>(
      `/inflow/purchase-orders?limit=${limit}&offset=${offset}`
    );
  }

  getPurchaseOrder(id: number): Observable<InflowPurchaseOrder> {
    return this.api.get<InflowPurchaseOrder>(`/inflow/purchase-orders/${id}`);
  }

  upsertPurchaseOrder(body: Partial<InflowPurchaseOrder>): Observable<InflowPurchaseOrder> {
    return this.api.put<InflowPurchaseOrder>('/inflow/purchase-orders', body);
  }

  // ── Locations ───────────────────────────────────────────────────────

  listLocations(limit = 50, offset = 0): Observable<InflowListResponse<InflowLocation>> {
    return this.api.get<InflowListResponse<InflowLocation>>(
      `/inflow/locations?limit=${limit}&offset=${offset}`
    );
  }

  getLocation(id: number): Observable<InflowLocation> {
    return this.api.get<InflowLocation>(`/inflow/locations/${id}`);
  }

  // ── Categories ──────────────────────────────────────────────────────

  listCategories(limit = 50, offset = 0): Observable<InflowListResponse<InflowCategory>> {
    return this.api.get<InflowListResponse<InflowCategory>>(
      `/inflow/categories?limit=${limit}&offset=${offset}`
    );
  }

  getCategory(id: number): Observable<InflowCategory> {
    return this.api.get<InflowCategory>(`/inflow/categories/${id}`);
  }

  // ── Stock Adjustments ───────────────────────────────────────────────

  listStockAdjustments(
    limit = 50,
    offset = 0
  ): Observable<InflowListResponse<InflowStockAdjustment>> {
    return this.api.get<InflowListResponse<InflowStockAdjustment>>(
      `/inflow/stock-adjustments?limit=${limit}&offset=${offset}`
    );
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

  listStockTransfers(
    limit = 50,
    offset = 0
  ): Observable<InflowListResponse<InflowStockTransfer>> {
    return this.api.get<InflowListResponse<InflowStockTransfer>>(
      `/inflow/stock-transfers?limit=${limit}&offset=${offset}`
    );
  }

  getStockTransfer(id: number): Observable<InflowStockTransfer> {
    return this.api.get<InflowStockTransfer>(`/inflow/stock-transfers/${id}`);
  }

  upsertStockTransfer(body: Partial<InflowStockTransfer>): Observable<InflowStockTransfer> {
    return this.api.put<InflowStockTransfer>('/inflow/stock-transfers', body);
  }

  // ── Stock Counts ────────────────────────────────────────────────────

  listStockCounts(limit = 50, offset = 0): Observable<InflowListResponse<InflowStockCount>> {
    return this.api.get<InflowListResponse<InflowStockCount>>(
      `/inflow/stock-counts?limit=${limit}&offset=${offset}`
    );
  }

  getStockCount(id: number): Observable<InflowStockCount> {
    return this.api.get<InflowStockCount>(`/inflow/stock-counts/${id}`);
  }

  upsertStockCount(body: Partial<InflowStockCount>): Observable<InflowStockCount> {
    return this.api.put<InflowStockCount>('/inflow/stock-counts', body);
  }

  // ── Manufacturing Orders ────────────────────────────────────────────

  listManufacturingOrders(
    limit = 50,
    offset = 0
  ): Observable<InflowListResponse<InflowManufacturingOrder>> {
    return this.api.get<InflowListResponse<InflowManufacturingOrder>>(
      `/inflow/manufacturing-orders?limit=${limit}&offset=${offset}`
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
}
