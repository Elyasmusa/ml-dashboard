from __future__ import annotations

import logging
from typing import Any

from utils import safe_value as _safe_value, NA_COUNTRIES as _NA_COUNTRIES
from services.cache_service import inflow_cache, _CacheEntry

logger = logging.getLogger(__name__)

_PARENT_ENDPOINT = "sales-orders"
_NA_KEY = "na_franchise_orders"


def _extract_country(row: dict[str, Any]) -> str | None:
    """Extract country from shippingAddress, falling back to billingAddress."""
    for addr_key in ("shippingAddress", "billingAddress"):
        addr = row.get(addr_key)
        if addr is None:
            continue
        addr = _safe_value(addr)
        if isinstance(addr, dict):
            country = addr.get("country")
            if country and isinstance(country, str) and country.strip():
                return country.strip()
    return None


def _is_north_america(row: dict[str, Any]) -> bool:
    country = _extract_country(row)
    if not country:
        return False
    # Normalize: strip periods and extra whitespace so "U.S." → "us"
    normalized = country.lower().replace(".", "").strip()
    return normalized in _NA_COUNTRIES


def _rebuild_na_frame(endpoint: str, entry: _CacheEntry) -> None:
    """Filter franchise store orders to only those in USA / Canada."""
    df = entry.df
    if df.empty or "orderNumber" not in df.columns:
        logger.warning("na_orders: no orderNumber column, skipping")
        return

    # Franchise store orders have "SO-" in orderNumber
    franchise_df = df[df["orderNumber"].str.contains("SO-", na=False)].copy()
    if franchise_df.empty:
        logger.info("na_orders: no franchise orders to filter")
        return

    records = franchise_df.to_dict(orient="records")
    na_records = [r for r in records if _is_north_america(r)]

    inflow_cache.put(_NA_KEY, na_records, len(na_records))

    logger.info(
        "NA franchise orders rebuilt: %d of %d franchise orders are in North America",
        len(na_records), len(records),
    )


def init_na_orders() -> None:
    """Register the callback and rebuild from existing cache if available."""
    inflow_cache.register_on_update(
        _PARENT_ENDPOINT,
        _rebuild_na_frame,
        derived_keys=[_NA_KEY],
    )

    # If sales-orders was loaded from disk on startup, build immediately
    if inflow_cache.has_cache(_PARENT_ENDPOINT):
        from services.cache_service import _make_cache_key
        key = _make_cache_key(_PARENT_ENDPOINT)
        entry = inflow_cache.get_entry(key)
        if entry is not None:
            _rebuild_na_frame(_PARENT_ENDPOINT, entry)


# Auto-initialise when this module is first imported
init_na_orders()
