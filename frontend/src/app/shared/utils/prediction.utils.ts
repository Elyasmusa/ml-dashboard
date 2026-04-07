import { CombinedPredictionRow } from '../models/training.model';

/** Timezone used for all date formatting across the dashboard. */
const TZ = 'America/New_York';

/**
 * Format a city slug (underscore-separated) as a title-cased display name.
 *
 * @example formatCity('new_york') // → 'New York'
 */
export function formatCity(slug: string): string {
  if (!slug) return '-';
  return slug.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Format an ISO date string as `MM/DD/YYYY` in the Eastern timezone.
 * Uses noon local time to avoid DST boundary edge cases.
 *
 * @example formatDate('2026-03-15') // → '03/15/2026'
 */
export function formatDate(date?: string): string {
  if (!date) return '-';
  const d = new Date(date + 'T12:00:00');
  if (isNaN(d.getTime())) return date;
  return d.toLocaleDateString('en-US', {
    timeZone: TZ,
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
  });
}

/**
 * Extract and sort the non-zero predicted product quantities from a prediction
 * row into `{ name, qty }` pairs ordered by descending quantity.
 *
 * Strips the `next_prod_` prefix and converts underscore slugs to title case.
 */
export function buildProductEntries(
  row: CombinedPredictionRow,
): { name: string; qty: number }[] {
  return Object.entries(row.predictedProducts || {})
    .filter(([, qty]) => qty > 0)
    .map(([slug, qty]) => ({
      name: slug
        .replace(/^next_prod_/, '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase()),
      qty: Math.round(qty),
    }))
    .sort((a, b) => b.qty - a.qty);
}
