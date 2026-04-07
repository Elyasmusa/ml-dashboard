/**
 * Single source of truth for the 18 products tracked across the dashboard,
 * order matrix, and product matrix.
 *
 * `slug` mirrors the Python _slug() function output:
 *   re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
 *
 * Backend: MATRIX_PRODUCT_ALLOWLIST in product_config.py must match these names.
 */

export interface MatrixProduct {
  displayName: string;
  /** Bare slug — used to build prod_ and next_prod_ column names. */
  slug: string;
}

export const MATRIX_PRODUCTS: MatrixProduct[] = [
  { displayName: 'Medium Roast Coffee (Whole)', slug: 'medium_roast_coffee_whole' },
  { displayName: 'Dark Roast Coffee (Whole)',   slug: 'dark_roast_coffee_whole'   },
  { displayName: 'Qishr',                       slug: 'qishr'                     },
  { displayName: 'Sunrise Socotra',             slug: 'sunrise_socotra'           },
  { displayName: 'Mount Haraz',                 slug: 'mount_haraz'               },
  { displayName: 'Gate of Yemen',               slug: 'gate_of_yemen'             },
  { displayName: 'Queen Sheeba',                slug: 'queen_sheeba'              },
  { displayName: 'Cinnamon (Ground)',            slug: 'cinnamon_ground'           },
  { displayName: 'Cloves (Whole)',               slug: 'cloves_whole'              },
  { displayName: 'Cardamom (Ground)',            slug: 'cardamom_ground'           },
  { displayName: 'Ginger (Ground)',              slug: 'ginger_ground'             },
  { displayName: 'Juban Mix',                   slug: 'juban_mix'                 },
  { displayName: 'Radaa Mix',                   slug: 'radaa_mix'                 },
  { displayName: 'Marib Mix',                   slug: 'marib_mix'                 },
  { displayName: 'Sanaa Mix',                   slug: 'sanaa_mix'                 },
  { displayName: 'Ancient Marib',               slug: 'ancient_marib'             },
  { displayName: "Old City Sana'a",             slug: 'old_city_sana_a'           },
  { displayName: 'Valley Juban',                slug: 'valley_juban'              },
];

/** Column name for the current-order quantity of this product. */
export function prodCol(p: MatrixProduct): string {
  return `prod_${p.slug}`;
}

/** Column name for the next-order quantity of this product. */
export function nextProdCol(p: MatrixProduct): string {
  return `next_prod_${p.slug}`;
}
