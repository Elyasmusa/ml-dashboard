import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService } from '../../../shared/services/inflow.service';
import { InflowSalesOrder, InflowSalesOrderItem, InflowSalesOrderLine } from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-order-information',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './order-information.component.html',
  styleUrl: './order-information.component.scss',
})
export class OrderInformationComponent implements OnInit {
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

    this.fetchAllOrders(0);
  }

  private fetchAllOrders(offset: number): void {
    const pageSize = 100;

    this.inflowService.listSalesOrdersWithDetails(pageSize, offset).subscribe({
      next: (response) => {
        const newOrders = response.data || [];
        this.salesOrders = [...this.salesOrders, ...newOrders];

        // If there are more orders, fetch the next page
        if (response.hasMore && newOrders.length === pageSize) {
          this.fetchAllOrders(offset + pageSize);
        } else {
          // All orders loaded, sort them
          this.salesOrders = this.sortOrdersByNumber(this.salesOrders);
          this.loading = false;
          console.log(`Loaded ${this.salesOrders.length} total orders`);
        }
      },
      error: (err) => {
        console.error('Error loading sales orders:', err);
        this.error = `Failed to load sales orders: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
      },
    });
  }

  sortOrdersByNumber(orders: InflowSalesOrder[]): InflowSalesOrder[] {
    return [...orders].sort((a, b) => {
      const orderA = a.orderNumber || '';
      const orderB = b.orderNumber || '';
      return orderA.localeCompare(orderB, undefined, { numeric: true });
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
    // Use shipping address first, fall back to billing address
    const addr = order.shippingAddress || order.billingAddress;
    if (addr && typeof addr === 'object') {
      const parts: string[] = [];

      // Helper to safely get string value
      const safeString = (val: unknown): string => {
        if (val == null) return '';
        if (typeof val === 'string') return val.trim();
        if (typeof val === 'object') return '';
        return String(val).trim();
      };

      const address1 = safeString(addr.address1);
      const city = safeString(addr.city);
      const state = safeString(addr.state);
      const country = safeString(addr.country);

      if (address1) parts.push(address1);
      if (city) parts.push(city);
      if (state) parts.push(state);
      if (country) parts.push(country);

      if (parts.length > 0) {
        return parts.join(', ');
      }
    }

    // Fallback to location field if it's a string
    if (order.location && typeof order.location === 'string') {
      return order.location;
    }

    return '-';
  }

  getOrderItems(order: InflowSalesOrder): InflowSalesOrderItem[] {
    // First try the 'lines' array from the API (when include=lines.product is used)
    if (order.lines && order.lines.length > 0) {
      return order.lines.map((line: InflowSalesOrderLine) => ({
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
    // Fallback to 'items' array if present
    return order.items || [];
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
