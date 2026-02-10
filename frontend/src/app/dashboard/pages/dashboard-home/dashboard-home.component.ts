import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MetricCard } from '../../../shared/models/dashboard.model';
import { ModelService } from '../../../shared/services/model.service';
import { InflowService } from '../../../shared/services/inflow.service';
import { InflowDashboardSummary, InflowSalesOrder, InflowPurchaseOrder } from '../../../shared/models/inflow.model';
import { environment } from '../../../../environments/environment';
import { MetricsCardComponent } from '../../components/metrics-card/metrics-card.component';
import { ChartPlaceholderComponent } from '../../components/chart-placeholder/chart-placeholder.component';

@Component({
  selector: 'app-dashboard-home',
  standalone: true,
  imports: [CommonModule, MetricsCardComponent, ChartPlaceholderComponent],
  templateUrl: './dashboard-home.component.html',
  styleUrl: './dashboard-home.component.scss',
})
export class DashboardHomeComponent implements OnInit {
  metricCards: MetricCard[] = [
    { title: 'Models', value: '0', icon: 'model_training', color: '#3f51b5' },
    { title: 'Products', value: '0', icon: 'inventory_2', color: '#4caf50' },
    { title: 'Customers', value: '0', icon: 'people', color: '#ff9800' },
    { title: 'Sales Orders', value: '0', icon: 'receipt_long', color: '#e91e63' },
    { title: 'Purchase Orders', value: '0', icon: 'local_shipping', color: '#9c27b0' },
  ];

  recentSalesOrders: InflowSalesOrder[] = [];
  recentPurchaseOrders: InflowPurchaseOrder[] = [];
  inflowLoading = true;
  inflowError = '';

  constructor(
    private modelService: ModelService,
    private inflowService: InflowService,
  ) {}

  ngOnInit(): void {
    this.modelService.listModels().subscribe({
      next: (models) => {
        this.metricCards[0].value = String(models.length);
      },
      error: () => {
        this.metricCards[0].value = 'Error';
      },
    });

    const limit = environment.recentOrdersLimit ?? 5;
    this.inflowService.getDashboardSummary(limit).subscribe({
      next: (summary: InflowDashboardSummary) => {
        this.metricCards[1].value = String(summary.productsCount);
        this.metricCards[2].value = String(summary.customersCount);
        this.metricCards[3].value = String(summary.salesOrdersCount);
        this.metricCards[4].value = String(summary.purchaseOrdersCount);
        // Sort recent sales orders by order number (highest first). Use numeric part when available
        this.recentSalesOrders = (summary.recentSalesOrders || []).slice().sort((a, b) => {
          const na = this.orderNumberValue(a?.orderNumber);
          const nb = this.orderNumberValue(b?.orderNumber);
          if (nb !== na) return nb - na;
          const sa = (a?.orderNumber || '').toString();
          const sb = (b?.orderNumber || '').toString();
          return sb.localeCompare(sa);
        });

        // Sort recent purchase orders by date (descending) for consistency
        this.recentPurchaseOrders = (summary.recentPurchaseOrders || []).slice().sort((a, b) => {
          return this.dateToTime(b?.orderDate) - this.dateToTime(a?.orderDate);
        });

        this.inflowLoading = false;
      },
      error: (err) => {
        this.inflowError = 'Failed to load Inflow data';
        this.inflowLoading = false;
        console.error('Inflow dashboard error:', err);
      },
    });
  }

  formatDate(date?: string): string {
    if (!date) return '-';
    const d = new Date(date);
    if (isNaN(d.getTime())) return date;
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const yyyy = d.getFullYear();
    return `${mm}/${dd}/${yyyy}`;
  }

  formatCurrency(value: number | string | undefined | null): string {
    if (value == null) return '-';
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(numValue)) return '-';
    return '$' + numValue.toFixed(2);
  }

  private dateToTime(date?: string): number {
    if (!date) return 0;
    // native parse
    let t = Date.parse(date);
    if (!isNaN(t)) return t;
    // try replacing space with T (common ISO variant)
    t = Date.parse(date.replace(' ', 'T'));
    if (!isNaN(t)) return t;
    // try dd/mm/yyyy -> swap to mm/dd/yyyy if day > 12
    const m = date.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})(.*)$/);
    if (m) {
      const p1 = parseInt(m[1], 10);
      const p2 = parseInt(m[2], 10);
      const rest = m[4] || '';
      let candidate = date;
      if (p1 > 12) {
        candidate = `${m[2]}/${m[1]}/${m[3]}${rest}`;
      }
      t = Date.parse(candidate);
      if (!isNaN(t)) return t;
    }
    return 0;
  }

  private orderNumberValue(orderNumber?: string): number {
    if (!orderNumber) return 0;
    const parts = orderNumber.match(/\d+/g);
    if (!parts || parts.length === 0) return 0;
    const last = parts[parts.length - 1];
    const n = parseInt(last, 10);
    return isNaN(n) ? 0 : n;
  }
}
