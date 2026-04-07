from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings, VARIANT_NAMES
from utils import safe_value as _safe_value, NA_COUNTRIES as _NA_COUNTRIES_SET
from services.cache_service import inflow_cache, _CacheEntry, _make_cache_key
from services.product_config import (
    EXCLUDED_CATEGORIES,
    EXCLUDED_PRODUCT_NAMES,
    EXCLUDED_PRODUCT_SKUS,
    get_base_product_name,
    get_product_scale,
)

logger = logging.getLogger(__name__)

_PARENT_ENDPOINT = "sales-orders"
_MATRIX_KEY = "franchise_order_matrix"
_LATEST_KEY = "latest_franchise_orders"

# Data variant combinations for model comparison
_VARIANT_NAMES = VARIANT_NAMES
def _MIN_ORDER_THRESHOLD() -> int:  # noqa: N802
    from services.settings_service import get as _get_settings
    return _get_settings().dataPipeline.minOrdersThreshold

# Dedicated folder for the matrix Parquet file
_MATRIX_DIR: Path = settings.cache_dir / "franchise_order_matrix"
_MATRIX_FILE = "matrix.parquet"
_MATRIX_META = "matrix.meta.json"

# Dedicated folder for the latest franchise orders (no next order date)
_LATEST_DIR: Path = settings.cache_dir / "latest_franchise_orders"
_LATEST_FILE = "latest.parquet"
_LATEST_META = "latest.meta.json"

_NA_COUNTRIES = _NA_COUNTRIES_SET

# Thresholds read from settings at pipeline execution time
def _MERGE_WINDOW_DAYS() -> int:  # noqa: N802
    from services.settings_service import get as _get_settings
    return _get_settings().dataPipeline.mergeWindowDays

def _DORMANT_THRESHOLD_DAYS() -> int:  # noqa: N802
    from services.settings_service import get as _get_settings
    return _get_settings().dataPipeline.dormantThresholdDays

# ── Module-level state for incremental updates ───────────────────────
# Populated after a full rebuild so incremental updates can avoid re-running
# the entire pipeline.  Naturally reset on server restart (full rebuild runs).
_order_data: list[dict[str, Any]] = []          # cleaned orders after merge/absorb/dormancy
_latest_per_location: dict[str, int] = {}       # citySlug → index in _order_data
_known_order_ids: set[str] = set()              # salesOrderId values already processed
_all_cities: set[str] = set()
_all_products: set[str] = set()
_city_groups_idx: dict[str, list[int]] = defaultdict(list)
_temporal_features: dict[int, dict[str, float]] = {}
_next_order_ts: list[pd.Timestamp | None] = []
_next_order_num: list[str | None] = []
_flat_rows: list[dict[str, Any]] = []           # all flat rows from last full rebuild
_state_ready: bool = False                       # True after first full rebuild completes

# Lock prevents a full rebuild and an incremental update from interleaving when
# the callback is triggered from multiple simultaneous cache updates.
_rebuild_lock = threading.Lock()

# Thread pool for Parquet I/O in the incremental update path.
# Moves blocking file operations off the calling thread so the GIL is released
# during I/O, keeping the event loop more responsive.
_parquet_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="parquet-io"
)


def _pq_read(path: Path) -> pd.DataFrame:
    """Read a Parquet file in a thread-pool worker."""
    return _parquet_pool.submit(pd.read_parquet, path).result()


