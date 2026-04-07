import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService } from '../../../shared/services/inflow.service';
import { FranchiseOrderMatrixRow } from '../../../shared/models/inflow.model';
import { MATRIX_PRODUCTS, nextProdCol } from '../../../shared/constants/products';

/** Slug → display name map built from the shared product list. */
const NEXT_PROD_DISPLAY: Record<string, string> = Object.fromEntries(
  MATRIX_PRODUCTS.map(p => [nextProdCol(p), p.displayName])
);

@Component({
  selector: 'app-franchise-product-matrix',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './franchise-product-matrix.component.html',
  styleUrl: './franchise-product-matrix.component.scss',
})
export class FranchiseProductMatrixComponent implements OnInit {
  rows: FranchiseOrderMatrixRow[] = [];
  loading = true;
  error: string | null = null;

  locColumns: string[] = [];
  nextProdColumns: string[] = [];

  readonly fixedColumns = [
    'orderNumber', 'contactName', 'daysToNext',
  ];

  readonly fixedHeaders: Record<string, string> = {
    orderNumber: 'Order #',
    contactName: 'Contact',
    daysToNext: 'Days to Next Order',
  };

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadMatrix();
  }

  loadMatrix(): void {
    this.loading = true;
    this.error = null;

    this.inflowService.listFranchiseProductMatrix().subscribe({
      next: (response) => {
        const raw = response.data || [];
        this.rows = raw.map(r => ({ ...r, daysToNext: this.computeDaysToNext(r) }));
        this.extractDynamicColumns();
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading product order matrix:', err);
        this.error = `Failed to load product order matrix: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
      },
    });
  }

  private computeDaysToNext(row: FranchiseOrderMatrixRow): number | null {
    const oDay = row['orderDay'], oMonth = row['orderMonth'], oYear = row['orderYear'];
    const nDay = row['nextOrderDay'], nMonth = row['nextOrderMonth'], nYear = row['nextOrderYear'];
    if (oDay == null || oMonth == null || oYear == null ||
        nDay == null || nMonth == null || nYear == null) return null;
    const orderDate = new Date(Number(oYear), Number(oMonth) - 1, Number(oDay));
    const nextDate  = new Date(Number(nYear), Number(nMonth) - 1, Number(nDay));
    return Math.round((nextDate.getTime() - orderDate.getTime()) / 86400000);
  }

  private extractDynamicColumns(): void {
    const locSet = new Set<string>();
    const nextProdSet = new Set<string>();

    for (const row of this.rows) {
      for (const key of Object.keys(row)) {
        if (key.startsWith('loc_')) locSet.add(key);
        else if (key.startsWith('next_prod_')) nextProdSet.add(key);
      }
    }

    this.locColumns = Array.from(locSet).sort();
    this.nextProdColumns = Array.from(nextProdSet).sort();
  }

  formatNextProdHeader(col: string): string {
    // Use the shared product list display name if available
    if (NEXT_PROD_DISPLAY[col]) return NEXT_PROD_DISPLAY[col];
    // Fall back to humanising the slug
    return col.substring(10)
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
