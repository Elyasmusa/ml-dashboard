from __future__ import annotations

import logging

from services.cache_service import inflow_cache, _CacheEntry

logger = logging.getLogger(__name__)

_PARENT_ENDPOINT = "sales-orders"
_FRANCHISE_KEY = "franchise_store_orders"
_ONLINE_KEY = "online_orders"


def _rebuild_derived_frames(endpoint: str, entry: _CacheEntry) -> None:
    """Split the sales-orders DataFrame into franchise and online orders.

    Called automatically whenever the ``sales-orders`` cache is updated
    (via full fetch or polling merge).
    """
    df = entry.df
    if df.empty or "orderNumber" not in df.columns:
        logger.warning("Cannot build derived frames: no orderNumber column")
        return

    franchise_df = df[df["orderNumber"].str.contains("SO-", na=False)].copy()
    online_df = df[df["orderNumber"].str.contains("SQ", na=False)].copy()

    inflow_cache.put(_FRANCHISE_KEY, franchise_df.to_dict(orient="records"), len(franchise_df))
    inflow_cache.put(_ONLINE_KEY, online_df.to_dict(orient="records"), len(online_df))

    logger.info(
        "Derived frames rebuilt: %d franchise store orders, %d online orders",
        len(franchise_df), len(online_df),
    )


def init_derived_frames() -> None:
    """Register the callback and rebuild from existing cache if available."""
    inflow_cache.register_on_update(
        _PARENT_ENDPOINT,
        _rebuild_derived_frames,
        derived_keys=[_FRANCHISE_KEY, _ONLINE_KEY],
    )

    # If sales-orders was loaded from disk on startup, build immediately
    if inflow_cache.has_cache(_PARENT_ENDPOINT):
        from services.cache_service import _make_cache_key, _CacheEntry as _CE
        key = _make_cache_key(_PARENT_ENDPOINT)
        entry = inflow_cache.get_entry(key)
        if entry is not None:
            _rebuild_derived_frames(_PARENT_ENDPOINT, entry)


# Auto-initialise when this module is first imported
init_derived_frames()
