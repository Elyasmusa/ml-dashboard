"""Shared product configuration for exclusions, name overrides, and scaling.

This is the single source of truth for the backend. Both order_matrix_service
and location_frames_service import from here so they can never drift apart.
The frontend mirrors these lists in inflow.model.ts and
product-inventory.component.ts.
"""
from __future__ import annotations


# ── Categories to exclude ────────────────────────────────────────────

EXCLUDED_CATEGORIES: set[str] = {
    "inactive", "bags", "storage bins", "tools", "merchandise",
    "raw material", "packaging", "equipment", "roasts", "services",
    "preblends", "pastries", "supplies", "warehouse supplies",
}

# ── Product names to exclude (lowercase) ─────────────────────────────

EXCLUDED_PRODUCT_NAMES: set[str] = {
    "1883 apple syrup",
    "1883 blackberry syrup",
    "1883 frappe mix syrup",
    "1883 peppermint syrup",
    "1883 standard mixed case",
    "4oz single walled hot cups",
    "allspice (ground)",
    "almonds",
    "almonds (fruits and nuts)",
    "almonds(fruits and nuts)",
    "barair",
    "bayad raisins",
    "chocoline pistachio sauce",
    "cold cups deactivate",
    "dark roast coffee (ground) | 5 lbs bag",
    "date syrup",
    "evaporated milk",
    "freeze dried lemons",
    "gate of yemen | dark roast (ground)",
    "gate of yemen whol",
    "ghirardelli sauce pump",
    "ghirardelli sauce rack",
    "ghirardelli white chocolate sauce",
    "cloves (ground)",
    "ground",
    "ground (labels)",
    "ground(labels)",
    "whole",
    "whole (labels)",
    "whole(labels)",
    "light roast coffee (ground) | 5 lbs bag",
    "light roast coffee (whole) | 5 lbs bag",
    "macadamia milk",
    "macadamia nut",
    "macadmia nut",
    "m3e",
    "medium roast coffee (ground) | 5 lbs bag",
    "mediuum",
    "mount haraz | medium roast (ground)",
    "monin flavoring syrup pump",
    "monin pumpkin spice syrup (bottle)",
    "old",
    "pistachio topping (6 x 900g bottles)",
    "port of aden | special blend (fine)",
    "pumpkin powder (ground)",
    "pumpkin spice mix",
    "qamaria mix",
    "queen sheeba bundle | qishr (whole)",
    "razqi raisins",
    "shipping discount",
    "squarespacediscount",
    "sunrise socotra | light roast (ground)",
    "white chocolate sauce",
    "tea",
}

# ── Product SKUs to exclude ──────────────────────────────────────────

EXCLUDED_PRODUCT_SKUS: set[str] = {
    "IF5127635",
    "IF5127634",
    "IF5127554",
    "IF5127797",
    "IF5127553",
    "IF5127552",
}

# ── Name overrides (lowercase key → canonical display name) ──────────

PRODUCT_NAME_OVERRIDES: dict[str, str] = {
    "ghirardelli caramel sauce": "Caramel Sauce",
    "caramel sauce": "Caramel Sauce",
    "ghirardelli chocolate sauce": "Chocolate Sauce",
    "chocolate sauce": "Chocolate Sauce",
    "mango smoothie": "Mango Smoothie",
    "monin mango smoothie": "Mango Smoothie",
    "strawberry smoothie": "Strawberry Smoothie",
    "monin strawberry smoothie": "Strawberry Smoothie",
    "ceremonial matcha": "Ceremonial Matcha",
    "ceremonial matcha tin": "Ceremonial Matcha",
    "al-kbous black tea (bag)": "Al-Kbous Black Tea",
    "al-kbous black tea": "Al-Kbous Black Tea",
    "hot lids": "Hot Lids",
    "hot white sipper lids": "Hot Lids",
    "white hot sipper lids": "Hot Lids",
    "white sipper lids": "Hot Lids",
    "white universal pp hot cup lids": "Hot Lids",
    "green hot sipper lids": "Hot Lids",
    "black sipper lids": "Hot Lids",
    "16oz white sipper lids": "Hot Lids",
    "white sipper lids - fredom": "Hot Lids",
    "16oz plastic lids": "Cold Lids",
    "karat 16oz clear cold lids": "Cold Lids",
    "pet flat lids": "Cold Lids",
    "16oz pet cold cups": "16oz Cold Cups",
    "16oz pet plastic cups": "16oz Cold Cups",
    "karat 16oz pet cold cups": "16oz Cold Cups",
    "6oz white sipper lids": "6oz White Sipper Lids",
    "6oz white sipper lids (2000)": "6oz White Sipper Lids",
    "6oz white sipper lids (2,000 pcs)": "6oz White Sipper Lids",
}

# ── Quantity scaling (lowercase key → multiplier) ────────────────────

PRODUCT_SCALING: dict[str, float] = {
    # Smoothies: 1:1 ratio (both map to same name, same scale)
    "mango smoothie": 1.0,
    "monin mango smoothie": 1.0,
    "strawberry smoothie": 1.0,
    "monin strawberry smoothie": 1.0,
    # Ceremonial Matcha: tin = 2.64555 normal units
    "ceremonial matcha": 1.0,
    "ceremonial matcha tin": 2.64555,
    # Mixes: base = 3 lbs bag
    "marib mix | 3 lbs bag": 1.0,
    "marib mix | 5 lbs bag": 5 / 3,
    "sanaa mix | 3 lbs bag": 1.0,
    "sanaa mix | 5 lbs bag": 5 / 3,
    "radaa mix | 3 lbs bag": 1.0,
    "radaa mix | 5 lbs bag": 5 / 3,
    "juban mix | 3 lbs bag": 1.0,
    "juban mix | 5 lbs bag": 5 / 3,
    # 6oz White Sipper Lids: base = 2000 pc
    "6oz white sipper lids": 5000 / 2000,  # 2.5
    "6oz white sipper lids (2000)": 1.0,
    "6oz white sipper lids (2,000 pcs)": 1.0,
    # Al-Kbous Black Tea: base = 2 bags = 1 order
    "al-kbous black tea (bag)": 0.5,   # 1 bag  / 2 bags
    "al-kbous black tea (2 bags)": 1.0, # 2 bags / 2 bags
    "al-kbous black tea (3 bags)": 1.5, # 3 bags / 2 bags
    "al-kbous black tea": 2.0,         # 4 bags / 2 bags
}


# ── Helper functions ─────────────────────────────────────────────────

def get_base_product_name(name: str) -> str:
    """Return the canonical product name after applying overrides."""
    override = PRODUCT_NAME_OVERRIDES.get(name.strip().lower())
    if override:
        return override
    for sep in (" - ", " | "):
        idx = name.find(sep)
        if idx > 0:
            base = name[:idx].strip()
            base_override = PRODUCT_NAME_OVERRIDES.get(base.lower())
            if base_override:
                return base_override
            return base
    return name.strip()


def get_product_scale(name: str) -> float:
    """Return the scaling factor for a product variant."""
    return PRODUCT_SCALING.get(name.strip().lower(), 1.0)
