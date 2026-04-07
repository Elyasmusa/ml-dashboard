from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any, Callable

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

_CACHE_DIR: Path = settings.cache_dir


def _make_cache_key(endpoint: str, extra_params: dict[str, Any] | None = None) -> str:
    """Build a deterministic cache key from endpoint + sorted extra_params.

    Internal pagination params (count, skip, includeCount) are excluded
    because they don't change the logical dataset.
    """
    if not extra_params:
        return endpoint
    stable = sorted(
        (k, v) for k, v in extra_params.items()
        if k not in {"count", "skip", "includeCount"}
    )
    if not stable:
        return endpoint
    qs = "&".join(f"{k}={v}" for k, v in stable)
    return f"{endpoint}?{qs}"


def _key_to_filename(key: str) -> str:
    """Convert a cache key to a safe filename (without extension)."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', key)


@dataclass
class _CacheEntry:
    df: pd.DataFrame
    total_count: int
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InflowCache:
    """DataFrame cache for Inflow API list responses, backed by Parquet files."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()
        self._on_update_callbacks: dict[str, list[Callable[[str, _CacheEntry], None]]] = defaultdict(list)
        self._derived_keys: dict[str, list[str]] = defaultdict(list)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    # ── Callbacks ─────────────────────────────────────────────────────

    def register_on_update(
        self, endpoint: str, callback: Callable[[str, _CacheEntry], None],
        derived_keys: list[str] | None = None,
    ) -> None:
        """Register a callback to fire when *endpoint* is updated via put/merge.

        If *derived_keys* are provided, they will be automatically invalidated
        whenever the parent endpoint is invalidated.
        """
        self._on_update_callbacks[endpoint].append(callback)
        if derived_keys:
            self._derived_keys[endpoint].extend(derived_keys)
        logger.info("Registered on-update callback for %s", endpoint)

    def _fire_callbacks(self, endpoint: str, entry: _CacheEntry) -> None:
        """Invoke all registered callbacks for the given endpoint."""
        for cb in self._on_update_callbacks.get(endpoint, []):
            try:
                cb(endpoint, entry)
            except Exception:
                logger.exception("on-update callback failed for %s", endpoint)

    # ── Disk persistence ────────────────────────────────────────────

    def _parquet_path(self, key: str) -> Path:
        return _CACHE_DIR / f"{_key_to_filename(key)}.parquet"

    def _meta_path(self, key: str) -> Path:
        return _CACHE_DIR / f"{_key_to_filename(key)}.meta.json"

    def _save_to_disk(self, key: str, entry: _CacheEntry) -> None:
        """Persist a single cache entry to a Parquet file + metadata JSON."""
        try:
            parquet_path = self._parquet_path(key)
            meta_path = self._meta_path(key)

            entry.df.to_parquet(parquet_path, index=False)

            meta = {
                "key": key,
                "total_count": entry.total_count,
                "cached_at": entry.cached_at.isoformat(),
            }
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            logger.info("Saved cache to disk: %s", parquet_path.name)
        except Exception:
            logger.exception("Failed to save cache entry %s to disk", key)

    def _remove_from_disk(self, key: str) -> None:
        """Delete the Parquet + metadata files for a cache key."""
        for path in (self._parquet_path(key), self._meta_path(key)):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                logger.exception("Failed to remove %s", path)

    def _load_from_disk(self) -> None:
        """Load all Parquet files from the cache directory on startup."""
        loaded = 0
        for meta_path in _CACHE_DIR.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                key = meta["key"]
                parquet_path = _CACHE_DIR / f"{meta_path.stem.removesuffix('.meta')}.parquet"

                if not parquet_path.exists():
                    logger.warning("Parquet file missing for %s, skipping", key)
                    continue

                df = pd.read_parquet(parquet_path)
                cached_at = datetime.fromisoformat(meta["cached_at"])

                self._store[key] = _CacheEntry(
                    df=df,
                    total_count=meta["total_count"],
                    cached_at=cached_at,
                )
                loaded += 1
            except Exception:
                logger.exception("Failed to load cache from %s", meta_path)

        if loaded:
            logger.info("Loaded %d cache entries from disk", loaded)

    # ── Public API (unchanged interface) ────────────────────────────

    async def get_lock_for(
        self, endpoint: str, extra_params: dict[str, Any] | None = None
    ) -> asyncio.Lock:
        """Get or create a per-key lock (prevents thundering-herd)."""
        key = _make_cache_key(endpoint, extra_params)
        async with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    def get_entry(self, key: str) -> "_CacheEntry | None":
        """Return the raw ``_CacheEntry`` for an already-computed cache key, or None.

        Use this when you need access to the underlying DataFrame rather than
        the JSON-serialisable response shape returned by :meth:`get`.  Avoids
        accessing the private ``_store`` dict from outside the class.
        """
        return self._store.get(key)

    def get(
        self, endpoint: str, extra_params: dict[str, Any] | None = None
    ) -> dict | None:
        """Return cached data in InflowListResponse shape, or None on miss."""
        key = _make_cache_key(endpoint, extra_params)
        entry = self._store.get(key)
        if entry is None:
            return None
        return self._entry_to_response(entry)

    def put(
        self,
        endpoint: str,
        data: list[dict[str, Any]],
        total_count: int,
        extra_params: dict[str, Any] | None = None,
    ) -> bool:
        """Store data as a DataFrame and persist to a Parquet file.

        Returns True if the cache was actually updated (data differs),
        False if the data was identical to what was already cached.
        """
        key = _make_cache_key(endpoint, extra_params)
        new_df = pd.DataFrame(data) if data else pd.DataFrame()

        existing = self._store.get(key)
        data_changed = True
        if existing is not None:
            # Normalise column order before comparison
            if set(existing.df.columns) == set(new_df.columns) and not new_df.empty:
                new_df = new_df[existing.df.columns]

            if (
                existing.total_count == total_count
                and existing.df.shape == new_df.shape
                and existing.df.equals(new_df)
            ):
                data_changed = False

        entry = _CacheEntry(df=new_df, total_count=total_count)
        self._store[key] = entry
        if data_changed:
            self._save_to_disk(key, entry)
            logger.info("Cache updated for %s (%d records)", key, total_count)
        else:
            logger.debug("Cache data unchanged for %s (%d records)", key, total_count)

        # Always fire callbacks — downstream processing logic may have changed
        # even when the raw data hasn't.
        self._fire_callbacks(endpoint, entry)
        return data_changed

    def has_cache(self, endpoint: str) -> bool:
        """Return True if a cache entry exists for this endpoint."""
        key = _make_cache_key(endpoint)
        return key in self._store

    # Column names the Inflow API uses for "last modified" timestamps,
    # checked in priority order.
    _MODIFIED_DATE_COLUMNS = (
        "timestamp",
        "lastModifiedDttm",
        "lastModifiedDateTime",
        "modifiedDate",
    )

    def get_cached_at(
        self, endpoint: str, extra_params: dict[str, Any] | None = None,
    ) -> datetime | None:
        """Return the datetime when this cache entry was last written, or None on miss."""
        key = _make_cache_key(endpoint, extra_params)
        entry = self._store.get(key)
        return entry.cached_at if entry is not None else None

    def get_last_modified(
        self, endpoint: str, extra_params: dict[str, Any] | None = None,
    ) -> str | None:
        """Return the latest modified-date value from the cached DataFrame.

        Checks several possible column names used by the Inflow API.
        Returns None if the cache is empty or has no recognised date column.
        """
        key = _make_cache_key(endpoint, extra_params)
        entry = self._store.get(key)
        if entry is None or entry.df.empty:
            return None
        for col_name in self._MODIFIED_DATE_COLUMNS:
            if col_name in entry.df.columns:
                col = entry.df[col_name].dropna()
                if not col.empty:
                    return str(col.max())
        return None

    def merge(
        self,
        endpoint: str,
        new_data: list[dict[str, Any]],
        id_column: str = "id",
        extra_params: dict[str, Any] | None = None,
    ) -> bool:
        """Merge new records into an existing cached DataFrame by id_column.

        Existing rows with matching IDs are updated; truly new rows are appended.
        Returns True if the cache was modified, False otherwise.
        """
        key = _make_cache_key(endpoint, extra_params)
        entry = self._store.get(key)
        if not new_data:
            return False
        if entry is None:
            # No existing cache — store the new data as-is
            return self.put(endpoint, new_data, len(new_data), extra_params)

        new_df = pd.DataFrame(new_data)
        if new_df.empty or id_column not in new_df.columns:
            return False

        existing_df = entry.df
        if id_column not in existing_df.columns:
            return False

        # Remove old versions of updated rows, then append all new rows
        updated_ids = set(new_df[id_column].dropna())
        kept = existing_df[~existing_df[id_column].isin(updated_ids)]
        merged = pd.concat([kept, new_df], ignore_index=True)

        new_total = len(merged)
        new_entry = _CacheEntry(df=merged, total_count=new_total)
        self._store[key] = new_entry
        self._save_to_disk(key, new_entry)
        logger.info(
            "Cache merged for %s (%d existing + %d new/updated = %d total)",
            key, len(kept), len(new_df), new_total,
        )
        self._fire_callbacks(endpoint, new_entry)
        return True

    def invalidate(self, endpoint: str) -> int:
        """Remove all cache entries whose key starts with the given endpoint.

        Invalidating ``sales-orders`` also removes
        ``sales-orders?include=lines.product,customer,location``
        and any registered derived keys.
        Returns the number of entries removed.
        """
        keys_to_remove = [
            k for k in self._store
            if k == endpoint or k.startswith(endpoint + "?")
        ]
        # Also invalidate derived keys registered for this endpoint
        for dk in self._derived_keys.get(endpoint, []):
            if dk in self._store and dk not in keys_to_remove:
                keys_to_remove.append(dk)
        for k in keys_to_remove:
            del self._store[k]
            self._remove_from_disk(k)
        if keys_to_remove:
            logger.info(
                "Cache invalidated for %s (%d entries)", endpoint, len(keys_to_remove)
            )
        return len(keys_to_remove)

    def invalidate_all(self) -> None:
        """Clear the entire cache (memory and disk)."""
        count = len(self._store)
        self._store.clear()
        for f in _CACHE_DIR.glob("*.parquet"):
            f.unlink(missing_ok=True)
        for f in _CACHE_DIR.glob("*.meta.json"):
            f.unlink(missing_ok=True)
        logger.info("Entire cache cleared (%d entries)", count)

    @staticmethod
    def _scrub_value(v: Any) -> Any:
        """Convert pandas NaN/NaT back to None; leave other types as-is.

        Also recovers nested dicts/lists that PyArrow serialized as JSON strings
        when persisting object columns to Parquet.  Applied recursively so that
        deeply nested structures (e.g. lines → product, lines → quantity) are
        fully restored, not just the top-level field.
        """
        # numpy arrays come back from Parquet for nested data — convert to list
        # first so the isinstance(list) branch below handles recursion.
        if hasattr(v, "tolist"):
            v = v.tolist()

        if isinstance(v, list):
            return [InflowCache._scrub_value(item) for item in v]

        if isinstance(v, dict):
            return {k: InflowCache._scrub_value(val) for k, val in v.items()}

        # PyArrow serializes nested dicts/lists as JSON strings in Parquet object
        # columns.  Attempt to recover the original structure so that downstream
        # code (e.g. customer/location flattening, line.product?.name) sees real
        # Python objects rather than raw strings.
        if isinstance(v, str) and len(v) > 1 and v[0] in ('{', '['):
            try:
                parsed = json.loads(v)
                # Recurse into the parsed value so any deeper strings are also fixed.
                return InflowCache._scrub_value(parsed)
            except (ValueError, TypeError):
                pass

        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass

        return v

    @staticmethod
    def _entry_to_response(entry: _CacheEntry) -> dict:
        """Convert a cache entry back to the InflowListResponse dict shape."""
        if entry.df.empty:
            data: list[dict[str, Any]] = []
        else:
            records = entry.df.to_dict(orient="records")
            data = [
                {k: InflowCache._scrub_value(v) for k, v in row.items()}
                for row in records
            ]
        return {
            "data": data,
            "hasMore": False,
            "totalCount": entry.total_count,
        }


# Module-level singleton
inflow_cache = InflowCache()
