from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

from config import settings
from services.cache_service import inflow_cache
from services.inflow_client import inflow_client, InflowClientError

logger = logging.getLogger(__name__)

_PAGE_COUNT = 100
_MAX_PAGES = 100

# Endpoints polled every cycle (only sales-orders affects matrices).
_POLL_ENDPOINTS: dict[str, str] = {
    "sales-orders": "salesOrderId",
}

# All endpoints fetched on startup and during full refreshes.
_ALL_ENDPOINTS: dict[str, str] = {
    "products": "productId",
    "customers": "customerId",
    "vendors": "vendorId",
    "sales-orders": "salesOrderId",
    "purchase-orders": "purchaseOrderId",
}

# Detailed sales orders variant that triggers derived frame rebuilds.
_DETAILED_SO_PARAMS: dict[str, Any] = {"include": "lines.product,customer,location"}

# Every Nth poll cycle, do a full re-fetch instead of an incremental merge.
# This ensures data integrity even if the incremental approach misses something.
# Set to 60 (= once per hour at 60s interval) since incremental updates handle normal cases.
_FULL_REFRESH_EVERY = 60


async def _fetch_page(
    endpoint: str,
    extra_params: dict[str, Any] | None = None,
    modified_since: str | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """Fetch a page from the Inflow API, sorted newest-first.

    If *modified_since* is given, only records modified after that timestamp
    are requested (the API may ignore the filter if unsupported, but that
    just means we fetch a little more data than strictly necessary).

    Returns (records, total_count).
    """
    params: dict[str, Any] = {
        "count": str(_PAGE_COUNT),
        "skip": "0",
        "includeCount": "true",
        "orderBy": "modifiedDate desc",
    }
    if modified_since:
        params["modifiedSince"] = modified_since
    if extra_params:
        params.update(extra_params)

    try:
        raw, list_count = await inflow_client.get_paged(endpoint, params=params)
    except InflowClientError as exc:
        logger.warning(
            "Fetch %s failed (status %s): %s",
            endpoint, exc.status_code, exc.detail,
        )
        return [], None

    if isinstance(raw, list):
        page_data = raw
    elif isinstance(raw, dict):
        page_data = raw.get("data", raw.get("items", []))
    else:
        page_data = []

    return page_data, list_count


async def _fetch_all_modified(
    endpoint: str,
    id_column: str,
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch ALL records modified since the last cache update.

    Pages through the API (newest first) until we hit records we've already
    seen, or exhaust all pages.
    """
    last_modified = inflow_cache.get_last_modified(endpoint, extra_params)

    all_data: list[dict[str, Any]] = []
    skip = 0

    for _ in range(_MAX_PAGES):
        params: dict[str, Any] = {
            "count": str(_PAGE_COUNT),
            "skip": str(skip),
            "includeCount": "true",
            "orderBy": "modifiedDate desc",
        }
        if last_modified:
            params["modifiedSince"] = last_modified
        if extra_params:
            params.update(extra_params)

        try:
            raw, _ = await inflow_client.get_paged(endpoint, params=params)
        except InflowClientError as exc:
            logger.warning(
                "Fetch modified %s failed (status %s): %s",
                endpoint, exc.status_code, exc.detail,
            )
            break

        if isinstance(raw, list):
            page_data = raw
        elif isinstance(raw, dict):
            page_data = raw.get("data", raw.get("items", []))
        else:
            page_data = []

        if not page_data:
            break

        all_data.extend(page_data)

        if len(page_data) < _PAGE_COUNT:
            break  # last page
        skip += len(page_data)

    return all_data


async def _initial_full_fetch() -> None:
    """Populate caches with a complete fetch of all pages from the Inflow API.

    Called once on startup.  Fetches products first (needed for exclusion
    filters), then detailed sales orders (triggers matrix build via callback),
    then remaining endpoints in parallel.

    If called without valid API credentials, skips the fetch and logs a warning.
    """
    from services import inflow_service

    if not settings.has_inflow_credentials:
        logger.warning(
            "Skipping initial fetch: Inflow API credentials not configured. "
            "Using cached data only."
        )
        return

    logger.info("Startup: fetching products with inventory lines")
    await inflow_service.list_products({"include": "inventoryLines,category,defaultPrice"})

    logger.info("Startup: fetching detailed sales orders (triggers matrix build)")
    await inflow_service.list_sales_orders(_DETAILED_SO_PARAMS)

    logger.info("Startup: fetching remaining endpoints in parallel")
    await asyncio.gather(
        inflow_service.list_customers(),
        inflow_service.list_vendors(),
        inflow_service.list_purchase_orders(),
    )
    logger.info("Startup fetch complete: products -> orders -> rest")

    # Populate today's orders from whatever predictions are already cached
    try:
        from services.todays_orders_service import build_all_variants
        build_all_variants()
        logger.info("Startup: today's predicted orders populated")
    except Exception:
        logger.exception("Startup: failed to build today's predicted orders")


async def _refresh_incremental() -> None:
    """Fetch records modified since the last poll and merge them into the cache.

    For each endpoint, fetches ALL modified records (paginating as needed)
    sorted by modifiedDate desc. This ensures new and updated records are
    always picked up.
    """
    logger.info("Incremental refresh: polling sales-orders for new data")

    for endpoint, id_col in _POLL_ENDPOINTS.items():
        modified = await _fetch_all_modified(endpoint, id_col)
        if modified:
            inflow_cache.merge(endpoint, modified, id_column=id_col)
            logger.info(
                "Merged %d modified records for %s", len(modified), endpoint,
            )

    # Also refresh detailed sales orders so derived frames (order matrix) rebuild
    modified = await _fetch_all_modified(
        "sales-orders", "salesOrderId", _DETAILED_SO_PARAMS,
    )
    if modified:
        inflow_cache.merge(
            "sales-orders", modified,
            id_column="salesOrderId",
            extra_params=_DETAILED_SO_PARAMS,
        )
        logger.info(
            "Merged %d modified detailed sales orders", len(modified),
        )

    logger.info("Incremental refresh complete")


async def full_refresh() -> None:
    """Force a complete re-fetch of all data from the Inflow API.

    Used by the manual /update endpoint.
    """
    from services import inflow_service

    for ep in _ALL_ENDPOINTS:
        inflow_cache.invalidate(ep)

    logger.info("Caches invalidated — fetching fresh data from Inflow API")
    await inflow_service.get_dashboard_summary()
    await inflow_service.list_sales_orders(_DETAILED_SO_PARAMS)
    logger.info("Full data refresh complete")


async def run_daily_product_refresh() -> None:
    """Refresh the products cache (with inventory lines) every day at 4 pm ET.

    Runs independently of the main polling loop so the schedule is exact
    regardless of how long incremental refreshes take.

    If Inflow API credentials are not configured, skips the refresh and logs a warning.
    """
    from services import inflow_service

    _INCLUDE = {"include": "inventoryLines,category,defaultPrice"}

    while True:
        now = datetime.now(_ET)
        target = now.replace(hour=16, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        logger.info(
            "Daily product refresh scheduled in %.0f s (next run: %s ET)",
            wait,
            target.strftime("%Y-%m-%d %H:%M"),
        )
        await asyncio.sleep(wait)
        try:
            if not settings.has_inflow_credentials:
                logger.debug("Skipping daily product refresh: no Inflow API credentials")
                continue
            inflow_cache.invalidate("products")
            await inflow_service.list_products(_INCLUDE)
            logger.info("Daily 4 pm ET product refresh complete")
        except Exception:
            logger.exception("Daily product refresh failed")


async def run_daily_orders_refresh() -> None:
    """Rebuild today's predicted orders at midnight ET each day.

    As the date changes, different prediction rows become "today's orders"
    (including the weekend → Monday collapse). Running at midnight ensures
    Monday picks up Saturday/Sunday predictions from the previous weekend.
    """
    from services.todays_orders_service import build_all_variants

    while True:
        now = datetime.now(_ET)
        # Next midnight ET
        target = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        wait = (target - now).total_seconds()
        logger.info(
            "Daily orders refresh scheduled in %.0f s (next run: %s ET)",
            wait,
            target.strftime("%Y-%m-%d %H:%M"),
        )
        await asyncio.sleep(wait)
        try:
            results = build_all_variants()
            logger.info("Daily midnight orders refresh complete: %s", results)
        except Exception:
            logger.exception("Daily orders refresh failed")


async def run_daily_predictions_refresh() -> None:
    """Re-run order predictions for all variants once after 5 pm ET each day.

    Uses the existing trained models — no retraining occurs.  This keeps
    predicted dates fresh as the current date advances relative to each
    location's last order date.
    """
    while True:
        now = datetime.now(_ET)
        target = now.replace(hour=17, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        logger.info(
            "Daily predictions refresh scheduled in %.0f s (next run: %s ET)",
            wait,
            target.strftime("%Y-%m-%d %H:%M"),
        )
        await asyncio.sleep(wait)
        try:
            from services.training_service import refresh_all_predictions
            results = refresh_all_predictions()
            logger.info("Daily 5pm ET predictions refresh complete: %s", results)
        except Exception:
            logger.exception("Daily predictions refresh failed")


async def run_stale_products_check() -> None:
    """Periodically ensure the products cache is from today (ET).

    If the backend restarts after midnight or the scheduled 4 pm refresh
    fails, this check catches the stale day and re-fetches products so that
    roast stock and inventory data stay current.  Runs every 30 minutes.
    """
    from services import inflow_service

    _INCLUDE = {"include": "inventoryLines,category,defaultPrice"}
    _CHECK_INTERVAL = 30 * 60  # 30 minutes

    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            if not settings.has_inflow_credentials:
                logger.debug("Skipping stale products check: no Inflow API credentials")
                continue
            cached_at = inflow_cache.get_cached_at("products", _INCLUDE)
            if cached_at is None:
                # Cache not populated yet — initial fetch will handle it.
                continue

            cached_date = cached_at.astimezone(_ET).date()
            today = datetime.now(_ET).date()

            if cached_date != today:
                logger.info(
                    "Products cache is from %s but today is %s — refreshing roast/inventory data",
                    cached_date,
                    today,
                )
                inflow_cache.invalidate("products")
                await inflow_service.list_products(_INCLUDE)
                logger.info("Stale products cache refresh complete")
            else:
                logger.debug(
                    "Products cache is current (cached_date=%s)", cached_date
                )
        except Exception:
            logger.exception("Stale products check failed")


_CB_FAILURE_THRESHOLD = 5   # consecutive failures before opening the circuit
_CB_BACKOFF_CAP = 600       # maximum back-off sleep in seconds (10 minutes)


async def run_polling_loop() -> None:
    """Background loop: full fetch on startup, then incremental refresh every interval.

    Every _FULL_REFRESH_EVERY cycles, does a full invalidate + re-fetch to
    ensure data integrity.  Uses exponential back-off with a circuit-breaker:
    after _CB_FAILURE_THRESHOLD consecutive failures the sleep doubles each
    cycle (capped at _CB_BACKOFF_CAP seconds) until a success resets the count.

    If Inflow API credentials are not configured, uses cached data only.
    """
    if not settings.has_inflow_credentials:
        logger.info("Polling service: no Inflow API credentials. Using cached data only.")
        # Still run daily prediction refresh to keep predictions current
        while True:
            await asyncio.sleep(3600)  # Just keep the service alive
        return

    interval = settings.poll_interval
    logger.info("Polling service started (interval=%ds)", interval)

    try:
        await _initial_full_fetch()
    except Exception:
        logger.exception("Initial data fetch failed")

    cycle = 0
    consecutive_failures = 0
    current_interval = interval

    while True:
        await asyncio.sleep(current_interval)
        cycle += 1
        try:
            if cycle % _FULL_REFRESH_EVERY == 0:
                logger.info("Cycle %d: full re-fetch", cycle)
                await full_refresh()
            else:
                await _refresh_incremental()
            # Success — reset back-off
            if consecutive_failures > 0:
                logger.info(
                    "Polling recovered after %d consecutive failure(s); "
                    "resetting interval to %ds",
                    consecutive_failures, interval,
                )
            consecutive_failures = 0
            current_interval = interval
        except Exception:
            consecutive_failures += 1
            logger.exception(
                "Scheduled data refresh failed (cycle %d, consecutive_failures=%d)",
                cycle, consecutive_failures,
            )
            if consecutive_failures >= _CB_FAILURE_THRESHOLD:
                current_interval = min(current_interval * 2, _CB_BACKOFF_CAP)
                logger.warning(
                    "Circuit breaker: %d consecutive failures — "
                    "backing off to %ds before next attempt",
                    consecutive_failures, current_interval,
                )
