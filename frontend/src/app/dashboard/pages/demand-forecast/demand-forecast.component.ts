import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { forkJoin } from 'rxjs';
import { TrainingService } from '../../../shared/services/training.service';
import { InflowService } from '../../../shared/services/inflow.service';
import { SettingsService } from '../../../shared/services/settings.service';
import { MATRIX_PRODUCTS, nextProdCol } from '../../../shared/constants/products';

interface DemandRow {
  rank: number;
  name: string;
  category: string;
  totalDemand: number;
  currentStock: number;
  net: number;
  /** (currentStock - threshold) / threshold, or null if no threshold set. */
  stockCoverage: number | null;
  /** (|net| + threshold) / batchSize, or null if no batch size defined. */
  netBatches: number | null;
  /** ((|Net|+T)/Batch) / (1 + stockCoverage * (threshold/batchSize)), or null if not computable. */
  batchScore: number | null;
}

@Component({
  selector: 'app-demand-forecast',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './demand-forecast.component.html',
  styleUrl: './demand-forecast.component.scss',
})
export class DemandForecastComponent implements OnInit {
  loading = true;
  error: string | null = null;
  demandRows: DemandRow[] = [];

  /** Display name → product category label */
  private readonly productCategoryMap: Record<string, string> = {
    'Medium Roast Coffee (Whole)': 'Whole',
    'Dark Roast Coffee (Whole)':   'Whole',
    'Qishr':                       'Whole',
    'Sunrise Socotra':             'Whole',
    'Mount Haraz':                 'Whole',
    'Gate of Yemen':               'Whole',
    'Queen Sheeba':                'Whole',
    'Cinnamon (Ground)':           'Spices',
    'Cloves (Whole)':              'Spices',
    'Cardamom (Ground)':           'Spices',
    'Ginger (Ground)':             'Spices',
    'Juban Mix':                   'Mixes',
    'Radaa Mix':                   'Mixes',
    'Marib Mix':                   'Mixes',
    'Sanaa Mix':                   'Mixes',
    'Ancient Marib':               'Mixes',
    "Old City Sana'a":             'Mixes',
    'Valley Juban':                'Mixes',
  };

  /** Display name → Inflow API product name prefix (for stock lookup) */
  private readonly productApiNameMap: Record<string, string> = {
    'Medium Roast Coffee (Whole)': 'medium roast coffee (whole)',
    'Dark Roast Coffee (Whole)':   'dark roast coffee (whole)',
    'Qishr':                       'qishr',
    'Sunrise Socotra':             'sunrise socotra',
    'Mount Haraz':                 'mount haraz',
    'Gate of Yemen':               'gate of yemen',
    'Queen Sheeba':                'queen sheeba',
    'Cinnamon (Ground)':           'cinnamon (ground) | 5 lbs bag',
    'Cloves (Whole)':              'cloves (whole) | 5 lbs bag',
    'Cardamom (Ground)':           'cardamom (ground) | 5 lbs bag',
    'Ginger (Ground)':             'ginger (ground) | 5 lbs bag',
    'Juban Mix':                   'juban mix',
    'Radaa Mix':                   'radaa mix',
    'Marib Mix':                   'marib mix',
    'Sanaa Mix':                   'sanaa mix',
    'Ancient Marib':               'ancient marib',
    "Old City Sana'a":             'old city sana\'a',
    'Valley Juban':                'valley juban',
  };

  constructor(
    private trainingService: TrainingService,
    private inflowService: InflowService,
    private settingsService: SettingsService,
  ) {}

  ngOnInit(): void {
    this.settingsService.load().subscribe();
    this.load();
  }

  private load(): void {
    this.loading = true;
    this.error = null;

    forkJoin({
      predictions: this.trainingService.getCombinedPredictions('base'),
      products: this.inflowService.listProducts(),
    }).subscribe({
      next: ({ predictions, products }) => {
        // Build stock map keyed by display name
        const stockMap: Record<string, number> = {};
        for (const [displayName, prefix] of Object.entries(this.productApiNameMap)) {
          let total = 0;
          for (const p of (products.data || [])) {
            const apiName = (p.name || '').toLowerCase();
            if (apiName === prefix || apiName.startsWith(prefix + ' |')) {
              total += Number(p.totalQuantityOnHand) || 0;
            }
          }
          stockMap[displayName] = Math.round(total);
        }

        // Sum predicted quantities per slug across ALL predictions
        const slugTotals: Record<string, number> = {};
        for (const row of (predictions.data || [])) {
          for (const [slug, qty] of Object.entries(row.predictedProducts || {})) {
            const rounded = Math.round(qty);
            if (rounded > 0) {
              slugTotals[slug] = (slugTotals[slug] || 0) + rounded;
            }
          }
        }

        // Build rows for dashboard products, ranked by total demand
        const rows: Omit<DemandRow, 'rank'>[] = MATRIX_PRODUCTS
          .map(p => {
            const displayName = p.displayName;
            const slug = nextProdCol(p);
            const totalDemand = slugTotals[slug] || 0;
            const currentStock = stockMap[displayName] ?? 0;
            const threshold = this.settingsService.current.stock.thresholds[displayName] ?? null;
            const stockCoverage = threshold !== null ? (currentStock - threshold) / threshold : null;
            const net = currentStock - totalDemand;
            const batchSize = this.settingsService.current.manufacturing.timings[displayName]?.bagBatchSize ?? null;
            const thresholdVal = threshold ?? 0;
            const absNet = net >= 0 ? 0 : Math.abs(net);
            const netBatches = batchSize !== null ? (absNet + thresholdVal) / batchSize : null;
            let batchScore: number | null = null;
            if (netBatches !== null && stockCoverage !== null && batchSize !== null && threshold !== null) {
              const denominator = (1 + stockCoverage) * (threshold / batchSize);
              if (denominator !== 0) {
                batchScore = netBatches / denominator;
              }
            } else if (netBatches === 0) {
              batchScore = 0;
            }
            return {
              name: displayName,
              category: this.productCategoryMap[displayName] || '',
              totalDemand,
              currentStock,
              net,
              stockCoverage,
              netBatches,
              batchScore,
            };
          })
          .sort((a, b) => b.totalDemand - a.totalDemand);

        this.demandRows = rows.map((r, i) => ({ ...r, rank: i + 1 }));
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load demand forecast.';
        this.loading = false;
      },
    });
  }

  getNetClass(net: number): string {
    if (net < 0) return 'net-negative';
    if (net === 0) return 'net-zero';
    return 'net-positive';
  }

  getRankLabel(rank: number): string {
    if (rank === 1) return '1st';
    if (rank === 2) return '2nd';
    if (rank === 3) return '3rd';
    return `${rank}th`;
  }

  formatCoverage(val: number | null): string {
    if (val === null) return '—';
    const pct = Math.round(val * 100);
    return (pct >= 0 ? '+' : '') + pct + '%';
  }

  getCoverageClass(val: number | null): string {
    if (val === null) return 'coverage-na';
    if (val < 0) return 'coverage-negative';
    if (val === 0) return 'coverage-zero';
    return 'coverage-positive';
  }

  formatBatchScore(val: number | null): string {
    if (val === null) return '—';
    return val % 1 === 0 ? val.toString() : val.toFixed(2);
  }

  formatNetBatches(val: number | null): string {
    if (val === null) return '—';
    return val % 1 === 0 ? val.toString() : val.toFixed(1);
  }

  get totalPredictedOrders(): number {
    return this.demandRows.reduce((sum, r) => sum + r.totalDemand, 0);
  }
}
