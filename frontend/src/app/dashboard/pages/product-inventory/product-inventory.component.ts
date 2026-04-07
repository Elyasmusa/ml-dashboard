import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InflowService, ROAST_SKUS } from '../../../shared/services/inflow.service';
import { InflowProduct, InflowProductVariant, EXCLUDED_PRODUCT_NAMES, EXCLUDED_PRODUCT_SKUS } from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-product-inventory',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './product-inventory.component.html',
  styleUrl: './product-inventory.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductInventoryComponent implements OnInit {
  products: InflowProduct[] = [];
  filteredProducts: InflowProduct[] = [];
  loading = true;
  error: string | null = null;
  searchTerm = '';
  sortColumn: keyof InflowProduct = 'name';
  sortAsc = true;
  expandedBaseName: string | null = null;

  private readonly excludedCategories = new Set([
    'inactive', 'bags', 'storage bins', 'tools', 'merchandise',
    'raw material', 'packaging', 'equipment', 'services',
    'preblends', 'pastries', 'supplies', 'warehouse supplies',
  ]);

  /** Map of exact product names (lowercase) → group base name. */
  private readonly groupOverrides = new Map<string, string>([
    ['ghirardelli caramel sauce', 'Caramel Sauce'],
    ['caramel sauce', 'Caramel Sauce'],
    ['ghirardelli chocolate sauce', 'Chocolate Sauce'],
    ['chocolate sauce', 'Chocolate Sauce'],
    ['mango smoothie', 'Mango Smoothie'],
    ['monin mango smoothie', 'Mango Smoothie'],
    ['strawberry smoothie', 'Strawberry Smoothie'],
    ['monin strawberry smoothie', 'Strawberry Smoothie'],
    ['ceremonial matcha', 'Ceremonial Matcha'],
    ['ceremonial matcha tin', 'Ceremonial Matcha'],
    ['al-kbous black tea (bag)', 'Al-Kbous Black Tea'],
    ['al-kbous black tea', 'Al-Kbous Black Tea'],
    ['hot lids', 'Hot Lids'],
    ['hot white sipper lids', 'Hot Lids'],
    ['white hot sipper lids', 'Hot Lids'],
    ['white sipper lids', 'Hot Lids'],
    ['white universal pp hot cup lids', 'Hot Lids'],
    ['green hot sipper lids', 'Hot Lids'],
    ['black sipper lids', 'Hot Lids'],
    ['16oz white sipper lids', 'Hot Lids'],
    ['white sipper lids - fredom', 'Hot Lids'],
    ['16oz plastic lids', 'Cold Lids'],
    ['karat 16oz clear cold lids', 'Cold Lids'],
    ['pet flat lids', 'Cold Lids'],
    ['16oz pet cold cups', '16oz Cold Cups'],
    ['16oz pet plastic cups', '16oz Cold Cups'],
    ['karat 16oz pet cold cups', '16oz Cold Cups'],
    ['6oz white sipper lids', '6oz White Sipper Lids'],
    ['6oz white sipper lids (2000)', '6oz White Sipper Lids'],
    ['6oz white sipper lids (2,000 pcs)', '6oz White Sipper Lids'],
  ]);

  /** Scaling factors for product variants when stacking quantities. */
  private readonly productScaling = new Map<string, number>([
    ['mango smoothie', 1.0],
    ['monin mango smoothie', 1.0],
    ['strawberry smoothie', 1.0],
    ['monin strawberry smoothie', 1.0],
    ['ceremonial matcha', 1.0],
    ['ceremonial matcha tin', 2.64555],
    ['marib mix | 3 lbs bag', 1.0],
    ['marib mix | 5 lbs bag', 5 / 3],
    ['sanaa mix | 3 lbs bag', 1.0],
    ['sanaa mix | 5 lbs bag', 5 / 3],
    ['radaa mix | 3 lbs bag', 1.0],
    ['radaa mix | 5 lbs bag', 5 / 3],
    ['juban mix | 3 lbs bag', 1.0],
    ['juban mix | 5 lbs bag', 5 / 3],
    ['6oz white sipper lids', 5000 / 2000],
    ['6oz white sipper lids (2000)', 1.0],
    ['6oz white sipper lids (2,000 pcs)', 1.0],
    ['al-kbous black tea (bag)', 0.5],
    ['al-kbous black tea (2 bags)', 1.0],
    ['al-kbous black tea (3 bags)', 1.5],
    ['al-kbous black tea', 2.0],
  ]);

  private getProductScale(name: string): number {
    return this.productScaling.get(name.trim().toLowerCase()) ?? 1.0;
  }

  private readonly destroyRef = inject(DestroyRef);
  private readonly cdr = inject(ChangeDetectorRef);

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    this.loadProducts();
  }

  loadProducts(): void {
    this.loading = true;
    this.error = null;

    this.inflowService.listProducts().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        const deduped = this.deduplicateById(response.data || []);

        // Build roast inventory data from the deduped product list.
        const roastRows = Object.entries(ROAST_SKUS).map(([sku, name]) => {
          const nameLower = name.toLowerCase();
          const p =
            deduped.find((x) => (x.sku || '').trim() === sku) ??
            deduped.find((x) => (x.name || '').toLowerCase() === nameLower);
          return { sku, name, stock: (p?.quantityOnHand as number) ?? 0 };
        });
        this.inflowService.setRoastRows(roastRows);

        const filtered = deduped.filter((p) => {
          const name = (p.name || '').trim().toLowerCase();
          if (this.excludedCategories.has(this.getCategoryName(p).toLowerCase())) return false;
          if (EXCLUDED_PRODUCT_NAMES.has(name)) return false;
          if (EXCLUDED_PRODUCT_SKUS.has((p.sku || '').trim())) return false;
          for (const sep of [' - ', ' | ']) {
            const idx = name.indexOf(sep);
            if (idx > 0 && EXCLUDED_PRODUCT_NAMES.has(name.substring(0, idx).trim())) return false;
          }
          return true;
        });
        this.products = this.groupByBaseName(filtered);
        this.applyFilter();
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (err) => {
        console.error('Error loading products:', err);
        this.error = `Failed to load products: ${err.message || err.statusText || 'Unknown error'}`;
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  applyFilter(): void {
    const term = this.searchTerm.toLowerCase().trim();
    if (!term) {
      this.filteredProducts = [...this.products];
    } else {
      this.filteredProducts = this.products.filter((p) => {
        // Match on the grouped product itself
        if (
          (p.name || '').toLowerCase().includes(term) ||
          (p.sku || '').toLowerCase().includes(term) ||
          this.getCategoryName(p).toLowerCase().includes(term)
        ) {
          return true;
        }
        // Also match on any variant
        return (p.variants || []).some((v) =>
          (v.name || '').toLowerCase().includes(term) ||
          (v.sku || '').toLowerCase().includes(term) ||
          (v.variantLabel || '').toLowerCase().includes(term)
        );
      });
    }
    this.applySort();
  }

  toggleSort(column: keyof InflowProduct): void {
    if (this.sortColumn === column) {
      this.sortAsc = !this.sortAsc;
    } else {
      this.sortColumn = column;
      this.sortAsc = true;
    }
    this.applySort();
  }

  getSortIcon(column: keyof InflowProduct): string {
    if (this.sortColumn !== column) return '';
    return this.sortAsc ? ' \u25B2' : ' \u25BC';
  }

  toggleExpand(product: InflowProduct): void {
    const key = product.name || '';
    this.expandedBaseName = this.expandedBaseName === key ? null : key;
  }

  isExpanded(product: InflowProduct): boolean {
    return this.expandedBaseName === (product.name || '');
  }

  hasVariants(product: InflowProduct): boolean {
    return (product.variants?.length ?? 0) > 1;
  }

  private applySort(): void {
    const col = this.sortColumn;
    const dir = this.sortAsc ? 1 : -1;
    this.filteredProducts.sort((a, b) => {
      const va = a[col] ?? '';
      const vb = b[col] ?? '';
      if (typeof va === 'number' && typeof vb === 'number') {
        return (va - vb) * dir;
      }
      return String(va).localeCompare(String(vb)) * dir;
    });
  }

  private toNum(v: unknown): number {
    if (v == null) return 0;
    const n = typeof v === 'string' ? parseFloat(v) : Number(v);
    return isNaN(n) ? 0 : n;
  }

  private computeQty(p: InflowProduct): number {
    const lines = p.inventoryLines;
    if (lines && lines.length > 0) {
      return Math.round(lines.reduce((sum, l) => sum + this.toNum(l.quantityOnHand), 0));
    }
    return Math.round(this.toNum(p.quantityOnHand));
  }

  private computeReorder(p: InflowProduct): number | undefined {
    const lines = p.inventoryLines;
    if (lines && lines.length > 0) {
      const max = lines.reduce((m, l) =>
        l.reorderPoint != null ? Math.max(m, this.toNum(l.reorderPoint)) : m, 0);
      return Math.round(max);
    }
    return p.reorderPoint != null ? Math.round(this.toNum(p.reorderPoint)) : undefined;
  }

  /**
   * Deduplicate products that share the same id, summing their inventory.
   */
  private deduplicateById(products: InflowProduct[]): InflowProduct[] {
    const map = new Map<string, InflowProduct>();
    for (const p of products) {
      const key = String(p.id ?? p.sku ?? p.name ?? '').trim();
      const qty = this.computeQty(p);
      const reorder = this.computeReorder(p);
      const existing = map.get(key);
      if (!existing) {
        map.set(key, { ...p, quantityOnHand: qty, reorderPoint: reorder });
      } else {
        existing.quantityOnHand = Math.round((existing.quantityOnHand ?? 0) + qty);
        if (reorder != null) {
          existing.reorderPoint = Math.round(Math.max(existing.reorderPoint ?? 0, reorder));
        }
      }
    }
    return Array.from(map.values());
  }

  /**
   * Extract the base product name. Checks manual overrides first,
   * then falls back to stripping the " - Variant" suffix.
   */
  private getBaseName(name: string): string {
    const override = this.groupOverrides.get(name.trim().toLowerCase());
    if (override) return override;
    for (const sep of [' - ', ' | ']) {
      const idx = name.indexOf(sep);
      if (idx > 0) {
        const base = name.substring(0, idx).trim();
        const baseOverride = this.groupOverrides.get(base.toLowerCase());
        if (baseOverride) return baseOverride;
        return base;
      }
    }
    return name.trim();
  }

  /**
   * Extract the variant label. For overrides the full name is the label;
   * for " - " products it's the part after the separator.
   */
  private getVariantLabel(name: string): string {
    if (this.groupOverrides.has(name.trim().toLowerCase())) return name.trim();
    for (const sep of [' - ', ' | ']) {
      const idx = name.indexOf(sep);
      if (idx > 0) return name.substring(idx + sep.length).trim();
    }
    return '';
  }

  /**
   * Group products by base name, stacking variants together.
   */
  private groupByBaseName(products: InflowProduct[]): InflowProduct[] {
    const map = new Map<string, InflowProduct>();

    for (const p of products) {
      const fullName = p.name || '';
      const baseName = this.getBaseName(fullName);
      const variantLabel = this.getVariantLabel(fullName);
      const baseKey = baseName.toLowerCase();

      const variant: InflowProductVariant = {
        id: p.id,
        name: fullName,
        variantLabel: variantLabel || baseName,
        sku: p.sku,
        barcode: p.barcode,
        quantityOnHand: p.quantityOnHand ?? 0,
        reorderPoint: p.reorderPoint,
        cost: p.cost,
        price: p.price,
        defaultPrice: p.defaultPrice,
        category: p.category,
        inventoryLines: p.inventoryLines,
      };

      const scale = this.getProductScale(fullName);
      const scaledQty = Math.round((p.quantityOnHand ?? 0) * scale);

      const existing = map.get(baseKey);
      if (!existing) {
        map.set(baseKey, {
          ...p,
          name: baseName,
          quantityOnHand: scaledQty,
          variants: [variant],
        });
      } else {
        existing.quantityOnHand = Math.round((existing.quantityOnHand ?? 0) + scaledQty);
        if (p.reorderPoint != null) {
          existing.reorderPoint = Math.round(Math.max(existing.reorderPoint ?? 0, p.reorderPoint));
        }
        existing.variants!.push(variant);
      }
    }

    return Array.from(map.values());
  }

  getCategoryName(product: InflowProduct | InflowProductVariant): string {
    const cat = product.category;
    if (!cat) return '-';
    if (typeof cat === 'string') return cat;
    return cat.name || '-';
  }

  formatCurrency(value: number | string | undefined | null): string {
    if (value == null) return '-';
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num)) return '-';
    return '$' + num.toFixed(2);
  }

  getStockClass(product: InflowProduct | InflowProductVariant): string {
    const qty = product.quantityOnHand;
    if (qty == null) return '';
    if (qty <= 0) return 'stock-out';
    const reorder = product.reorderPoint;
    if (reorder != null && qty <= reorder) return 'stock-low';
    return 'stock-ok';
  }

  getStockLabel(product: InflowProduct | InflowProductVariant): string {
    const qty = product.quantityOnHand;
    if (qty == null) return '';
    if (qty <= 0) return 'Out of stock';
    const reorder = product.reorderPoint;
    if (reorder != null && qty <= reorder) return 'Low stock';
    return 'In stock';
  }
}
