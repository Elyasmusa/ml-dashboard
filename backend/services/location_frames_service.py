from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from utils import safe_value as _safe_value
from services.cache_service import inflow_cache, _CacheEntry, _make_cache_key
from services.product_config import (
    EXCLUDED_PRODUCT_NAMES,
    EXCLUDED_PRODUCT_SKUS,
    get_base_product_name,
    get_product_scale,
)

logger = logging.getLogger(__name__)

_PARENT_ENDPOINT = "sales-orders"
_DEDUP_DAYS = 3

# Orders containing any of these products are excluded entirely
_EXCLUDED_PRODUCTS: set[str] = {
    "Puqpress Q2 Auto Tamper - 58mm",
    "Mazzer Robur S Electronic Grinder",
    "La Marzocco - Classic Linea S (AV) - 3 Group",
}

# Dedicated folder for all per-city Parquet files
_LOCATION_DIR: Path = settings.cache_dir / "franchise_location_orders"

# In-memory store (city_slug → flat DataFrame)
_city_store: dict[str, pd.DataFrame] = {}
_cities_index: list[dict[str, str]] = []


# ── Helpers ──────────────────────────────────────────────────────────

def _extract_city(row: dict[str, Any]) -> str | None:
    """Extract city from shippingAddress, falling back to billingAddress."""
    for addr_key in ("shippingAddress", "billingAddress"):
        addr = row.get(addr_key)
        if addr is None:
            continue
        addr = _safe_value(addr)
        if isinstance(addr, dict):
            city = addr.get("city")
            if city and isinstance(city, str) and city.strip():
                return city.strip()
    return None


def _city_slug(city: str) -> str:
    """Normalise a city name to a URL-safe / filename-safe slug."""
    return city.lower().replace(" ", "_")


def _slug_to_filename(slug: str) -> str:
    """Convert a slug to a safe filename (without extension)."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', slug)


def _dedup_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Greedy 3-day dedup: keep first order, skip any within 3 days."""
    if df.empty:
        return df

    df = df.copy()
    df["_parsed_date"] = pd.to_datetime(df["orderDate"], errors="coerce", utc=True)
    df = df.sort_values("_parsed_date").reset_index(drop=True)

    kept_mask: list[bool] = []
    last_kept_date = None

    for _, row in df.iterrows():
        order_date = row["_parsed_date"]
        if pd.isna(order_date):
            kept_mask.append(True)
            continue
        if last_kept_date is None or (order_date - last_kept_date).days >= _DEDUP_DAYS:
            kept_mask.append(True)
            last_kept_date = order_date
        else:
            kept_mask.append(False)

    return df.loc[kept_mask].drop(columns=["_parsed_date"])


def _has_excluded_product(row: dict[str, Any]) -> bool:
    """Return True if the order contains any excluded product."""
    lines = row.get("lines")
    if lines is not None:
        lines = _safe_value(lines)
    if not lines or not isinstance(lines, list):
        return False
    for line in lines:
        line = _safe_value(line)
        if not isinstance(line, dict):
            continue
        product = _safe_value(line.get("product") or {})
        if isinstance(product, dict):
            name = product.get("name")
            if name and name in _EXCLUDED_PRODUCTS:
                return True
    return False


