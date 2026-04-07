import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService } from '../../../shared/services/inflow.service';
import { FranchiseOrderMatrixRow } from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-latest-franchise-orders',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './latest-franchise-orders.component.html',
  styleUrl: './latest-franchise-orders.component.scss',
})
export class LatestFranchiseOrdersComponent implements OnInit {
  rows: FranchiseOrderMatrixRow[] = [];
  loading = true;
  error: string | null = null;

  locColumns: string[] = [];
  prodColumns: string[] = [];

  readonly fixedColumns = [
    'orderNumber', 'contactName',
    'orderDay', 'orderMonth', 'orderYear',
  ];

  readonly fixedHeaders: Record<string, string> = {
    orderNumber: 'Order #',
    contactName: 'Contact',
    orderDay: 'Day',
    orderMonth: 'Month',
    orderYear: 'Year',
  };

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    this.inflowService.listLatestFranchiseOrders().subscribe({
      next: (response) => {
        this.rows = response.data || [];
        this.extractDynamicColumns();
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading latest franchise orders:', err);
        this.error = `Failed to load latest franchise orders: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
      },
    });
  }

  private extractDynamicColumns(): void {
    const locSet = new Set<string>();
    const prodSet = new Set<string>();

    for (const row of this.rows) {
      for (const key of Object.keys(row)) {
        if (key.startsWith('loc_')) locSet.add(key);
        else if (key.startsWith('prod_')) prodSet.add(key);
      }
    }

    this.locColumns = Array.from(locSet).sort();
    this.prodColumns = Array.from(prodSet).sort();
  }

  formatColumnHeader(col: string): string {
    let name = col;
    if (name.startsWith('loc_')) name = name.substring(4);
    else if (name.startsWith('prod_')) name = name.substring(5);
    return name
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  getCellValue(row: FranchiseOrderMatrixRow, col: string): string {
    const val = row[col];
    if (val == null) return '-';
    return String(val);
  }
}
