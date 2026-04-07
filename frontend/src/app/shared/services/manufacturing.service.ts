import { Injectable } from '@angular/core';
import { SettingsService } from './settings.service';
import { MATRIX_PRODUCTS, nextProdCol } from '../constants/products';

export interface ManufacturingInput {
  stockMap: Record<string, number>;
  activeOrderProductTotals: Record<string, number>;
  productTotals: Record<string, number>;
  weekPredictionTotals: Record<string, number>;
  allPredictionTotals: Record<string, number>;
  activeView: 'day' | 'week' | 'month';
}

export interface ManufacturingRecommendation {
  name: string;
  stock: number;
  totalDemand: number;
  remaining: number;
  toManufacture: number;
  timeMinutes: number;
}

/** All products considered for manufacturing scheduling (including roasts which
 *  are filtered out automatically when they have no timing config). */
const ALL_PRODUCTS = [
  'Light Roast', 'Medium Roast', 'Dark Roast',
  'Medium Roast Coffee (Whole)', 'Dark Roast Coffee (Whole)', 'Qishr',
  'Sunrise Socotra', 'Mount Haraz', 'Gate of Yemen', 'Queen Sheeba',
  'Cinnamon (Ground)', 'Cloves (Whole)', 'Cardamom (Ground)', 'Ginger (Ground)',
  'Juban Mix', 'Radaa Mix', 'Marib Mix', 'Sanaa Mix',
  'Ancient Marib', "Old City Sana'a", 'Valley Juban',
];

/** Maps product display name → prediction slug (next_prod_*). */
const PRODUCT_SLUG_MAP: Record<string, string> = Object.fromEntries(
  MATRIX_PRODUCTS.map(p => [p.displayName, nextProdCol(p)])
);

@Injectable({ providedIn: 'root' })
export class ManufacturingService {

  private readonly multipleOf5Products = new Set([
    'Cinnamon (Ground)', 'Cloves (Whole)', 'Ginger (Ground)',
  ]);

  private readonly multipleOf10Products = new Set([
    'Dark Roast Coffee (Whole)', 'Qishr',
    'Juban Mix', 'Radaa Mix', 'Marib Mix', 'Sanaa Mix', 'Cardamom (Ground)',
  ]);

  private readonly multipleOf16Products = new Set([
    'Sunrise Socotra', 'Gate of Yemen', 'Mount Haraz', 'Queen Sheeba',
    'Ancient Marib', "Old City Sana'a", 'Valley Juban',
  ]);

  constructor(private settingsService: SettingsService) {}

  // ── Public API ──────────────────────────────────────────────────

  /** Available manufacturing minutes for the given view period.
   *  Week = dailyHours × 5; Month = weeklyHours × 4. */
  viewCapacityMinutes(activeView: 'day' | 'week' | 'month'): number {
    const { dailyHours } = this.settingsService.current.manufacturing.capacity;
    const weeklyHours  = dailyHours * 5;
    const monthlyHours = weeklyHours * 4;
    switch (activeView) {
      case 'day':   return dailyHours   * 60;
      case 'week':  return weeklyHours  * 60;
      case 'month': return monthlyHours * 60;
    }
  }

  /** Format minutes as a human-readable string, e.g. "2h 30m". */
  formatMfgTime(min: number): string {
    if (min <= 0) return '-';
    const h = Math.floor(min / 60);
    const m = min % 60;
    if (h === 0) return `${m}m`;
    if (m === 0) return `${h}h`;
    return `${h}h ${m}m`;
  }

