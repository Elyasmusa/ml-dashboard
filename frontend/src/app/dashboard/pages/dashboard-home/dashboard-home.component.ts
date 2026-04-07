import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { interval, switchMap } from 'rxjs';
import { TrainingService } from '../../../shared/services/training.service';
import { CombinedPredictionRow } from '../../../shared/models/training.model';
import { InflowService } from '../../../shared/services/inflow.service';
import { SettingsService } from '../../../shared/services/settings.service';
import {
  InflowProduct,
  InflowSalesOrder,
  InflowSalesOrderItem,
  InflowSalesOrderLine,
  EXCLUDED_PRODUCT_NAMES,
  EXCLUDED_PRODUCT_SKUS,
} from '../../../shared/models/inflow.model';
import { MATRIX_PRODUCTS, nextProdCol } from '../../../shared/constants/products';
import { formatCity, formatDate, buildProductEntries } from '../../../shared/utils/prediction.utils';
import { ManufacturingService, ManufacturingRecommendation } from '../../../shared/services/manufacturing.service';

type ViewMode = 'day' | 'week' | 'month';

const TZ = 'America/New_York';

@Component({
  selector: 'app-dashboard-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard-home.component.html',
  styleUrl: './dashboard-home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardHomeComponent implements OnInit {
  activeView: ViewMode = 'day';
  allPredictions: CombinedPredictionRow[] = [];
  activeOrdersToday: InflowSalesOrder[] = [];
  loading = true;
  loadingActiveOrders = true;
  updating = false;
  expandedActiveOrderId: string | null = null;
  showOverdueTable = false;

  // --- Cached computed properties (updated only when source data changes) ---
  filteredPredictions: CombinedPredictionRow[] = [];
  overduePredictions: CombinedPredictionRow[] = [];
  weekPredictions: CombinedPredictionRow[] = [];
  productTotals: Record<string, number> = {};
  allPredictionTotals: Record<string, number> = {};
  weekPredictionTotals: Record<string, number> = {};
  activeOrderProductTotals: Record<string, number> = {};
  manufacturingRecommendations: ManufacturingRecommendation[] = [];
  totalMfgMinutes = 0;
  predictedOrderCount = 0;

  private _futurePredictions: CombinedPredictionRow[] = [];
  private _productEntriesCache = new Map<string, { name: string; qty: number }[]>();
  // -------------------------------------------------------------------------

  private readonly destroyRef = inject(DestroyRef);
  private readonly cdr = inject(ChangeDetectorRef);

  /** Current stock on hand keyed by display product name. */
  stockMap: Record<string, number> = {};

  readonly productColumns = {
    roasts: [
      'Light Roast',
      'Medium Roast',
      'Dark Roast',
    ],
    whole: [
      'Medium Roast Coffee (Whole)',
      'Dark Roast Coffee (Whole)',
      'Qishr',
      'Sunrise Socotra',
      'Mount Haraz',
      'Gate of Yemen',
      'Queen Sheeba',
    ],
    spices: [
      'Cinnamon (Ground)',
      'Cloves (Whole)',
      'Cardamom (Ground)',
      'Ginger (Ground)',
    ],
    mixes: [
      'Juban Mix',
      'Radaa Mix',
      'Marib Mix',
      'Sanaa Mix',
      'Ancient Marib',
      'Old City Sana\'a',
      'Valley Juban',
    ],
  };

  /** Map display name → prediction slug key — built from the shared product list. */
  private readonly productSlugMap: Record<string, string> = Object.fromEntries(
    MATRIX_PRODUCTS.map(p => [p.displayName, nextProdCol(p)])
  );

  /** Map display name → Inflow API product name prefix (for stock lookup). */
  private readonly productApiNameMap: Record<string, string> = {
    'Medium Roast Coffee (Whole)': 'medium roast coffee (whole)',
    'Dark Roast Coffee (Whole)': 'dark roast coffee (whole)',
    'Qishr': 'qishr',
    'Sunrise Socotra': 'sunrise socotra',
    'Mount Haraz': 'mount haraz',
    'Gate of Yemen': 'gate of yemen',
    'Queen Sheeba': 'queen sheeba',
    'Cinnamon (Ground)': 'cinnamon (ground) | 5 lbs bag',
    'Cloves (Whole)': 'cloves (whole) | 5 lbs bag',
    'Cardamom (Ground)': 'cardamom (ground) | 5 lbs bag',
    'Ginger (Ground)': 'ginger (ground) | 5 lbs bag',
    'Juban Mix': 'juban mix',
    'Radaa Mix': 'radaa mix',
    'Marib Mix': 'marib mix',
    'Sanaa Mix': 'sanaa mix',
    'Ancient Marib': 'ancient marib',
    'Old City Sana\'a': 'old city sana\'a',
    'Valley Juban': 'valley juban',
  };

  /** Map display name → exact Inflow SKU for products where a specific variant must be used. */
  private readonly productSkuMap: Record<string, string> = {
    'Cardamom (Ground)':  'IF5127738',
    'Cinnamon (Ground)':  'IF5127739',
    'Ginger (Ground)':    'IF5127740',
    'Cloves (Whole)':     'IF5127796',
  };

  /** Get the minimum stock threshold for a product. */
  getThreshold(name: string): number {
    return this.settingsService.current.stock.thresholds[name] ?? 0;
  }

  readonly productRowIndices = Array.from(
    { length: Math.max(
      this.productColumns.roasts.length,
      this.productColumns.whole.length,
      this.productColumns.spices.length,
      this.productColumns.mixes.length,
    ) },
    (_, i) => i,
  );

  /** Get predicted qty for a product display name (reads from cached productTotals). */
  getProductQty(name: string): number {
    if (!name) return 0;
    const slug = this.productSlugMap[name];
    if (!slug) return 0;
    return this.productTotals[slug] || 0;
  }

  /** Get current stock on hand for a product display name. */
  getStock(name: string): number {
    return this.stockMap[name] ?? 0;
  }

  /** Get remaining stock = current stock - predicted qty - active order qty. */
  getRemaining(name: string): number {
    return this.getStock(name) - this.getProductQty(name) - (this.activeOrderProductTotals[name] || 0);
  }

  /** True if remaining stock falls below the minimum threshold. */
  isLow(name: string): boolean {
    return this.getRemaining(name) < this.getThreshold(name);
  }

  /** Total predicted demand across ALL non-overdue predictions (reads from cached allPredictionTotals). */
  getTotalDemand(name: string): number {
    const slug = this.productSlugMap[name];
    if (!slug) return 0;
    return this.allPredictionTotals[slug] || 0;
  }

  /** Get this week's predicted demand for a product (reads from cached weekPredictionTotals). */
  getWeekDemand(name: string): number {
    if (!name) return 0;
    const slug = this.productSlugMap[name];
    if (!slug) return 0;
    return this.weekPredictionTotals[slug] || 0;
  }

  /** Stock remaining after this week's predicted orders. */
  getRemainingAfterWeek(name: string): number {
    return this.getStock(name) - this.getWeekDemand(name);
  }

  get viewCapacityMinutes(): number {
    return this.manufacturingService.viewCapacityMinutes(this.activeView);
  }

  formatMfgTime(min: number): string {
    return this.manufacturingService.formatMfgTime(min);
  }

  // ---------------------------------------------------------------------------
  // Recompute methods — run once when source data changes, not on every CD cycle
  // ---------------------------------------------------------------------------

  /** Recompute all prediction-derived properties.
   *  Call whenever allPredictions or activeView changes. */
  private _recomputePredictions(): void {
    const nowET = this.nowInET();
    const pad = (n: number) => String(n).padStart(2, '0');
    const toStr = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;
    const today = toStr(nowET.year, nowET.month, nowET.day);
    const { end } = this.getDateRange(nowET);

    // filteredPredictions — active view window, today or later
    this.filteredPredictions = this.allPredictions.filter(row => {
      if (!row.predictedNextOrderDate) return false;
      const eff = this.effectiveDate(row.predictedNextOrderDate);
      return eff >= today && eff <= end;
    });

    // overduePredictions — effective date before today
    this.overduePredictions = this.allPredictions.filter(row => {
      if (!row.predictedNextOrderDate) return false;
      return this.effectiveDate(row.predictedNextOrderDate) < today;
    });

    // weekPredictions — Sat–Fri window, today or later
    const daysSinceSat = (nowET.dayOfWeek + 1) % 7;
    const satDate = new Date(nowET.year, nowET.month - 1, nowET.day - daysSinceSat);
    const friDate = new Date(nowET.year, nowET.month - 1, nowET.day - daysSinceSat + 6);
    const weekStart = toStr(satDate.getFullYear(), satDate.getMonth() + 1, satDate.getDate());
    const weekEnd   = toStr(friDate.getFullYear(), friDate.getMonth() + 1, friDate.getDate());

    this.weekPredictions = this.allPredictions.filter(row => {
      if (!row.predictedNextOrderDate) return false;
      const eff = this.effectiveDate(row.predictedNextOrderDate);
      return eff >= today && eff >= weekStart && eff <= weekEnd;
    });

    // futurePredictions — all non-overdue, base for demand / manufacturing math
    this._futurePredictions = this.allPredictions.filter(row =>
      !!row.predictedNextOrderDate && this.effectiveDate(row.predictedNextOrderDate) >= today
    );

    // Aggregate totals — one pass each
    this.productTotals      = this._aggregateTotals(this.filteredPredictions);
    this.allPredictionTotals = this._aggregateTotals(this._futurePredictions);
    this.weekPredictionTotals = this._aggregateTotals(this.weekPredictions);

    this.predictedOrderCount = this.filteredPredictions.length;

    // Build product entries cache — keyed by orderNumber for O(1) template lookups
    this._productEntriesCache.clear();
    for (const row of this.allPredictions) {
      this._productEntriesCache.set(row.orderNumber ?? '', this._buildProductEntries(row));
    }

    this._recomputeManufacturing();
  }

  /** Aggregate predictedProducts totals across a set of prediction rows. */
  private _aggregateTotals(rows: CombinedPredictionRow[]): Record<string, number> {
    const totals: Record<string, number> = {};
    for (const row of rows) {
      for (const [slug, qty] of Object.entries(row.predictedProducts || {})) {
        const rounded = Math.round(qty);
        if (rounded > 0) {
          totals[slug] = (totals[slug] || 0) + rounded;
        }
      }
    }
    return totals;
  }

  /** Build sorted product entries for a single prediction row. */
  private _buildProductEntries(row: CombinedPredictionRow): { name: string; qty: number }[] {
    return buildProductEntries(row);
  }

  /** Recompute activeOrderProductTotals then trigger manufacturing recompute.
   *  Call whenever activeOrdersToday changes. */
  private _recomputeActiveOrders(): void {
    const totals: Record<string, number> = {};
    for (const order of this.activeOrdersToday) {
      for (const item of this.getActiveOrderItems(order)) {
        const itemName = (item.productName || '').toLowerCase().trim();
        if (!itemName) continue;
        for (const [displayName, apiName] of Object.entries(this.productApiNameMap)) {
          const base = apiName.split(' |')[0].trim();
          if (itemName === base || itemName.startsWith(base + ' |') || itemName.startsWith(base + ' - ')) {
            totals[displayName] = (totals[displayName] || 0) + Math.round(item.quantity ?? 0);
            break;
          }
        }
      }
    }
    this.activeOrderProductTotals = totals;
    this._recomputeManufacturing();
  }

  /** Recompute manufacturingRecommendations and totalMfgMinutes.
   *  Call whenever stockMap, activeOrderProductTotals, prediction totals, or activeView changes. */
  private _recomputeManufacturing(): void {
    const { recommendations, totalMinutes } = this.manufacturingService.compute({
      stockMap: this.stockMap,
      activeOrderProductTotals: this.activeOrderProductTotals,
      productTotals: this.productTotals,
      weekPredictionTotals: this.weekPredictionTotals,
      allPredictionTotals: this.allPredictionTotals,
      activeView: this.activeView,
    });
    this.manufacturingRecommendations = recommendations;
    this.totalMfgMinutes = totalMinutes;
    this.cdr.markForCheck();
  }

  // ---------------------------------------------------------------------------

  constructor(
    private trainingService: TrainingService,
    private inflowService: InflowService,
    private settingsService: SettingsService,
    private manufacturingService: ManufacturingService,
  ) {}

  ngOnInit(): void {
    this.settingsService.load().pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
    this.loadPredictions();
    this.loadStock();
    this.loadActiveOrdersWeek();
    this.startPolling();
  }

  triggerUpdate(): void {
    if (this.updating) return;
    this.updating = true;
    this.inflowService.updateData().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.updating = false;
        this.inflowService.clearCache();
        this.loadPredictions();
        this.loadStock();
        this.loadActiveOrdersWeek();
      },
      error: () => {
        this.updating = false;
        this.cdr.markForCheck();
      },
    });
  }

  selectView(view: ViewMode): void {
    this.activeView = view;
    this._recomputePredictions();
  }

  get viewLabel(): string {
    switch (this.activeView) {
      case 'day': return 'Today';
      case 'week': return 'This Week (Sat\u2013Fri)';
      case 'month': return 'This Month';
    }
  }

  /** Return the cached product entries for a prediction row — O(1) Map lookup. */
  getProductEntries(row: CombinedPredictionRow): { name: string; qty: number }[] {
    return this._productEntriesCache.get(row.orderNumber ?? '') ?? this._buildProductEntries(row);
  }

  formatDate(date?: string): string {
    return formatDate(date);
  }

  formatCity(slug: string): string {
    return formatCity(slug);
  }

  private startPolling(): void {
    interval(this.settingsService.current.system.frontendPollIntervalMs).pipe(
      switchMap(() => this.inflowService.updateData()),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (result) => {
        // Always refresh stock and active orders on each poll cycle
        this.inflowService.clearCache('products');
        this.loadStock();
        this.loadActiveOrdersWeek();
        // If new orders were found, also reload predictions
        if (result.totalNewRecords > 0) {
          this.loadPredictions();
        }
      },
      error: () => {
        // Still refresh stock and active orders even if the update call fails
        this.inflowService.clearCache('products');
        this.loadStock();
        this.loadActiveOrdersWeek();
      },
    });
  }

  private loadPredictions(): void {
    this.loading = true;
    this.trainingService.getCombinedPredictions('base').pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.allPredictions = res.data || [];
        this.loading = false;
        this._recomputePredictions();
      },
      error: () => {
        this.allPredictions = [];
        this.loading = false;
        this._recomputePredictions();
      },
    });
  }

  /** Compute quantity on hand for a product using inventory lines when available,
   *  mirroring the logic in ProductInventoryComponent. */
  private computeQty(p: InflowProduct): number {
    const lines = p.inventoryLines;
    if (lines && lines.length > 0) {
      return lines.reduce((sum, l) => sum + (Number(l.quantityOnHand) || 0), 0);
    }
    return Number(p.quantityOnHand) || 0;
  }

  private loadStock(): void {
    this.inflowService.listProducts().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        const map: Record<string, number> = {};
        const products = res.data || [];

        // Non-roast products — looked up via name prefix or exact SKU.
        for (const displayName of Object.keys(this.productApiNameMap)) {
          const sku = this.productSkuMap[displayName];
          let total = 0;
          if (sku) {
            const match = products.find(p => (p.sku || '').trim() === sku);
            if (match) total = this.computeQty(match);
          } else {
            const baseName = this.productApiNameMap[displayName].split(' |')[0];
            for (const p of products) {
              const apiName = (p.name || '').toLowerCase();
              if (apiName === baseName || apiName.startsWith(baseName + ' |')) {
                total += this.computeQty(p);
              }
            }
          }
          map[displayName] = Math.round(total);
        }

        // Roast stock: populated by the tap inside listProducts() before this
        // subscriber callback runs, so roastRows$.value is always ready here.
        for (const { name, stock } of this.inflowService.roastRows$.value) {
          map[name] = stock;
        }

        this.stockMap = map;
        this._recomputeManufacturing();
      },
    });
  }

  private loadActiveOrdersWeek(): void {
    this.loadingActiveOrders = true;
    this.inflowService.listActiveOrdersWeek().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.activeOrdersToday = (res.data || []).filter(o =>
          (o.orderNumber || '').toUpperCase().startsWith('SO-')
        );
        this.loadingActiveOrders = false;
        this._recomputeActiveOrders();
      },
      error: () => {
        this.activeOrdersToday = [];
        this.loadingActiveOrders = false;
        this._recomputeActiveOrders();
      },
    });
  }

  formatOrderStatus(status?: string): string {
    if (!status) return 'Open';
    return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
  }

  getActiveOrderId(order: InflowSalesOrder): string {
    return order.salesOrderId || order.id || '';
  }

  toggleActiveOrderExpand(order: InflowSalesOrder): void {
    const id = this.getActiveOrderId(order);
    if (!id) return;
    this.expandedActiveOrderId = this.expandedActiveOrderId === id ? null : id;
  }

  isActiveOrderExpanded(order: InflowSalesOrder): boolean {
    const id = this.getActiveOrderId(order);
    return id !== '' && this.expandedActiveOrderId === id;
  }

  getActiveOrderItems(order: InflowSalesOrder): InflowSalesOrderItem[] {
    if (order.lines && order.lines.length > 0) {
      return order.lines
        .filter(
          (line: InflowSalesOrderLine) =>
            !EXCLUDED_PRODUCT_NAMES.has((line.product?.name || '').trim().toLowerCase()) &&
            !EXCLUDED_PRODUCT_SKUS.has((line.product?.sku || '').trim())
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
        }));
    }
    return (order.items || []).filter(
      (item) => !EXCLUDED_PRODUCT_NAMES.has((item.productName || '').trim().toLowerCase())
    );
  }

  formatCurrency(value?: number | string): string {
    const n = Number(value);
    if (isNaN(n)) return '-';
    return '$' + n.toFixed(2);
  }

  /**
   * Return the effective date for a prediction: Saturday → next Monday, Sunday → next Monday.
   * All other days are returned unchanged. Input and output are YYYY-MM-DD strings.
   */
  private effectiveDate(dateStr: string): string {
    // Parse at noon to avoid any DST edge cases
    const d = new Date(dateStr + 'T12:00:00');
    const dow = d.getDay(); // 0=Sun, 6=Sat
    if (dow === 6) d.setDate(d.getDate() + 2); // Sat → Mon
    if (dow === 0) d.setDate(d.getDate() + 1); // Sun → Mon
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /** Get the current date parts in America/New_York. */
  private nowInET(): { year: number; month: number; day: number; dayOfWeek: number } {
    const now = new Date();
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
    }).formatToParts(now);

    const get = (type: string) => parts.find(p => p.type === type)?.value || '';
    const year = parseInt(get('year'), 10);
    const month = parseInt(get('month'), 10);
    const day = parseInt(get('day'), 10);

    // Compute day of week from a Date constructed in ET
    const etDate = new Date(year, month - 1, day);
    const dayOfWeek = etDate.getDay(); // 0=Sun, 6=Sat

    return { year, month, day, dayOfWeek };
  }

  /** Build YYYY-MM-DD start/end strings for the active view period in ET. */
  private getDateRange(et: { year: number; month: number; day: number; dayOfWeek: number }): { start: string; end: string } {
    const pad = (n: number) => String(n).padStart(2, '0');
    const toStr = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;

    switch (this.activeView) {
      case 'day': {
        const s = toStr(et.year, et.month, et.day);
        return { start: s, end: s };
      }

      case 'week': {
        // Week runs Saturday to Friday
        // Days since last Saturday: Sat=0, Sun=1, Mon=2, ..., Fri=6
        const daysSinceSat = (et.dayOfWeek + 1) % 7;
        const satDate = new Date(et.year, et.month - 1, et.day - daysSinceSat);
        const friDate = new Date(et.year, et.month - 1, et.day - daysSinceSat + 6);
        const start = toStr(satDate.getFullYear(), satDate.getMonth() + 1, satDate.getDate());
        const end = toStr(friDate.getFullYear(), friDate.getMonth() + 1, friDate.getDate());
        return { start, end };
      }

      case 'month': {
        const start = toStr(et.year, et.month, 1);
        const lastDay = new Date(et.year, et.month, 0).getDate();
        const end = toStr(et.year, et.month, lastDay);
        return { start, end };
      }
    }
  }
}
