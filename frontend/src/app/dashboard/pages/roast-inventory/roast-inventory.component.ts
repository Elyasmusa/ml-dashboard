import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InflowService, RoastRow, ROAST_SKUS } from '../../../shared/services/inflow.service';
import { InflowInventoryLine } from '../../../shared/models/inflow.model';

@Component({
  selector: 'app-roast-inventory',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './roast-inventory.component.html',
  styleUrl: './roast-inventory.component.scss',
})
export class RoastInventoryComponent implements OnInit {
  roasts: RoastRow[] = [];
  loading = true;
  error: string | null = null;

  constructor(private inflowService: InflowService) {}

  ngOnInit(): void {
    // If product inventory has already run its filter step the data is ready.
    const existing = this.inflowService.roastRows$.value;
    if (existing.length > 0) {
      this.roasts = existing;
      this.loading = false;
      return;
    }

    // Direct navigation — product inventory hasn't run yet.
    // Call listProducts() (cached, no extra HTTP request if already fetched)
    // and extract roast rows locally using the same SKU map.
    this.inflowService.listProducts().subscribe({
      next: (res) => {
        const products = res.data || [];
        const rows: RoastRow[] = Object.entries(ROAST_SKUS).map(([sku, name]) => {
          const nameLower = name.toLowerCase();
          const p =
            products.find((x) => (x.sku || '').trim() === sku) ??
            products.find((x) => (x.name || '').toLowerCase() === nameLower);
          return { sku, name, stock: p ? this.computeQty(p) : 0 };
        });
        this.inflowService.setRoastRows(rows);
        this.roasts = rows;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load roast stock.';
        this.loading = false;
      },
    });
  }

  private computeQty(p: { quantityOnHand?: number; inventoryLines?: InflowInventoryLine[] }): number {
    const lines = p.inventoryLines;
    if (lines && lines.length > 0) {
      return Math.round(lines.reduce((sum, l) => sum + (Number(l.quantityOnHand) || 0), 0));
    }
    return Math.round(Number(p.quantityOnHand) || 0);
  }
}
