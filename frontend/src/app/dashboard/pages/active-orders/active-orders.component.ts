import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { forkJoin } from 'rxjs';
import { InflowService } from '../../../shared/services/inflow.service';
import {
  InflowProduct,
  InflowSalesOrder,
  InflowSalesOrderItem,
  InflowSalesOrderLine,
  EXCLUDED_PRODUCT_NAMES,
  EXCLUDED_PRODUCT_SKUS,
} from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-active-orders',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './active-orders.component.html',
  styleUrl: './active-orders.component.scss',
})
export class ActiveOrdersComponent implements OnInit {
  orders: InflowSalesOrder[] = [];
  loading = true;
  error: string | null = null;
  expandedOrderId: string | null = null;

  private allowedProductNames = new Set<string>();
  private allowedProductSKUs = new Set<string>();

  private readonly excludedCategories = new Set([
    'inactive', 'bags', 'storage bins', 'tools', 'merchandise',
    'raw material', 'packaging', 'equipment', 'services',
    'preblends', 'pastries', 'supplies', 'warehouse supplies',
  ]);

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadOrders();
  }

  loadOrders(): void {
    this.loading = true;
    this.error = null;
    this.orders = [];
    this.allowedProductNames.clear();
    this.allowedProductSKUs.clear();

    forkJoin({
      orders: this.inflowService.listActiveOrders(),
      products: this.inflowService.listProducts(),
    }).subscribe({
      next: ({ orders, products }) => {
        this.buildAllowedSets(products.data || []);
        this.orders = (orders.data || []).filter(o =>
          (o.orderNumber || '').toUpperCase().startsWith('SO-')
        );
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading active orders:', err);
        this.error = `Failed to load active orders: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
      },
    });
  }

  private buildAllowedSets(products: InflowProduct[]): void {
    for (const p of products) {
      const name = (p.name || '').trim().toLowerCase();
      const sku = (p.sku || '').trim();
      const cat = this.getProductCategory(p).toLowerCase();

      if (this.excludedCategories.has(cat)) continue;
      if (EXCLUDED_PRODUCT_NAMES.has(name)) continue;
      if (sku && EXCLUDED_PRODUCT_SKUS.has(sku)) continue;

      let prefixExcluded = false;
      for (const sep of [' - ', ' | ']) {
        const idx = name.indexOf(sep);
        if (idx > 0 && EXCLUDED_PRODUCT_NAMES.has(name.substring(0, idx).trim())) {
          prefixExcluded = true;
          break;
        }
      }
      if (prefixExcluded) continue;

      this.allowedProductNames.add(name);
      if (sku) this.allowedProductSKUs.add(sku);
    }
  }

  private getProductCategory(p: InflowProduct): string {
    const cat = p.category;
    if (!cat) return '';
    return typeof cat === 'string' ? cat : (cat.name || '');
  }

  private isLineAllowed(name: string, sku: string): boolean {
    const nameLower = name.trim().toLowerCase();
    const skuTrimmed = sku.trim();
    if (EXCLUDED_PRODUCT_NAMES.has(nameLower)) return false;
    if (skuTrimmed && EXCLUDED_PRODUCT_SKUS.has(skuTrimmed)) return false;
    if (this.allowedProductNames.size === 0 && this.allowedProductSKUs.size === 0) return true;
    if (skuTrimmed && this.allowedProductSKUs.has(skuTrimmed)) return true;
    return this.allowedProductNames.has(nameLower);
  }

  getOrderId(order: InflowSalesOrder): string {
    return order.salesOrderId || order.id || '';
  }

  toggleExpand(order: InflowSalesOrder): void {
    const id = this.getOrderId(order);
    if (!id) return;
    this.expandedOrderId = this.expandedOrderId === id ? null : id;
  }

  isExpanded(order: InflowSalesOrder): boolean {
    const id = this.getOrderId(order);
    return id !== '' && this.expandedOrderId === id;
  }

  getOrderItems(order: InflowSalesOrder): InflowSalesOrderItem[] {
    if (order.lines && order.lines.length > 0) {
      return order.lines
        .filter((line: InflowSalesOrderLine) =>
          this.isLineAllowed(line.product?.name || '', line.product?.sku || '')
        )
        .map((line: InflowSalesOrderLine) => ({
          productId: line.productId,
          productName: line.product?.name || line.description || '-',
          sku: line.product?.sku,
          quantity: line.quantity?.uomQuantity
            ? parseFloat(line.quantity.uomQuantity)
            : line.quantity?.standardQuantity
              ? parseFloat(line.quantity.standardQuantity)
              : undefined,
          unitPrice: typeof line.unitPrice === 'string' ? parseFloat(line.unitPrice) : line.unitPrice,
          total: typeof line.subTotal === 'string' ? parseFloat(line.subTotal) : line.subTotal,
          description: line.description,
        }));
    }
    return (order.items || []).filter((item) =>
      this.isLineAllowed(item.productName || '', item.sku || '')
    );
  }

  getContactName(order: InflowSalesOrder): string {
    return (order.contactName || order.customer || '').trim() || '-';
  }

  getLocation(order: InflowSalesOrder): string {
    const addr = order.shippingAddress || order.billingAddress;
    if (addr && typeof addr === 'object') {
      const parts: string[] = [];
      const s = (v: unknown): string =>
        typeof v === 'string' ? v.trim() : '';
      if (s(addr.city)) parts.push(s(addr.city));
      if (s(addr.state)) parts.push(s(addr.state));
      if (s(addr.country)) parts.push(s(addr.country));
      if (parts.length) return parts.join(', ');
    }
    return typeof order.location === 'string' ? order.location || '-' : '-';
  }

  formatDate(dateString: string | undefined | null): string {
    if (!dateString) return '-';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  }

  formatCurrency(value: number | string | undefined | null): string {
    if (value == null) return '-';
    const n = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(n) ? '-' : '$' + n.toFixed(2);
  }

  getStatusClass(status: string | undefined): string {
    if (!status) return '';
    const s = status.toLowerCase();
    if (s.includes('complete') || s.includes('fulfilled')) return 'status-complete';
    if (s.includes('pending') || s.includes('open')) return 'status-pending';
    if (s.includes('cancel')) return 'status-cancelled';
    return '';
  }
}