def _flatten_order_lines(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a single order row into one dict per cleaned product line.

    Products are excluded, renamed via overrides, and scaled. Lines that
    map to the same canonical name are merged (quantities summed).
    """
    contact = row.get("contactName") or ""
    if not contact:
        cust = _safe_value(row.get("customer") or {})
        if isinstance(cust, dict):
            contact = cust.get("name") or cust.get("contactName") or ""
        elif isinstance(cust, str):
            contact = cust
    base = {
        "orderNumber": row.get("orderNumber"),
        "contactName": contact,
        "orderDate": row.get("orderDate"),
        "orderTotal": row.get("total"),
    }

    lines = row.get("lines")
    if lines is not None:
        lines = _safe_value(lines)

    if not lines or not isinstance(lines, list):
        return [{**base, "productName": None, "productSku": None,
                 "unitPrice": None, "quantity": None, "lineTotal": None}]

    # First pass: collect lines grouped by canonical product name
    grouped: dict[str, dict[str, Any]] = {}
    for line in lines:
        line = _safe_value(line)
        if not isinstance(line, dict):
            continue

        product = _safe_value(line.get("product") or {})
        if not isinstance(product, dict):
            product = {}

        product_name = product.get("name")
        if not product_name:
            continue
        name_lower = product_name.strip().lower()
        if name_lower in EXCLUDED_PRODUCT_NAMES:
            continue
        if any(
            name_lower[:name_lower.index(sep)].strip() in EXCLUDED_PRODUCT_NAMES
            for sep in (" - ", " | ") if sep in name_lower
        ):
            continue
        product_sku = product.get("sku")
        if product_sku and product_sku.strip() in EXCLUDED_PRODUCT_SKUS:
            continue

        canonical = get_base_product_name(product_name)
        scale = get_product_scale(product_name)

        qty_obj = _safe_value(line.get("quantity") or {})
        if not isinstance(qty_obj, dict):
            qty_obj = {}
        raw_qty = qty_obj.get("uomQuantity") or qty_obj.get("standardQuantity")
        try:
            qty = float(raw_qty) * scale if raw_qty is not None else 0.0
        except (ValueError, TypeError):
            qty = 0.0

        raw_total = line.get("subTotal")
        try:
            line_total = float(raw_total) if raw_total is not None else 0.0
        except (ValueError, TypeError):
            line_total = 0.0

        if canonical in grouped:
            grouped[canonical]["quantity"] += qty
            grouped[canonical]["lineTotal"] += line_total
        else:
            grouped[canonical] = {
                **base,
                "productName": canonical,
                "productSku": product_sku,
                "unitPrice": line.get("unitPrice"),
                "quantity": qty,
                "lineTotal": line_total,
            }

    rows = list(grouped.values())
    return rows if rows else [{**base, "productName": None, "productSku": None,
                                "unitPrice": None, "quantity": None, "lineTotal": None}]


# ── Disk I/O ─────────────────────────────────────────────────────────

_FLAT_COLUMNS = [
    "orderNumber", "contactName", "orderDate", "orderTotal",
    "productName", "productSku", "unitPrice", "quantity", "lineTotal",
]


def _save_city(slug: str, df: pd.DataFrame) -> None:
    """Save a per-city DataFrame to a Parquet file in the dedicated folder."""
    try:
        path = _LOCATION_DIR / f"{_slug_to_filename(slug)}.parquet"
        df.to_parquet(path, index=False)
    except Exception:
        logger.exception("Failed to save location frame for %s", slug)


def _remove_city_file(slug: str) -> None:
    """Remove a per-city Parquet file."""
    path = _LOCATION_DIR / f"{_slug_to_filename(slug)}.parquet"
    try:
        path.unlink(missing_ok=True)
    except Exception:
        logger.exception("Failed to remove %s", path)


def _save_cities_index(index: list[dict[str, str]]) -> None:
    """Save the cities index as a JSON file."""
    try:
        path = _LOCATION_DIR / "cities_index.json"
        path.write_text(json.dumps(index), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save cities index")


def _load_from_disk() -> None:
    """Load all per-city Parquet files from the dedicated folder on startup."""
    global _cities_index

    if not _LOCATION_DIR.exists():
        return

    # Load cities index
    index_path = _LOCATION_DIR / "cities_index.json"
    if index_path.exists():
        try:
            _cities_index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load cities index")

    # Load per-city Parquet files
    loaded = 0
    for parquet_path in _LOCATION_DIR.glob("*.parquet"):
        try:
            slug = parquet_path.stem
            df = pd.read_parquet(parquet_path)
            _city_store[slug] = df
            loaded += 1
        except Exception:
            logger.exception("Failed to load location frame from %s", parquet_path)

    if loaded:
        logger.info("Loaded %d location frames from disk", loaded)


# ── Public API (used by router) ──────────────────────────────────────

def get_cities() -> list[dict[str, str]] | None:
    """Return the cities index, or None if not yet built."""
    return _cities_index if _cities_index else None


def get_city_orders(city_slug: str) -> dict | None:
    """Return orders for a city in InflowListResponse shape, or None."""
    filename = _slug_to_filename(city_slug)
    df = _city_store.get(filename)
    if df is None:
        return None
    records = df.to_dict(orient="records")
    # Scrub NaN values
    clean = []
    for row in records:
        clean.append({k: (None if pd.isna(v) else v) if not isinstance(v, (dict, list)) else v
                       for k, v in row.items()})
    return {
        "data": clean,
        "hasMore": False,
        "totalCount": len(clean),
    }


# ── Core rebuild callback ────────────────────────────────────────────

def _rebuild_location_frames(endpoint: str, entry: _CacheEntry) -> None:
    """Split franchise orders by city, dedup, flatten lines, save to folder."""
    global _cities_index

    df = entry.df

    # Only process detailed fetches that include line items
    if df.empty or "lines" not in df.columns:
        logger.debug("location_frames: no 'lines' column, skipping (plain fetch)")
        return
    if "orderNumber" not in df.columns:
        logger.warning("location_frames: no orderNumber column, skipping")
        return

    # Filter for franchise store orders only
    franchise_df = df[df["orderNumber"].str.contains("SO-", na=False)].copy()
    if franchise_df.empty:
        logger.info("location_frames: no franchise orders in detailed fetch")
        return

    # Group by city
    records = franchise_df.to_dict(orient="records")
    cities_map: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        city = _extract_city(row)
        if city:
            slug = _city_slug(city)
            cities_map.setdefault(slug, []).append(row)

    # Build and store per-city DataFrames
    kept_slugs: list[str] = []
    for city_slug, city_orders in cities_map.items():
        filename = _slug_to_filename(city_slug)

        # Remove orders containing excluded products
        city_orders = [r for r in city_orders if not _has_excluded_product(r)]
        if not city_orders:
            continue

        kept_slugs.append(city_slug)

        # Dedup
        city_df = pd.DataFrame(city_orders)
        city_df = _dedup_orders(city_df)

        # Flatten line items
        flat_rows: list[dict[str, Any]] = []
        for row in city_df.to_dict(orient="records"):
            flat_rows.extend(_flatten_order_lines(row))

        flat_df = pd.DataFrame(flat_rows, columns=_FLAT_COLUMNS) if flat_rows else pd.DataFrame(columns=_FLAT_COLUMNS)

        _city_store[filename] = flat_df
        _save_city(city_slug, flat_df)

    # Clean up stale city files (cities removed or fully excluded)
    kept_filenames = {_slug_to_filename(slug) for slug in kept_slugs}
    stale_filenames = set(_city_store.keys()) - kept_filenames
    for stale in stale_filenames:
        del _city_store[stale]
        _remove_city_file(stale)

    # Build and save cities index (only cities that have orders after filtering)
    _cities_index = [
        {"citySlug": slug, "displayName": slug.replace("_", " ").title()}
        for slug in sorted(kept_slugs)
    ]
    _save_cities_index(_cities_index)

    logger.info(
        "location_frames: built %d city frames in %s",
        len(kept_slugs),
        _LOCATION_DIR,
    )


# ── Initialisation ───────────────────────────────────────────────────

def init_location_frames() -> None:
    """Register the callback and rebuild from existing cache if available."""
    _LOCATION_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing files from disk first
    _load_from_disk()

    # Register callback for future updates
    inflow_cache.register_on_update(
        _PARENT_ENDPOINT,
        _rebuild_location_frames,
    )

    # If the detailed sales-orders cache was loaded from disk, rebuild now
    detailed_key = _make_cache_key(
        _PARENT_ENDPOINT,
        {"include": "lines.product,customer,location"},
    )
    entry = inflow_cache.get_entry(detailed_key)
    if entry is not None:
        _rebuild_location_frames(_PARENT_ENDPOINT, entry)


# Auto-initialise when this module is first imported
init_location_frames()
