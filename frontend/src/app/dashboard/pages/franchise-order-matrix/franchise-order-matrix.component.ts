import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService } from '../../../shared/services/inflow.service';
import { FranchiseOrderMatrixRow } from '../../../shared/models/inflow.model';
import { MATRIX_PRODUCTS, prodCol } from '../../../shared/constants/products';

/** Slug → display name map built from the shared product list. */
const PROD_DISPLAY: Record<string, string> = Object.fromEntries(
  MATRIX_PRODUCTS.map(p => [prodCol(p), p.displayName])
);

@Component({
  selector: 'app-franchise-order-matrix',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './franchise-order-matrix.component.html',
  styleUrl: './franchise-order-matrix.component.scss',
})
export class FranchiseOrderMatrixComponent implements OnInit {
  rows: FranchiseOrderMatrixRow[] = [];
  loading = true;
  error: string | null = null;

  locColumns: string[] = [];
  prodColumns: string[] = [];

  readonly fixedColumns = [
    'orderNumber', 'contactName',
    'orderDay', 'orderMonth', 'orderYear',
    'nextOrderNumber', 'nextOrderDay', 'nextOrderMonth', 'nextOrderYear',
  ];

  readonly fixedHeaders: Record<string, string> = {
    orderNumber: 'Order #',
    contactName: 'Contact',
    orderDay: 'Day',
    orderMonth: 'Month',
    orderYear: 'Year',
    nextOrderNumber: 'Next Order #',
    nextOrderDay: 'Next Day',
    nextOrderMonth: 'Next Month',
    nextOrderYear: 'Next Year',
  };

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadMatrix();
  }

  loadMatrix(): void {
    this.loading = true;
    this.error = null;

    this.inflowService.listFranchiseOrderMatrix().subscribe({
      next: (response) => {
        this.rows = response.data || [];
        this.extractDynamicColumns();
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading order matrix:', err);
        this.error = `Failed to load order matrix: ${err.message || err.statusText || 'Unknown error'}`;
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

  formatProdHeader(col: string): string {
    // Use the shared product list display name if available
    if (PROD_DISPLAY[col]) return PROD_DISPLAY[col];
    // Fall back to humanising the slug
    return col.substring(5)
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  formatLocHeader(col: string): string {
    return col.substring(4)
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  getCellValue(row: FranchiseOrderMatrixRow, col: string): string {
    const val = row[col];
    if (val == null) return '-';
    return String(val);
  }
}
