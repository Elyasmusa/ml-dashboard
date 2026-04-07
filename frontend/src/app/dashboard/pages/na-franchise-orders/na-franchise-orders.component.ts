import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService } from '../../../shared/services/inflow.service';
import { InflowSalesOrder, InflowSalesOrderItem, InflowSalesOrderLine, EXCLUDED_PRODUCT_NAMES, EXCLUDED_PRODUCT_SKUS } from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-na-franchise-orders',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './na-franchise-orders.component.html',
  styleUrl: './na-franchise-orders.component.scss',
})
export class NaFranchiseOrdersComponent implements OnInit {
  salesOrders: InflowSalesOrder[] = [];
  loading = true;
  error: string | null = null;
  expandedOrderId: string | null = null;

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadOrders();
  }

  loadOrders(): void {
    this.loading = true;
    this.error = null;
    this.salesOrders = [];

    this.inflowService.listNaFranchiseOrders().subscribe({
      next: (response) => {
        this.salesOrders = this.sortOrdersByDate(response.data || []);
        this.loading = false;
        console.log(`Loaded ${this.salesOrders.length} North America franchise orders`);
      },
      error: (err) => {
        console.error('Error loading NA franchise orders:', err);
        this.error = `Failed to load North America franchise orders: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
      },
    });
  }

  sortOrdersByDate(orders: InflowSalesOrder[]): InflowSalesOrder[] {
    return [...orders].sort((a, b) => {
      const dateA = a.orderDate ? new Date(a.orderDate).getTime() : 0;
      const dateB = b.orderDate ? new Date(b.orderDate).getTime() : 0;
      return dateB - dateA;
    });
  }

  getOrderId(order: InflowSalesOrder): string {
    return order.salesOrderId || order.id || '';
  }

  toggleOrderExpand(order: InflowSalesOrder): void {
    const orderId = this.getOrderId(order);
    if (!orderId) return;
    this.expandedOrderId = this.expandedOrderId === orderId ? null : orderId;
  }

  isExpanded(order: InflowSalesOrder): boolean {
    const orderId = this.getOrderId(order);
    return orderId !== '' && this.expandedOrderId === orderId;
  }

  formatDate(dateString: string | undefined | null): string {
    if (!dateString) return '-';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
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
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(numValue)) return '-';
    return '$' + numValue.toFixed(2);
  }

  getLocation(order: InflowSalesOrder): string {
    const addr = order.shippingAddress || order.billingAddress;
    if (addr && typeof addr === 'object') {
      const parts: string[] = [];

      const safeString = (val: unknown): string => {
        if (val == null) return '';
        if (typeof val === 'string') return val.trim();
        if (typeof val === 'object') return '';
        return String(val).trim();
      };

      const city = safeString(addr.city);
      const state = safeString(addr.state);
      const country = safeString(addr.country);

      if (city) parts.push(city);
      if (state) parts.push(state);
      if (country) parts.push(country);

      if (parts.length > 0) {
        return parts.join(', ');
      }
    }

    if (order.location && typeof order.location === 'string') {
      return order.location;
    }

    return '-';
  }

  getOrderItems(order: InflowSalesOrder): InflowSalesOrderItem[] {
    if (order.lines && order.lines.length > 0) {
      return order.lines
        .filter((line: InflowSalesOrderLine) =>
          !EXCLUDED_PRODUCT_NAMES.has((line.product?.name || '').trim().toLowerCase()) &&
          !EXCLUDED_PRODUCT_SKUS.has((line.product?.sku || '').trim())
        )
        .map((line: InflowSalesOrderLine) => ({
          productId: line.productId,
          productName: line.product?.name || line.description || '-',
          sku: line.product?.sku,
          quantity: line.quantity?.uomQuantity
            ? parseFloat(line.quantity.uomQuantity)
            : (line.quantity?.standardQuantity ? parseFloat(line.quantity.standardQuantity) : undefined),
          unitPrice: typeof line.unitPrice === 'string' ? parseFloat(line.unitPrice) : line.unitPrice,
          total: typeof line.subTotal === 'string' ? parseFloat(line.subTotal) : line.subTotal,
          description: line.description,
        }));
    }
    return (order.items || []).filter(
      (item) => !EXCLUDED_PRODUCT_NAMES.has((item.productName || '').trim().toLowerCase())
    );
  }

  getContactName(order: InflowSalesOrder): string {
    const name = order.contactName || order.customer;
    if (name && typeof name === 'string') {
      return name.trim() || '-';
    }
    return '-';
  }

  getCompletedDate(order: InflowSalesOrder): string {
    return this.formatDate(order.completedDate || order.invoicedDate);
  }

  getStatusClass(status: string | undefined): string {
    if (!status) return '';
    const lowerStatus = status.toLowerCase();
    if (lowerStatus.includes('complete') || lowerStatus.includes('fulfilled')) {
      return 'status-complete';
    }
    if (lowerStatus.includes('pending') || lowerStatus.includes('open')) {
      return 'status-pending';
    }
    if (lowerStatus.includes('cancel')) {
      return 'status-cancelled';
    }
    return '';
  }
}