  /** Run the two-pass manufacturing scheduling algorithm and return
   *  the ordered recommendation list with its total time. */
  compute(input: ManufacturingInput): { recommendations: ManufacturingRecommendation[]; totalMinutes: number } {
    const { stockMap, activeOrderProductTotals, activeView } = input;
    const settings  = this.settingsService.current.manufacturing;
    const bufferMinutes = settings.capacity.bufferMinutes;
    const totalBudget   = this.viewCapacityMinutes(activeView);
    const viewDays      = this.viewDays(activeView);

    // ── Build candidates ──────────────────────────────────────────
    const candidates = ALL_PRODUCTS
      .map(name => {
        const stock       = (stockMap[name] ?? 0) - (activeOrderProductTotals[name] ?? 0);
        const totalDemand = this.viewScopedDemand(name, input);
        const remaining   = stock - totalDemand;
        const threshold   = settings.timings[name] ? (this.settingsService.current.stock.thresholds[name] ?? 0) : 0;
        const rawQty      = Math.max(0, threshold - remaining);
        const dailyCap    = settings.dailyCaps[name];
        const cappedQty   = (dailyCap !== undefined && dailyCap !== null)
          ? Math.min(rawQty, dailyCap * viewDays)
          : rawQty;
        const multiplier  = settings.maxBatchMultiplier ?? 2;
        const maxQty      = settings.timings[name] ? settings.timings[name].bagBatchSize * multiplier : Infinity;
        const toManufacture = this.roundManufactureQty(name, Math.min(cappedQty, maxQty));
        return {
          name,
          stock,
          totalDemand,
          remaining,
          toManufacture,
          timeMinutes: this.itemMfgMinutes(name, toManufacture),
        };
      })
      .filter(item => {
        if (item.toManufacture <= 0) return false;
        if (settings.excluded.includes(item.name)) return false;
        const cov  = this.coverage(item.name, stockMap, activeOrderProductTotals);
        return cov === null || cov < settings.coverage.exclusionThreshold;
      });

    // ── Sort (phase 1 = below coverage threshold, phase 2 = above) ─
    const p1Threshold = settings.coverage.phase1Threshold;

    const sortPhase1 = (a: typeof candidates[0], b: typeof candidates[0]) => {
      const covA = this.coverage(a.name, stockMap, activeOrderProductTotals) ?? 0;
      const covB = this.coverage(b.name, stockMap, activeOrderProductTotals) ?? 0;
      if ((covA < 0) !== (covB < 0)) return covA < 0 ? -1 : 1;
      return b.totalDemand - a.totalDemand;
    };

    const phase1 = candidates
      .filter(i => { const c = this.coverage(i.name, stockMap, activeOrderProductTotals); return c === null || c < p1Threshold; })
      .sort(sortPhase1);
    const phase2 = candidates
      .filter(i => { const c = this.coverage(i.name, stockMap, activeOrderProductTotals); return c !== null && c >= p1Threshold; })
      .sort((a, b) => b.totalDemand - a.totalDemand);

    const sorted = [...phase1, ...phase2];
    const n = sorted.length;

    const roastRequirements = settings.roastRequirements ?? {};
    const roastBudget: Record<string, number> = {
      'Light Roast':  stockMap['Light Roast']  ?? 0,
      'Medium Roast': stockMap['Medium Roast'] ?? 0,
      'Dark Roast':   stockMap['Dark Roast']   ?? 0,
    };

    // ── Pass 1: fair-share allocation ─────────────────────────────
    const fairShareMinutes = Math.max(1, Math.floor(totalBudget / Math.max(n, 1)));
    const result: typeof sorted = [];
    let budget = totalBudget;
    const scheduledQty = new Map<string, number>();

    for (const item of sorted) {
      if (budget <= 0) break;
      const bufCost     = result.length > 0 ? bufferMinutes : 0;
      const timeForItem = Math.min(budget - bufCost, fairShareMinutes);
      if (timeForItem <= 0) continue;

      let toMfg     = item.toManufacture;
      const req1    = roastRequirements[item.name];
      if (req1 && req1.lbsPerUnit > 0) {
        const maxByRoast = Math.floor(roastBudget[req1.roast] / req1.lbsPerUnit);
        toMfg = Math.min(toMfg, this.roundDownManufactureQty(item.name, maxByRoast));
      }
      if (toMfg <= 0) continue;

      const cappedQty  = this.roundDownManufactureQty(item.name, Math.min(toMfg, this.calcMaxMfgQtyInTime(item.name, timeForItem)));
      if (cappedQty <= 0) continue;

      const cappedTime = this.itemMfgMinutes(item.name, cappedQty);
      result.push({ ...item, toManufacture: cappedQty, timeMinutes: cappedTime });
      budget -= bufCost + cappedTime;
      scheduledQty.set(item.name, cappedQty);
      if (req1) roastBudget[req1.roast] -= cappedQty * req1.lbsPerUnit;
    }

    // ── Pass 2: fill remaining budget with unmet demand ───────────
    for (const item of sorted) {
      if (budget <= 0) break;
      const alreadyScheduled = scheduledQty.get(item.name) ?? 0;
      const moreNeeded       = item.toManufacture - alreadyScheduled;
      if (moreNeeded <= 0) continue;

      const existingIdx = result.findIndex(r => r.name === item.name);
      const isNew       = existingIdx < 0;
      const bufCost     = isNew && result.length > 0 ? bufferMinutes : 0;
      const timeAvail   = budget - bufCost;
      if (timeAvail <= 0) continue;

      let additionalQty = moreNeeded;
      const req2        = roastRequirements[item.name];
      if (req2 && req2.lbsPerUnit > 0) {
        const maxByRoast = Math.floor(roastBudget[req2.roast] / req2.lbsPerUnit);
        additionalQty = Math.min(additionalQty, this.roundDownManufactureQty(item.name, maxByRoast));
      }
      if (additionalQty <= 0) continue;

      const additionalTime = this.itemMfgMinutes(item.name, additionalQty);
      const finalQty = additionalTime <= timeAvail
        ? additionalQty
        : this.roundDownManufactureQty(item.name, Math.min(this.calcMaxMfgQtyInTime(item.name, timeAvail), additionalQty));
      if (finalQty <= 0) continue;

      const finalTime = this.itemMfgMinutes(item.name, finalQty);
      if (isNew) {
        result.push({ ...item, toManufacture: finalQty, timeMinutes: finalTime });
        budget -= bufCost + finalTime;
      } else {
        const prevTime    = result[existingIdx].timeMinutes;
        const combinedQty = result[existingIdx].toManufacture + finalQty;
        const combinedTime = this.itemMfgMinutes(item.name, combinedQty);
        result[existingIdx] = { ...result[existingIdx], toManufacture: combinedQty, timeMinutes: combinedTime };
        budget -= combinedTime - prevTime;
      }
      scheduledQty.set(item.name, alreadyScheduled + finalQty);
      if (req2) roastBudget[req2.roast] -= finalQty * req2.lbsPerUnit;
    }

    const totalMinutes = result.length === 0
      ? 0
      : result.reduce((acc, i) => acc + i.timeMinutes, 0)
          + Math.max(0, result.length - 1) * bufferMinutes;

    return { recommendations: result, totalMinutes };
  }

