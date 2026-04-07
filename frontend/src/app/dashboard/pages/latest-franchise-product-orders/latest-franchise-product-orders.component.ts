import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { InflowService } from '../../../shared/services/inflow.service';
import { TrainingService } from '../../../shared/services/training.service';
import { FranchiseOrderMatrixRow } from '../../../shared/models/inflow.model';
import { MATRIX_PRODUCTS, prodCol, nextProdCol } from '../../../shared/constants/products';

/** Slug → display name lookup for both prod_ and next_prod_ columns. */
const PROD_DISPLAY: Record<string, string> = Object.fromEntries([
  ...MATRIX_PRODUCTS.map(p => [prodCol(p),     p.displayName]),
  ...MATRIX_PRODUCTS.map(p => [nextProdCol(p), p.displayName]),
]);

@Component({
  selector: 'app-latest-franchise-product-orders',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './latest-franchise-product-orders.component.html',
  styleUrl: './latest-franchise-product-orders.component.scss',
})
export class LatestFranchiseProductOrdersComponent implements OnInit {
  rows: FranchiseOrderMatrixRow[] = [];
  loading = true;
  error: string | null = null;
  predictionsMissing = false;

  locColumns: string[] = [];
  prodColumns: string[] = [];
  nextProdColumns: string[] = [];

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

  constructor(
    private inflowService: InflowService,
    private trainingService: TrainingService,
  ) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;
    this.predictionsMissing = false;

    forkJoin({
      latest: this.inflowService.listLatestFranchiseProductOrders(),
      predictions: this.trainingService.getProductVariantPredictions('base').pipe(
        catchError(() => of({ data: [], totalCount: 0 }))
      ),
    }).subscribe({
      next: ({ latest, predictions }) => {
        const predMap = new Map<string, Record<string, number>>();
        for (const pred of (predictions.data || [])) {
          predMap.set(pred.orderNumber, pred.predictedProducts || {});
        }

        if (predMap.size === 0) {
          this.predictionsMissing = true;
        }

        // Merge predicted next-order products into each row
        this.rows = (latest.data || []).map(row => {
          const predicted = predMap.get(String(row['orderNumber'] ?? '')) ?? {};
          return { ...row, ...predicted };
        });

        this.extractDynamicColumns();
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading latest franchise product orders:', err);
        this.error = `Failed to load data: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
      },
    });
  }

  private extractDynamicColumns(): void {
    const locSet      = new Set<string>();
    const prodSet     = new Set<string>();
    const nextProdSet = new Set<string>();

    for (const row of this.rows) {
      for (const key of Object.keys(row)) {
        if (key.startsWith('loc_'))                             locSet.add(key);
        else if (key.startsWith('prod_'))                       prodSet.add(key);
        else if (key.startsWith('next_prod_') && (row[key] as number) > 0) nextProdSet.add(key);
      }
    }

    this.locColumns      = Array.from(locSet).sort();
    this.prodColumns     = Array.from(prodSet).sort();
    this.nextProdColumns = Array.from(nextProdSet).sort();
  }

  formatProdHeader(col: string): string {
    return PROD_DISPLAY[col] ?? col.replace(/^(next_prod_|prod_)/, '')
      .split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }

  formatLocHeader(col: string): string {
    return col.substring(4)
      .split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }

  getCellValue(row: FranchiseOrderMatrixRow, col: string): string {
    const val = row[col];
    if (val == null || val === 0) return '-';
    return String(val);
  }
}