def _pq_write(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet in a thread-pool worker."""
    _parquet_pool.submit(lambda: df.to_parquet(path, index=False)).result()


# ── Helpers ──────────────────────────────────────────────────────────

def _extract_address_field(row: dict[str, Any], field: str) -> str | None:
    """Extract a field from shippingAddress, falling back to billingAddress."""
    for addr_key in ("shippingAddress", "billingAddress"):
        addr = row.get(addr_key)
        if addr is None:
            continue
        addr = _safe_value(addr)
        if isinstance(addr, dict):
            val = addr.get(field)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
    return None


_CITY_NORMALIZATION: dict[str, str] = {
    "mississagua": "Mississauga",
}

# Franchise locations excluded from both the order matrix and product matrix.
# Checked as a case-insensitive prefix of the raw extracted location string so
# that "City, ST" variants are caught alongside bare city names.
_EXCLUDED_FRANCHISE_LOCATION_PREFIXES: tuple[str, ...] = (
    "windermere",
    "canton",
    "phoenix",
    "dmv catering",
    "dearborn (hashem",
)


def _is_excluded_franchise_location(location: str) -> bool:
    loc_lower = location.strip().lower()
    return any(loc_lower.startswith(prefix) for prefix in _EXCLUDED_FRANCHISE_LOCATION_PREFIXES)


def _extract_city(row: dict[str, Any]) -> str | None:
    city = _extract_address_field(row, "city")
    if city:
        normalized = _CITY_NORMALIZATION.get(city.strip().lower())
        if normalized:
            return normalized
    return city


def _extract_franchise_location(row: dict[str, Any]) -> str | None:
    """Extract franchise location from the customer name.

    Customer names follow the pattern "Qamaria - {Location}" or
    "Qamaria Coffee - {Location}".  Returns the location part (e.g.
    "Fremont, CA") or None if the pattern doesn't match.
    Falls back to shipping/billing city.
    """
    cust = _safe_value(row.get("customer") or {})
    if isinstance(cust, dict):
        name = cust.get("name") or ""
    elif isinstance(cust, str):
        name = cust
    else:
        name = ""

    if name:
        # Match "Qamaria - X" or "Qamaria Coffee - X"
        m = re.match(r"^qamaria(?:\s+coffee)?\s*-\s*(.+)", name.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Fall back to shipping/billing city
    return _extract_city(row)


def _is_north_america(row: dict[str, Any]) -> bool:
    country = _extract_address_field(row, "country")
    if country:
        # Normalize: strip periods and extra whitespace so "U.S." → "us"
        normalized = country.lower().replace(".", "").strip()
        return normalized in _NA_COUNTRIES
    # Country is empty — infer from state or postal code
    state = _extract_address_field(row, "state")
    if state and len(state) <= 4:
        # Short state code (e.g. OH, CA, NY, ON) — likely US/Canada
        return True
    postal = _extract_address_field(row, "postalCode")
    if postal and re.match(r'^\d{5}', postal):
        # US ZIP code pattern
        return True
    return False


def _slug(text: str) -> str:
    """Lowercase, replace spaces/special chars with underscores."""
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _parse_date(date_str: Any) -> pd.Timestamp | None:
    if not date_str:
        return None
    ts = pd.to_datetime(date_str, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts


def _get_category_name(cat: Any) -> str:
    cat = _safe_value(cat)
    if not cat:
        return ""
    if isinstance(cat, str):
        return cat
    if isinstance(cat, dict):
        return cat.get("name", "") or ""
    return ""


# ── Build excluded product names from products cache ─────────────────

def _build_excluded_product_names() -> set[str]:
    """Cross-reference the products cache to find product names in excluded categories."""
    excluded: set[str] = set()

    # Try the detailed products cache first, then the plain one
    for extra in ({"include": "inventoryLines,category"}, {"include": "category"}, None):
        key = _make_cache_key("products", extra)
        entry = inflow_cache.get_entry(key)
        if entry is not None and not entry.df.empty:
            for row in entry.df.to_dict(orient="records"):
                cat_name = _get_category_name(row.get("category"))
                if cat_name and cat_name.lower() in EXCLUDED_CATEGORIES:
                    name = row.get("name")
                    if name:
                        excluded.add(name)
            logger.info("Excluded %d products by category", len(excluded))
            return excluded

    logger.warning("Products cache not available; no category-based filtering applied")
    return excluded


def _get_products_page_names() -> set[str]:
    """Return the canonical product names visible on the /products page.

    Reads the products cache and applies the same category / name / SKU
    exclusions that the frontend uses, then normalises names through
    get_base_product_name().  The result is the authoritative column set
    for the product matrix — only products that appear on the /products
    page will become columns.

    Returns an empty set if the products cache is not yet populated
    (the caller should fall back to discovered-from-orders products).
    """
    for extra in (
        {"include": "inventoryLines,category,defaultPrice"},
        {"include": "inventoryLines,category"},
        {"include": "category"},
        None,
    ):
        key = _make_cache_key("products", extra)
        entry = inflow_cache.get_entry(key)
        if entry is not None and not entry.df.empty:
            break
    else:
        logger.warning(
            "_get_products_page_names: products cache not available; "
            "matrix will use products discovered from orders"
        )
        return set()

    names: set[str] = set()
    for row in entry.df.to_dict(orient="records"):
        cat_name = _get_category_name(row.get("category")).lower()
        if cat_name in EXCLUDED_CATEGORIES:
            continue

        raw_name = row.get("name")
        if not raw_name or not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        name_lower = name.lower()

        if name_lower in EXCLUDED_PRODUCT_NAMES:
            continue

        excluded_by_prefix = False
        for sep in (" - ", " | "):
            if sep in name_lower:
                prefix = name_lower[:name_lower.index(sep)].strip()
                if prefix in EXCLUDED_PRODUCT_NAMES:
                    excluded_by_prefix = True
                    break
        if excluded_by_prefix:
            continue

        sku = row.get("sku")
        if sku and isinstance(sku, str) and sku.strip() in EXCLUDED_PRODUCT_SKUS:
            continue

        names.add(get_base_product_name(name))

    logger.info(
        "_get_products_page_names: %d canonical product columns from products cache",
        len(names),
    )
    return names


# ── Disk I/O ─────────────────────────────────────────────────────────

def _save_matrix_to_disk(df: pd.DataFrame, total_count: int) -> None:
    """Save the matrix DataFrame to a dedicated Parquet file."""
    try:
        _MATRIX_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_MATRIX_DIR / _MATRIX_FILE, index=False)
        meta = {"total_count": total_count}
        (_MATRIX_DIR / _MATRIX_META).write_text(json.dumps(meta), encoding="utf-8")
        logger.info("Saved order matrix to %s (%d rows)", _MATRIX_DIR / _MATRIX_FILE, total_count)
    except Exception:
        logger.exception("Failed to save order matrix to disk")


def _load_from_disk() -> bool:
    """Load the matrix from the dedicated Parquet file on startup.

    Returns True if data was loaded into the in-memory cache.
    """
    parquet_path = _MATRIX_DIR / _MATRIX_FILE
    meta_path = _MATRIX_DIR / _MATRIX_META
    if not parquet_path.exists():
        return False
    try:
        df = pd.read_parquet(parquet_path)
        total_count = len(df)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            total_count = meta.get("total_count", total_count)
        inflow_cache.put(_MATRIX_KEY, df.to_dict(orient="records"), total_count)
        logger.info("Loaded order matrix from disk: %d rows", total_count)
        return True
    except Exception:
        logger.exception("Failed to load order matrix from disk")
        return False


# ── Disk I/O (latest franchise orders) ────────────────────────────────

def _save_latest_to_disk(df: pd.DataFrame, total_count: int) -> None:
    """Save the latest franchise orders DataFrame to a dedicated Parquet file."""
    try:
        _LATEST_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_LATEST_DIR / _LATEST_FILE, index=False)
        meta = {"total_count": total_count}
        (_LATEST_DIR / _LATEST_META).write_text(json.dumps(meta), encoding="utf-8")
        logger.info("Saved latest franchise orders to %s (%d rows)", _LATEST_DIR / _LATEST_FILE, total_count)
    except Exception:
        logger.exception("Failed to save latest franchise orders to disk")


def _load_latest_from_disk() -> bool:
    """Load latest franchise orders from the dedicated Parquet file on startup."""
    parquet_path = _LATEST_DIR / _LATEST_FILE
    meta_path = _LATEST_DIR / _LATEST_META
    if not parquet_path.exists():
        return False
    try:
        df = pd.read_parquet(parquet_path)
        total_count = len(df)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            total_count = meta.get("total_count", total_count)
        inflow_cache.put(_LATEST_KEY, df.to_dict(orient="records"), total_count)
        logger.info("Loaded latest franchise orders from disk: %d rows", total_count)
        return True
    except Exception:
        logger.exception("Failed to load latest franchise orders from disk")
        return False


# ── Order parsing (shared by full rebuild and incremental update) ────

def _parse_order_record(
    row: dict[str, Any],
    excluded_products: set[str],
) -> dict[str, Any] | None:
    """Parse a single raw sales-order record into structured order data.

    Returns None if the order should be skipped (no valid products, not
    franchise, not North America, etc.).
    """
    order_number = row.get("orderNumber")
    if not order_number or not str(order_number).startswith("SO-"):
        return None
    if not _is_north_america(row):
        return None

    raw_contact = row.get("contactName") or ""
    if not raw_contact:
        # Fall back to the nested customer object's name
        cust = _safe_value(row.get("customer") or {})
        if isinstance(cust, dict):
            raw_contact = cust.get("name") or cust.get("contactName") or ""
        elif isinstance(cust, str):
            raw_contact = cust
    contact_name = raw_contact if isinstance(raw_contact, str) else str(raw_contact)
    order_ts = _parse_date(row.get("orderDate"))
    city = _extract_franchise_location(row)
    if city and _is_excluded_franchise_location(city):
        return None
    city_s = _slug(city) if city else "unknown"

    lines = row.get("lines")
    if lines is not None:
        lines = _safe_value(lines)
    if not lines or not isinstance(lines, list):
        return None

    product_qtys: dict[str, float] = defaultdict(float)
    for line in lines:
        line = _safe_value(line)
        if not isinstance(line, dict):
            continue
        product = _safe_value(line.get("product") or {})
        if not isinstance(product, dict):
            continue
        product_name = product.get("name")
        if not product_name:
            continue
        if product_name in excluded_products:
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

        base_name = get_base_product_name(product_name)
        qty_obj = _safe_value(line.get("quantity") or {})
        if not isinstance(qty_obj, dict):
            qty_obj = {}
        qty = _to_float(qty_obj.get("uomQuantity") or qty_obj.get("standardQuantity"))
        scale = get_product_scale(product_name)
        product_qtys[base_name] += qty * scale

    if not product_qtys:
        return None

    return {
        "orderNumber": order_number,
        "contactName": contact_name,
        "orderTs": order_ts,
        "citySlug": city_s,
        "productQtys": dict(product_qtys),
        "salesOrderId": row.get("salesOrderId"),
    }


# ── Incremental update ──────────────────────────────────────────────

def _incremental_update(entry: _CacheEntry) -> None:
    """Process only genuinely new orders, moving previous latest → training.

    This avoids re-running the full merge/absorb/dormancy pipeline when
    only a few new orders have arrived via polling.
    """
    if not _rebuild_lock.acquire(blocking=False):
        logger.warning("incremental_update: rebuild already in progress, skipping")
        return
    try:
        _incremental_update_inner(entry)
    finally:
        _rebuild_lock.release()


def _incremental_update_inner(entry: _CacheEntry) -> None:
    global _order_data, _latest_per_location, _known_order_ids
    global _all_cities, _all_products, _state_ready
    global _city_groups_idx, _temporal_features, _next_order_ts, _next_order_num
    global _flat_rows

    df = entry.df
    records = df.to_dict(orient="records")

    excluded_products = _build_excluded_product_names()

    # Find new orders not in our known set
    new_raw_orders: list[dict[str, Any]] = []
    for row in records:
        sid = row.get("salesOrderId")
        if sid and sid not in _known_order_ids:
            parsed = _parse_order_record(row, excluded_products)
            if parsed:
                new_raw_orders.append(parsed)
                _known_order_ids.add(sid)

    if not new_raw_orders:
        logger.info("incremental_update: no new franchise orders found")
        return

    logger.info("incremental_update: processing %d new orders", len(new_raw_orders))

    newly_completed: list[dict[str, Any]] = []  # orders moved from latest → training

    for new_od in new_raw_orders:
        city_s = new_od["citySlug"]
        _all_cities.add(city_s)
        for pname in new_od["productQtys"]:
            _all_products.add(pname)

        if city_s not in _latest_per_location:
            # New location — just record as latest
            idx = len(_order_data)
            _order_data.append(new_od)
            _latest_per_location[city_s] = idx
            _city_groups_idx[city_s].append(idx)
            # Compute temporal features for first order at this location
            _temporal_features[idx] = {
                "days_since_last": 0.0,
                "avg_gap": 0.0,
                "order_count": 1.0,
                "prev_gap": 0.0,
                "gap_trend": 1.0,
            }
            logger.info("incremental_update: new location '%s' added", city_s)
            continue

        prev_latest_idx = _latest_per_location[city_s]
        prev_latest = _order_data[prev_latest_idx]

        # Compute gap between previous latest and new order
        gap_days = 0.0
        if prev_latest["orderTs"] and new_od["orderTs"]:
            gap_days = abs((new_od["orderTs"] - prev_latest["orderTs"]).total_seconds()) / 86400

        # Same-day merge check
        if gap_days <= _MERGE_WINDOW_DAYS():
            # Merge new order into previous latest
            for prod, qty in new_od["productQtys"].items():
                prev_latest["productQtys"][prod] = prev_latest["productQtys"].get(prod, 0) + qty
            if new_od["orderNumber"]:
                prev_latest["orderNumber"] = prev_latest["orderNumber"] + ", " + new_od["orderNumber"]
            if new_od["orderTs"] and (prev_latest["orderTs"] is None or new_od["orderTs"] < prev_latest["orderTs"]):
                prev_latest["orderTs"] = new_od["orderTs"]
            logger.info("incremental_update: merged order into existing latest at '%s'", city_s)
            continue

        # Dormancy check
        if gap_days > _DORMANT_THRESHOLD_DAYS():
            # Location was dormant — discard previous latest, new order becomes latest
            new_idx = len(_order_data)
            _order_data.append(new_od)
            _latest_per_location[city_s] = new_idx
            _city_groups_idx[city_s].append(new_idx)
            _temporal_features[new_idx] = {
                "days_since_last": 0.0,
                "avg_gap": 0.0,
                "order_count": 1.0,
                "prev_gap": 0.0,
                "gap_trend": 1.0,
            }
            logger.info(
                "incremental_update: dormant gap (%.0f days) at '%s', reset latest",
                gap_days, city_s,
            )
            continue

        # Normal case: complete the previous latest with next-order info
        # and move it to the training matrix
        _next_order_ts[prev_latest_idx] = new_od["orderTs"]
        _next_order_num[prev_latest_idx] = new_od["orderNumber"]

        # Previous latest is now a completed training row
        newly_completed.append(prev_latest)

        # Add new order to the order data
        new_idx = len(_order_data)
        _order_data.append(new_od)
        _latest_per_location[city_s] = new_idx
        _city_groups_idx[city_s].append(new_idx)
        _next_order_ts.append(None)
        _next_order_num.append(None)

        # Compute temporal features for the new order
        city_indices = _city_groups_idx[city_s]
        pos_in_city = len(city_indices) - 1
        prev_tf = _temporal_features.get(prev_latest_idx, {})
        prev_gaps_count = prev_tf.get("order_count", 1.0)
        prev_avg_gap = prev_tf.get("avg_gap", 0.0)

        # Running average: new_avg = (old_avg * old_count + new_gap) / new_count
        new_count = prev_gaps_count + 1.0
        new_avg_gap = (prev_avg_gap * (new_count - 1) + gap_days) / new_count if new_count > 1 else gap_days
        prev_gap_val = prev_tf.get("days_since_last", 0.0)

        _temporal_features[new_idx] = {
            "days_since_last": gap_days,
            "avg_gap": new_avg_gap,
            "order_count": new_count,
            "prev_gap": prev_gap_val,
            "gap_trend": (prev_gap_val / new_avg_gap) if new_avg_gap > 0 else 1.0,
        }

        logger.info(
            "incremental_update: '%s' — moved previous latest to training, "
            "gap=%.0f days, new order becomes latest",
            city_s, gap_days,
        )

    if not newly_completed:
        logger.info("incremental_update: no orders moved to training matrix")
        # Still rebuild latest variant files since we may have merged or added new locations
        _rebuild_variant_files_incremental(newly_completed=[])
        return

    # Rebuild variant files with the newly completed rows
    _rebuild_variant_files_incremental(newly_completed)

    # Trigger fine-tuning
    _trigger_incremental_training()


def _rebuild_variant_files_incremental(
    newly_completed: list[dict[str, Any]],
) -> None:
    """Update variant parquet files with newly completed training rows and refreshed latest."""
    sorted_cities = sorted(_all_cities)
    sorted_products = sorted(_all_products)
    loc_cols = [f"loc_{c}" for c in sorted_cities]
    prod_cols = [f"prod_{_slug(p)}" for p in sorted_products]
    prod_slug_to_name = {_slug(p): p for p in sorted_products}

    # Build flat rows for newly completed orders
    new_training_rows: list[dict[str, Any]] = []
    for od in newly_completed:
        idx = _order_data.index(od)
        nts = _next_order_ts[idx] if idx < len(_next_order_ts) else None
        non = _next_order_num[idx] if idx < len(_next_order_num) else None
        flat = _build_single_flat_row(od, idx, nts, non, loc_cols, prod_cols, prod_slug_to_name)
        if flat:
            new_training_rows.append(flat)

    # Build flat rows for all current latest orders
    latest_rows: list[dict[str, Any]] = []
    for city_s, idx in _latest_per_location.items():
        od = _order_data[idx]
        flat = _build_single_flat_row(od, idx, None, None, loc_cols, prod_cols, prod_slug_to_name)
        if flat:
            latest_rows.append(flat)

    # Compute year_norm range from all order data
    all_years = [od["orderTs"].year for od in _order_data if od.get("orderTs")]
    min_year = min(all_years) if all_years else 2020
    max_year = max(all_years) if all_years else 2025
    year_range = max(max_year - min_year, 1)

    # Count orders per location for min_orders filtering
    loc_order_counts: dict[str, int] = defaultdict(int)
    for cs, indices in _city_groups_idx.items():
        for lc in loc_cols:
            if lc == f"loc_{cs}":
                loc_order_counts[lc] = len(indices)
                break

    for variant in _VARIANT_NAMES:
        use_min_orders = "min_orders" in variant
        use_year = "year" in variant

        # Apply variant filters to new training rows
        v_new_training = _apply_variant_filters(
            new_training_rows, use_min_orders, use_year,
            loc_order_counts, loc_cols, min_year, year_range,
        )

        # Apply variant filters to latest rows
        v_latest = _apply_variant_filters(
            latest_rows, use_min_orders, use_year,
            loc_order_counts, loc_cols, min_year, year_range,
        )

        # Append new training rows to existing matrix
        v_matrix_dir = settings.cache_dir / f"franchise_order_matrix_{variant}"
        v_matrix_dir.mkdir(parents=True, exist_ok=True)
        matrix_path = v_matrix_dir / "matrix.parquet"

        if v_new_training:
            if matrix_path.exists():
                existing_df = _pq_read(matrix_path)
                new_df = pd.DataFrame(v_new_training)
                # Align columns — new rows may have different columns if new products appeared
                for col in new_df.columns:
                    if col not in existing_df.columns:
                        existing_df[col] = 0
                for col in existing_df.columns:
                    if col not in new_df.columns:
                        new_df[col] = 0
                updated_df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                updated_df = pd.DataFrame(v_new_training)
            _pq_write(updated_df, matrix_path)
            (v_matrix_dir / "matrix.meta.json").write_text(
                json.dumps({"total_count": len(updated_df)}), encoding="utf-8",
            )
            inflow_cache.put(
                f"franchise_order_matrix_{variant}",
                updated_df.to_dict(orient="records"),
                len(updated_df),
            )

        # Overwrite latest
        v_latest_dir = settings.cache_dir / f"latest_franchise_orders_{variant}"
        v_latest_dir.mkdir(parents=True, exist_ok=True)
        v_latest_df = pd.DataFrame(v_latest) if v_latest else pd.DataFrame()
        _pq_write(v_latest_df, v_latest_dir / "latest.parquet")
        (v_latest_dir / "latest.meta.json").write_text(
            json.dumps({"total_count": len(v_latest)}), encoding="utf-8",
        )
        inflow_cache.put(f"latest_franchise_orders_{variant}", v_latest, len(v_latest))

        # Base variant backward compat
        if variant == "base":
            if v_new_training and matrix_path.exists():
                full_matrix = _pq_read(matrix_path)
                inflow_cache.put(_MATRIX_KEY, full_matrix.to_dict(orient="records"), len(full_matrix))
                _save_matrix_to_disk(full_matrix, len(full_matrix))
            inflow_cache.put(_LATEST_KEY, v_latest, len(v_latest))
            _save_latest_to_disk(v_latest_df, len(v_latest))

        # Product matrix: same rows as order matrix
        next_prod_cols = [c for c in (v_latest_df.columns if len(v_latest_df) else [])
                          if c.startswith("next_prod_")]
        if not next_prod_cols and matrix_path.exists():
            check_df = pd.read_parquet(matrix_path)
            next_prod_cols = [c for c in check_df.columns if c.startswith("next_prod_")]

        if next_prod_cols:
            prod_matrix_dir = settings.cache_dir / f"franchise_product_matrix_{variant}"
            prod_matrix_dir.mkdir(parents=True, exist_ok=True)
            if matrix_path.exists():
                full_df = _pq_read(matrix_path)
                _pq_write(full_df, prod_matrix_dir / "matrix.parquet")
                (prod_matrix_dir / "matrix.meta.json").write_text(
                    json.dumps({"total_count": len(full_df)}), encoding="utf-8",
                )
                inflow_cache.put(
                    f"franchise_product_matrix_{variant}",
                    full_df.to_dict(orient="records"),
                    len(full_df),
                )

            prod_latest_dir = settings.cache_dir / f"latest_franchise_product_orders_{variant}"
            prod_latest_dir.mkdir(parents=True, exist_ok=True)
            _pq_write(v_latest_df, prod_latest_dir / "latest.parquet")
            (prod_latest_dir / "latest.meta.json").write_text(
                json.dumps({"total_count": len(v_latest)}), encoding="utf-8",
            )
            inflow_cache.put(f"latest_franchise_product_orders_{variant}", v_latest, len(v_latest))

        logger.info(
            "incremental variant '%s': +%d training rows, %d latest rows",
            variant, len(v_new_training), len(v_latest),
        )


def _apply_variant_filters(
    rows: list[dict[str, Any]],
    use_min_orders: bool,
    use_year: bool,
    loc_order_counts: dict[str, int],
    loc_cols: list[str],
    min_year: int,
    year_range: int,
) -> list[dict[str, Any]]:
    """Apply variant-specific filters to a set of flat rows."""
    if use_min_orders:
        valid_locs = {lc for lc, cnt in loc_order_counts.items()
                      if cnt >= _MIN_ORDER_THRESHOLD()}
        rows = [r for r in rows if any(r.get(lc) == 1 for lc in valid_locs)]

    if use_year:
        rows = [
            {**r, "year_norm": round(
                ((r.get("orderYear") or min_year) - min_year) / year_range, 4
            )}
            for r in rows
        ]

    return rows


def _build_single_flat_row(
    od: dict[str, Any],
    idx: int,
    nts: pd.Timestamp | None,
    non: str | None,
    loc_cols: list[str],
    prod_cols: list[str],
    prod_slug_to_name: dict[str, str],
) -> dict[str, Any] | None:
    """Build a single flat row dict from order data, for one order."""
    ts = od["orderTs"]
    if ts is None:
        return None

    # Compute order_size_norm for this single order (use 0.5 as default for incremental)
    order_size = 0.5  # approximation for incremental; full rebuild computes per-location stats

    row_dict: dict[str, Any] = {
        "orderNumber": od["orderNumber"],
        "contactName": od["contactName"],
        "orderDay": ts.day,
        "orderMonth": ts.month,
        "orderYear": ts.year,
        "nextOrderNumber": non,
        "nextOrderDay": nts.day if nts else None,
        "nextOrderMonth": nts.month if nts else None,
        "nextOrderYear": nts.year if nts else None,
        "order_size": round(order_size, 4),
    }

    tf = _temporal_features.get(idx, {})
    row_dict["days_since_last"] = round(tf.get("days_since_last", 0.0), 4)
    row_dict["avg_gap"] = round(tf.get("avg_gap", 0.0), 4)
    row_dict["order_count"] = round(tf.get("order_count", 1.0), 4)
    row_dict["prev_gap"] = round(tf.get("prev_gap", 0.0), 4)
    row_dict["gap_trend"] = round(tf.get("gap_trend", 1.0), 4)

    for lc in loc_cols:
        city_key = lc[4:]
        row_dict[lc] = 1 if od["citySlug"] == city_key else 0

    for pc in prod_cols:
        prod_key = pc[5:]
        base_name = prod_slug_to_name.get(prod_key, "")
        row_dict[pc] = round(od["productQtys"].get(base_name, 0))

    # Next-order product targets
    # Look up next order's products from _order_data if we have a next order number
    next_qtys: dict[str, float] = {}
    if non:
        for o in _order_data:
            if o["orderNumber"] == non:
                next_qtys = o["productQtys"]
                break
    for pc in prod_cols:
        prod_key = pc[5:]
        base_name = prod_slug_to_name.get(prod_key, "")
        row_dict[f"next_{pc}"] = round(next_qtys.get(base_name, 0))

    return row_dict


# ── Core rebuild ─────────────────────────────────────────────────────

def _rebuild_order_matrix(endpoint: str, entry: _CacheEntry) -> None:
    with _rebuild_lock:
        _rebuild_order_matrix_inner(endpoint, entry)


def _rebuild_order_matrix_inner(endpoint: str, entry: _CacheEntry) -> None:
    global _order_data, _latest_per_location, _known_order_ids
    global _all_cities, _all_products, _state_ready
    global _city_groups_idx, _temporal_features, _next_order_ts, _next_order_num
    global _flat_rows

    df = entry.df
    if df.empty or "lines" not in df.columns:
        logger.debug("order_matrix: no 'lines' column, skipping (plain fetch)")
        return
    if "orderNumber" not in df.columns:
        logger.warning("order_matrix: no orderNumber column, skipping")
        return

    # ── Check if incremental update is possible ──────────────────
    if _state_ready:
        # Check if the cache only has NEW orders (no modifications to existing ones)
        current_ids = set()
        for row in df.to_dict(orient="records"):
            sid = row.get("salesOrderId")
            if sid:
                current_ids.add(sid)
        new_ids = current_ids - _known_order_ids
        if new_ids and not (_known_order_ids - current_ids):
            # Only new orders added, none removed — safe for incremental
            logger.info(
                "order_matrix: incremental path — %d new order IDs detected",
                len(new_ids),
            )
            _incremental_update(entry)
            return
        else:
            logger.info("order_matrix: full rebuild (orders modified or removed)")

    # ── Full rebuild path ─────────────────────────────────────────

    # Filter franchise store orders
    franchise_df = df[df["orderNumber"].str.contains("SO-", na=False)].copy()
    if franchise_df.empty:
        logger.info("order_matrix: no franchise orders")
        return

    excluded_products = _build_excluded_product_names()
    records = franchise_df.to_dict(orient="records")

    # Filter to North America only
    records = [r for r in records if _is_north_america(r)]
    if not records:
        logger.info("order_matrix: no NA franchise orders after country filter")
        return

    # ── First pass: extract structured data per order ────────────
    order_data: list[dict[str, Any]] = []
    all_cities: set[str] = set()
    all_products: set[str] = set()

    for row in records:
        parsed = _parse_order_record(row, excluded_products)
        if parsed:
            order_data.append(parsed)
            all_cities.add(parsed["citySlug"])
            all_products.update(parsed["productQtys"].keys())

    # ── Merge orders from the same location within 3 days ──────
    merged_order_data: list[dict[str, Any]] = []
    pre_merge_count = len(order_data)

    merge_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for od in order_data:
        merge_groups[od["citySlug"]].append(od)

    for city_s, city_orders in merge_groups.items():
        city_orders.sort(key=lambda o: o["orderTs"] or pd.Timestamp.min.tz_localize("UTC"))

        i = 0
        while i < len(city_orders):
            # Start a new merged group with the current order
            group = [city_orders[i]]
            anchor_ts = city_orders[i]["orderTs"]
            j = i + 1
            while j < len(city_orders):
                cur_ts = city_orders[j]["orderTs"]
                if anchor_ts and cur_ts:
                    delta = abs((cur_ts - anchor_ts).total_seconds()) / 86400
                    if delta <= _MERGE_WINDOW_DAYS():
                        group.append(city_orders[j])
                        j += 1
                        continue
                break
            i = j

            if len(group) == 1:
                merged_order_data.append(group[0])
            else:
                # Merge: combine order numbers, use earliest date, sum product qtys
                combined_qtys: dict[str, float] = defaultdict(float)
                order_nums: list[str] = []
                contacts: list[str] = []
                earliest_ts = group[0]["orderTs"]
                for g in group:
                    if g["orderNumber"]:
                        order_nums.append(g["orderNumber"])
                    if g["contactName"] and g["contactName"] not in contacts:
                        contacts.append(g["contactName"])
                    if g["orderTs"] and (earliest_ts is None or g["orderTs"] < earliest_ts):
                        earliest_ts = g["orderTs"]
                    for prod, qty in g["productQtys"].items():
                        combined_qtys[prod] += qty

                merged_order_data.append({
                    "orderNumber": ", ".join(order_nums),
                    "contactName": ", ".join(contacts),
                    "orderTs": earliest_ts,
                    "citySlug": city_s,
                    "productQtys": dict(combined_qtys),
                })

    order_data = merged_order_data
    if pre_merge_count != len(order_data):
        logger.info(
            "order_matrix: merged %d -> %d orders (3-day window)",
            pre_merge_count, len(order_data),
        )

    # Rebuild all_products after merging (some products may only appear in merged rows)
    all_products = set()
    for od in order_data:
        all_products.update(od["productQtys"].keys())

    # ── Absorb small orders at big-order stores ─────────────────
    # At locations where small orders (totalQty <= 5) are rare (< 20%),
    # merge each small order's products into the preceding order at that
    # location.  This removes noise from random add-on orders that
    # artificially split real ordering gaps.
    _SMALL_QTY_THRESHOLD = 5
    _SMALL_ORDER_PCT_THRESHOLD = 0.20

    pre_absorb_count = len(order_data)

    absorb_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for od in order_data:
        absorb_groups[od["citySlug"]].append(od)

    absorbed_order_data: list[dict[str, Any]] = []
    total_absorbed = 0

    for city_s, city_orders in absorb_groups.items():
        city_orders.sort(
            key=lambda o: o["orderTs"] or pd.Timestamp.min.tz_localize("UTC"),
        )

        # What fraction of this location's orders are small?
        total_qty_per_order = [
            sum(o["productQtys"].values()) for o in city_orders
        ]
        n_small = sum(1 for q in total_qty_per_order if q <= _SMALL_QTY_THRESHOLD)
        pct_small = n_small / len(city_orders) if city_orders else 0

        if pct_small >= _SMALL_ORDER_PCT_THRESHOLD or n_small == 0:
            # Small orders ARE this location's normal pattern, or none exist
            absorbed_order_data.extend(city_orders)
            continue

        # Pass 1: absorb orders with qty <= threshold into previous order
        result: list[dict[str, Any]] = []
        for od in city_orders:
            total_qty = sum(od["productQtys"].values())
            if total_qty <= _SMALL_QTY_THRESHOLD and len(result) > 0:
                prev = result[-1]
                for prod, qty in od["productQtys"].items():
                    prev["productQtys"][prod] = prev["productQtys"].get(prod, 0) + qty
                if od["orderNumber"]:
                    prev["orderNumber"] = prev["orderNumber"] + ", " + od["orderNumber"]
                total_absorbed += 1
            else:
                result.append(od)

        # Pass 2: cascade — if an order (even after absorbing a small one)
        # is still far below the location's average, absorb it into the
        # order before it.  Repeat until no more absorptions occur.
        _OUTLIER_FRACTION = 0.25  # below 25 % of mean -> still an outlier
        changed = True
        while changed and len(result) > 1:
            changed = False
            avg_qty = sum(
                sum(o["productQtys"].values()) for o in result
            ) / len(result)
            threshold = avg_qty * _OUTLIER_FRACTION
            new_result: list[dict[str, Any]] = [result[0]]
            for od in result[1:]:
                total_qty = sum(od["productQtys"].values())
                if total_qty < threshold:
                    prev = new_result[-1]
                    for prod, qty in od["productQtys"].items():
                        prev["productQtys"][prod] = prev["productQtys"].get(prod, 0) + qty
                    if od["orderNumber"]:
                        prev["orderNumber"] = prev["orderNumber"] + ", " + od["orderNumber"]
                    total_absorbed += 1
                    changed = True
                else:
                    new_result.append(od)
            result = new_result

        absorbed_order_data.extend(result)

    order_data = absorbed_order_data
    if total_absorbed:
        logger.info(
            "order_matrix: absorbed %d small/outlier orders into previous orders "
            "at big-order stores (%d -> %d)",
            total_absorbed, pre_absorb_count, len(order_data),
        )

    # Rebuild all_products after absorbing
    all_products = set()
    for od in order_data:
        all_products.update(od["productQtys"].keys())

    # ── Dormancy filter (operates on order_data before flat rows) ─
    # Iteratively remove orders whose gap to the next order exceeds
    # the threshold, then recompute next-order links until stable.
    total_dormant_removed = 0

    while True:
        # Compute next-order per location
        city_groups_idx: dict[str, list[int]] = defaultdict(list)
        for i, od in enumerate(order_data):
            city_groups_idx[od["citySlug"]].append(i)

        next_order_ts: list[pd.Timestamp | None] = [None] * len(order_data)
        next_order_num: list[str | None] = [None] * len(order_data)
        for city_s, indices in city_groups_idx.items():
            indices.sort(key=lambda i: order_data[i]["orderTs"] or pd.Timestamp.min.tz_localize("UTC"))
            for pos in range(len(indices) - 1):
                cur_idx = indices[pos]
                nxt_idx = indices[pos + 1]
                next_order_ts[cur_idx] = order_data[nxt_idx]["orderTs"]
                next_order_num[cur_idx] = order_data[nxt_idx]["orderNumber"]

        # Find dormant orders (gap > threshold)
        dormant_indices: set[int] = set()
        for i, od in enumerate(order_data):
            cur_ts = od["orderTs"]
            nxt_ts = next_order_ts[i]
            if cur_ts and nxt_ts:
                gap_days = abs((nxt_ts - cur_ts).total_seconds()) / 86400
                if gap_days > _DORMANT_THRESHOLD_DAYS():
                    dormant_indices.add(i)

        if not dormant_indices:
            break  # stable — no more dormant orders

        total_dormant_removed += len(dormant_indices)
        order_data = [od for i, od in enumerate(order_data) if i not in dormant_indices]
        next_order_ts = [None] * len(order_data)
        next_order_num = [None] * len(order_data)

    if total_dormant_removed:
        logger.info(
            "order_matrix: removed %d dormant-shop orders (>%d day gap)",
            total_dormant_removed, _DORMANT_THRESHOLD_DAYS(),
        )

    # ── Remove closed-down shops from latest orders ─────────────
    # If a location's most recent order is far behind the dataset's
    # newest order, that shop is likely closed.  Use the same dormancy
    # threshold measured from the most-recent order across all locations.
    # IMPORTANT: use ALL raw NA franchise orders (including those whose
    # products were all excluded) so that locations with recent orders
    # of excluded-only products are not wrongly marked as closed.
    all_ts = [od["orderTs"] for od in order_data if od["orderTs"]]
    if all_ts:
        dataset_max_ts = max(all_ts)

        # Build city latest timestamps from ALL raw records (not just parsed)
        city_latest_ts: dict[str, pd.Timestamp] = {}
        for raw_row in records:
            raw_city = _extract_franchise_location(raw_row)
            raw_city_s = _slug(raw_city) if raw_city else "unknown"
            raw_ts = _parse_date(raw_row.get("orderDate"))
            if raw_ts and (raw_city_s not in city_latest_ts or raw_ts > city_latest_ts[raw_city_s]):
                city_latest_ts[raw_city_s] = raw_ts

        closed_cities: set[str] = set()
        for cs, latest_ts in city_latest_ts.items():
            age_days = abs((dataset_max_ts - latest_ts).total_seconds()) / 86400
            if age_days > _DORMANT_THRESHOLD_DAYS():
                closed_cities.add(cs)

        if closed_cities:
            pre_closed = len(order_data)
            order_data = [od for od in order_data if od["citySlug"] not in closed_cities]
            logger.info(
                "order_matrix: removed %d closed-shop orders (%d locations: %s)",
                pre_closed - len(order_data),
                len(closed_cities),
                ", ".join(sorted(closed_cities)),
            )

    # ── Remove empty locations from feature columns ───────────────
    active_cities: set[str] = {od["citySlug"] for od in order_data}
    removed_cities = all_cities - active_cities
    all_cities = active_cities
    if removed_cities:
        logger.info(
            "order_matrix: dropped %d empty location columns: %s",
            len(removed_cities),
            ", ".join(sorted(removed_cities)),
        )

    # ── Final next-order computation on clean data ────────────────
    city_groups_idx = defaultdict(list)
    for i, od in enumerate(order_data):
        city_groups_idx[od["citySlug"]].append(i)

    next_order_ts = [None] * len(order_data)
    next_order_num = [None] * len(order_data)
    for city_s, indices in city_groups_idx.items():
        indices.sort(key=lambda i: order_data[i]["orderTs"] or pd.Timestamp.min.tz_localize("UTC"))
        for pos in range(len(indices) - 1):
            cur_idx = indices[pos]
            nxt_idx = indices[pos + 1]
            next_order_ts[cur_idx] = order_data[nxt_idx]["orderTs"]
            next_order_num[cur_idx] = order_data[nxt_idx]["orderNumber"]

    # ── Compute historical ordering-pattern features ─────────────
    # Per-location temporal features derived from the chronological order chain.
    temporal_features: dict[int, dict[str, float]] = {}
    for city_s, indices in city_groups_idx.items():
        prev_gaps: list[float] = []
        for pos, idx in enumerate(indices):
            cur_ts = order_data[idx]["orderTs"]
            feats: dict[str, float] = {}
            if pos == 0 or cur_ts is None:
                feats["days_since_last"] = 0.0
                feats["avg_gap"] = 0.0
                feats["order_count"] = 1.0
                feats["prev_gap"] = 0.0
                feats["gap_trend"] = 1.0
            else:
                prev_idx = indices[pos - 1]
                prev_ts = order_data[prev_idx]["orderTs"]
                gap = abs((cur_ts - prev_ts).total_seconds()) / 86400 if prev_ts else 0.0
                prev_gaps.append(gap)
                feats["days_since_last"] = gap
                feats["avg_gap"] = sum(prev_gaps) / len(prev_gaps)
                feats["order_count"] = float(pos + 1)
                feats["prev_gap"] = prev_gaps[-2] if len(prev_gaps) >= 2 else 0.0
                feats["gap_trend"] = (feats["prev_gap"] / feats["avg_gap"]) if feats["avg_gap"] > 0 else 1.0
            temporal_features[idx] = feats

    # ── Rebuild column lists from active data ─────────────────────
    sorted_cities = sorted(all_cities)
    # Derive product columns from the /products page rather than from whatever
    # happened to appear in orders.  This keeps the matrix columns in sync with
    # the UI and automatically adds new products when they are added to Inflow.
    # Falls back to the set discovered from orders if the products cache is empty.
    page_products = _get_products_page_names()
    sorted_products = sorted(page_products if page_products else all_products)

    loc_cols = [f"loc_{c}" for c in sorted_cities]
    prod_cols = [f"prod_{_slug(p)}" for p in sorted_products]
    prod_slug_to_name = {_slug(p): p for p in sorted_products}

    # ── Compute per-location order_size (0.0–1.0) ──────────────
    # For each location: min→0.0, mean→0.5, max→1.0 (piecewise linear).
    order_totals = [sum(od["productQtys"].values()) for od in order_data]

    city_totals: dict[str, list[float]] = defaultdict(list)
    for od, total in zip(order_data, order_totals):
        city_totals[od["citySlug"]].append(total)

    city_stats: dict[str, tuple[float, float, float]] = {}
    for cs, totals in city_totals.items():
        city_stats[cs] = (min(totals), sum(totals) / len(totals), max(totals))

    order_sizes: list[float] = []
    for od, total in zip(order_data, order_totals):
        mn, avg, mx = city_stats[od["citySlug"]]
        if mn == mx:
            # Only one distinct size — treat as average
            order_sizes.append(0.5)
        elif total <= avg:
            # Map [min, mean] → [0.0, 0.5]
            order_sizes.append(0.5 * (total - mn) / (avg - mn) if avg > mn else 0.5)
        else:
            # Map [mean, max] → [0.5, 1.0]
            order_sizes.append(0.5 + 0.5 * (total - avg) / (mx - avg) if mx > avg else 0.5)

    # ── Build flat rows from clean combined data ──────────────────
    # Lookup: orderNumber → productQtys (for next-order product targets)
    order_products = {od["orderNumber"]: od["productQtys"] for od in order_data}

    flat_rows: list[dict[str, Any]] = []
    for i, od in enumerate(order_data):
        ts = od["orderTs"]
        nts = next_order_ts[i]

        row_dict: dict[str, Any] = {
            "orderNumber": od["orderNumber"],
            "contactName": od["contactName"],
            "orderDay": ts.day if ts else None,
            "orderMonth": ts.month if ts else None,
            "orderYear": ts.year if ts else None,
            "nextOrderNumber": next_order_num[i],
            "nextOrderDay": nts.day if nts else None,
            "nextOrderMonth": nts.month if nts else None,
            "nextOrderYear": nts.year if nts else None,
            "order_size": round(order_sizes[i], 4),
        }

        # Historical ordering-pattern features
        tf = temporal_features.get(i, {})
        row_dict["days_since_last"] = round(tf.get("days_since_last", 0.0), 4)
        row_dict["avg_gap"] = round(tf.get("avg_gap", 0.0), 4)
        row_dict["order_count"] = round(tf.get("order_count", 1.0), 4)
        row_dict["prev_gap"] = round(tf.get("prev_gap", 0.0), 4)
        row_dict["gap_trend"] = round(tf.get("gap_trend", 1.0), 4)

        # One-hot location columns
        for lc in loc_cols:
            city_key = lc[4:]  # strip "loc_"
            row_dict[lc] = 1 if od["citySlug"] == city_key else 0

        # Product quantity columns (current order — features)
        for pc in prod_cols:
            prod_key = pc[5:]  # strip "prod_"
            base_name = prod_slug_to_name.get(prod_key, "")
            row_dict[pc] = round(od["productQtys"].get(base_name, 0))

        # Next-order product quantity columns (targets for product prediction)
        next_on = next_order_num[i]
        next_qtys = order_products.get(next_on, {}) if next_on else {}
        for pc in prod_cols:
            prod_key = pc[5:]  # strip "prod_"
            base_name = prod_slug_to_name.get(prod_key, "")
            row_dict[f"next_{pc}"] = round(next_qtys.get(base_name, 0))

        flat_rows.append(row_dict)

    # Sort by date ascending
    flat_rows.sort(key=lambda r: (r["orderYear"] or 0, r["orderMonth"] or 0, r["orderDay"] or 0))

    # ── Split and save per-variant data ─────────────────────────────
    # Count orders per location for min_orders filtering
    loc_order_counts: dict[str, int] = defaultdict(int)
    for r in flat_rows:
        for lc in loc_cols:
            if r.get(lc) == 1:
                loc_order_counts[lc] += 1
                break

    # Compute year_norm range
    all_years = [r["orderYear"] for r in flat_rows if r.get("orderYear")]
    min_year = min(all_years) if all_years else 2020
    max_year = max(all_years) if all_years else 2025
    year_range = max(max_year - min_year, 1)

    for variant in _VARIANT_NAMES:
        use_min_orders = "min_orders" in variant
        use_year = "year" in variant

        # Filter by min orders if needed
        if use_min_orders:
            valid_locs = {lc for lc, cnt in loc_order_counts.items()
                          if cnt >= _MIN_ORDER_THRESHOLD()}
            variant_rows = [
                r for r in flat_rows
                if any(r.get(lc) == 1 for lc in valid_locs)
            ]
        else:
            variant_rows = list(flat_rows)

        # Add year_norm if needed (copy rows to avoid mutating originals)
        if use_year:
            variant_rows = [
                {**r, "year_norm": round(
                    ((r.get("orderYear") or min_year) - min_year) / year_range, 4
                )}
                for r in variant_rows
            ]

        # Split into matrix and latest
        v_matrix = [r for r in variant_rows if r.get("nextOrderDay") is not None]
        v_latest = [r for r in variant_rows if r.get("nextOrderDay") is None]

        # Save to variant-specific directories
        v_matrix_dir = settings.cache_dir / f"franchise_order_matrix_{variant}"
        v_latest_dir = settings.cache_dir / f"latest_franchise_orders_{variant}"
        v_matrix_dir.mkdir(parents=True, exist_ok=True)
        v_latest_dir.mkdir(parents=True, exist_ok=True)

        v_matrix_df = pd.DataFrame(v_matrix) if v_matrix else pd.DataFrame()
        v_latest_df = pd.DataFrame(v_latest) if v_latest else pd.DataFrame()

        v_matrix_df.to_parquet(v_matrix_dir / "matrix.parquet", index=False)
        v_latest_df.to_parquet(v_latest_dir / "latest.parquet", index=False)

        (v_matrix_dir / "matrix.meta.json").write_text(
            json.dumps({"total_count": len(v_matrix)}), encoding="utf-8")
        (v_latest_dir / "latest.meta.json").write_text(
            json.dumps({"total_count": len(v_latest)}), encoding="utf-8")

        # Store variant latest data in cache for live predictions
        inflow_cache.put(f"latest_franchise_orders_{variant}", v_latest, len(v_latest))

        # Base variant also populates original paths/cache for backward compat
        if variant == "base":
            inflow_cache.put(_MATRIX_KEY, v_matrix, len(v_matrix))
            _save_matrix_to_disk(v_matrix_df, len(v_matrix))
            inflow_cache.put(_LATEST_KEY, v_latest, len(v_latest))
            _save_latest_to_disk(v_latest_df, len(v_latest))

        # ── Product prediction DataFrames ──────────────────────────────
        # Identify next_prod_* columns
        next_prod_cols = [c for c in (v_matrix_df.columns if len(v_matrix_df) else
                                       v_latest_df.columns if len(v_latest_df) else [])
                          if c.startswith("next_prod_")]

        if next_prod_cols:
            # Product matrix: same rows as date matrix (has known next order products)
            prod_matrix_dir = settings.cache_dir / f"franchise_product_matrix_{variant}"
            prod_matrix_dir.mkdir(parents=True, exist_ok=True)
            v_matrix_df.to_parquet(prod_matrix_dir / "matrix.parquet", index=False)
            (prod_matrix_dir / "matrix.meta.json").write_text(
                json.dumps({"total_count": len(v_matrix)}), encoding="utf-8")
            inflow_cache.put(f"franchise_product_matrix_{variant}", v_matrix, len(v_matrix))

            # Latest product orders: same rows as latest (for prediction, next_prod_* are 0)
            prod_latest_dir = settings.cache_dir / f"latest_franchise_product_orders_{variant}"
            prod_latest_dir.mkdir(parents=True, exist_ok=True)
            v_latest_df.to_parquet(prod_latest_dir / "latest.parquet", index=False)
            (prod_latest_dir / "latest.meta.json").write_text(
                json.dumps({"total_count": len(v_latest)}), encoding="utf-8")
            inflow_cache.put(f"latest_franchise_product_orders_{variant}", v_latest, len(v_latest))

        logger.info(
            "Variant '%s': %d matrix + %d latest rows, %d next_prod cols",
            variant, len(v_matrix), len(v_latest), len(next_prod_cols),
        )

    logger.info(
        "Order matrix built: %d total flat rows, %d location cols, %d product cols, "
        "%d variants saved",
        len(flat_rows), len(loc_cols), len(prod_cols), len(_VARIANT_NAMES),
    )

    # ── Save state for incremental updates ─────────────────────────
    _order_data = order_data
    _all_cities = all_cities
    _all_products = set(sorted_products)  # products-page set, not just order-discovered
    _city_groups_idx = defaultdict(list, city_groups_idx)
    _temporal_features = temporal_features
    _next_order_ts = next_order_ts
    _next_order_num = next_order_num
    _flat_rows = flat_rows

    # Build _known_order_ids from the raw DataFrame
    _known_order_ids = set()
    for row in df.to_dict(orient="records"):
        sid = row.get("salesOrderId")
        if sid:
            _known_order_ids.add(sid)

    # Build _latest_per_location: for each city, the index of the last order
    _latest_per_location = {}
    for city_s, indices in city_groups_idx.items():
        if indices:
            _latest_per_location[city_s] = indices[-1]

    _state_ready = True
    logger.info(
        "State saved for incremental updates: %d orders, %d locations, %d known IDs",
        len(_order_data), len(_latest_per_location), len(_known_order_ids),
    )

    # ── Trigger incremental training if new completed orders detected ──
    _trigger_incremental_training()


# Track known matrix order numbers between rebuilds
_prev_matrix_orders: dict[str, set[str]] = {}


def _trigger_incremental_training() -> None:
    """Check each variant for new completed orders and fine-tune the model."""
    global _prev_matrix_orders
    from services.training_service import training_service

    for variant in _VARIANT_NAMES:
        model_path = settings.model_dir / f"order_predictor_{variant}.pt"
        if not model_path.exists():
            continue

        matrix_key = f"franchise_order_matrix_{variant}"
        cached = inflow_cache.get(matrix_key)
        if cached is None or not cached.get("data"):
            # Try loading from parquet if not in cache
            parquet_path = settings.cache_dir / f"franchise_order_matrix_{variant}" / "matrix.parquet"
            if not parquet_path.exists():
                continue
            new_df = pd.read_parquet(parquet_path)
        else:
            new_df = pd.DataFrame(cached["data"])

        if new_df.empty or "orderNumber" not in new_df.columns:
            continue

        current_orders = set(new_df["orderNumber"].dropna().astype(str))
        prev_orders = _prev_matrix_orders.get(variant, set())

        new_orders = current_orders - prev_orders
        _prev_matrix_orders[variant] = current_orders

        if not prev_orders:
            # First run — just record the baseline, don't trigger training
            logger.info("[%s] Baseline: %d matrix orders tracked", variant, len(current_orders))
            continue

        if not new_orders:
            continue

        logger.info(
            "[%s] %d new completed orders detected — triggering fine-tuning",
            variant, len(new_orders),
        )

        # Fine-tune order prediction model
        try:
            training_service.incremental_train(variant, new_df)
        except Exception:
            logger.exception("[%s] Order model fine-tuning failed", variant)

        # Fine-tune product prediction model
        try:
            from services.product_training_service import product_training_service
            product_training_service.incremental_train(variant, new_df)
        except Exception:
            logger.exception("[%s] Product model fine-tuning failed", variant)


# ── Initialisation ───────────────────────────────────────────────────

def init_order_matrix() -> None:
    _MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    _LATEST_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing files from disk first
    _load_from_disk()
    _load_latest_from_disk()

    # Register callback for future updates
    inflow_cache.register_on_update(
        _PARENT_ENDPOINT,
        _rebuild_order_matrix,
        derived_keys=[_MATRIX_KEY, _LATEST_KEY],
    )

    # If detailed sales-orders already in cache, rebuild now
    detailed_key = _make_cache_key(
        _PARENT_ENDPOINT,
        {"include": "lines.product,customer,location"},
    )
    entry = inflow_cache.get_entry(detailed_key)
    if entry is not None:
        _rebuild_order_matrix(_PARENT_ENDPOINT, entry)


# Auto-initialise when this module is first imported
init_order_matrix()