  // ── Private helpers ─────────────────────────────────────────────

  private viewDays(activeView: 'day' | 'week' | 'month'): number {
    switch (activeView) {
      case 'day':   return 1;
      case 'week':  return 5;
      case 'month': return 20;
    }
  }

  private viewScopedDemand(name: string, input: ManufacturingInput): number {
    const slug = PRODUCT_SLUG_MAP[name];
    if (!slug) return 0;
    switch (input.activeView) {
      case 'day':   return input.productTotals[slug]        ?? 0;
      case 'week':  return input.weekPredictionTotals[slug] ?? 0;
      case 'month': return input.allPredictionTotals[slug]  ?? 0;
    }
  }

  private coverage(
    name: string,
    stockMap: Record<string, number>,
    activeOrderProductTotals: Record<string, number>,
  ): number | null {
    const threshold = this.settingsService.current.stock.thresholds[name] ?? 0;
    if (!threshold) return null;
    const effectiveStock = (stockMap[name] ?? 0) - (activeOrderProductTotals[name] ?? 0);
    return (effectiveStock - threshold) / threshold;
  }

  private roundManufactureQty(name: string, qty: number): number {
    if (qty <= 0) return 0;
    if (this.multipleOf16Products.has(name)) return Math.max(32, Math.ceil(qty / 16) * 16);
    if (this.multipleOf10Products.has(name)) return Math.ceil(qty / 10) * 10;
    if (this.multipleOf5Products.has(name))  return Math.ceil(qty / 5)  * 5;
    return qty;
  }

  private roundDownManufactureQty(name: string, qty: number): number {
    if (qty <= 0) return 0;
    if (this.multipleOf16Products.has(name)) {
      const f = Math.floor(qty / 16) * 16;
      return f >= 32 ? f : 0;
    }
    if (this.multipleOf10Products.has(name)) return Math.floor(qty / 10) * 10;
    if (this.multipleOf5Products.has(name))  return Math.floor(qty / 5)  * 5;
    return qty;
  }

  private calcMaxMfgQtyInTime(name: string, availableMinutes: number): number {
    const cfg = this.settingsService.current.manufacturing.timings[name];
    if (!cfg) return 0;
    const step = this.multipleOf16Products.has(name) ? 16
               : this.multipleOf10Products.has(name) ? 10
               : this.multipleOf5Products.has(name)  ? 5
               : 1;
    let maxQty = 0;
    for (let qty = step; qty <= 10000; qty += step) {
      const prepBatches = cfg.prepPerBatch > 0 ? Math.ceil(qty / cfg.prepBatchSize) : 0;
      const bagBatches  = cfg.bagPerBatch  > 0 ? Math.ceil(qty / cfg.bagBatchSize)  : 0;
      if (prepBatches * cfg.prepPerBatch + bagBatches * cfg.bagPerBatch <= availableMinutes) {
        maxQty = qty;
      } else {
        break;
      }
    }
    return maxQty;
  }

  private itemMfgMinutes(name: string, qty: number): number {
    const cfg = this.settingsService.current.manufacturing.timings[name];
    if (!cfg || qty <= 0) return 0;
    const prepBatches = cfg.prepPerBatch > 0 ? Math.ceil(qty / cfg.prepBatchSize) : 0;
    const bagBatches  = cfg.bagPerBatch  > 0 ? Math.ceil(qty / cfg.bagBatchSize)  : 0;
    return prepBatches * cfg.prepPerBatch + bagBatches * cfg.bagPerBatch;
  }
}
