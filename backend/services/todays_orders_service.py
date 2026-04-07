from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from config import VARIANT_NAMES
from services.cache_service import inflow_cache

logger = logging.getLogger(__name__)

_VARIANTS = VARIANT_NAMES


def _effective_date(d: date) -> date:
    """Shift Saturday (+2) and Sunday (+1) to the following Monday."""
    weekday = d.weekday()  # 0=Mon … 5=Sat, 6=Sun
    if weekday == 5:
        return d + timedelta(days=2)
    if weekday == 6:
        return d + timedelta(days=1)
    return d


def build_todays_predicted_orders(variant: str) -> int:
    """Filter predictions for today and store in cache.

    Uses _effective_date() so that Saturday/Sunday predictions are
    treated as belonging to the following Monday.

    Returns the number of rows matched.
    """
    today_effective = _effective_date(date.today())

    cache_key = f"predicted_next_order_date_{variant}"
    cached = inflow_cache.get(cache_key)
    if cached is None:
        logger.info(
            "build_todays_predicted_orders(%s): no predictions cached yet", variant
        )
        return 0

    rows: list[dict[str, Any]] = cached.get("data") or []
    today_rows: list[dict[str, Any]] = []

    for row in rows:
        pred_str: str | None = row.get("predictedNextOrderDate")
        if not pred_str:
            continue
        try:
            pred_date = date.fromisoformat(pred_str)
        except ValueError:
            continue
        if _effective_date(pred_date) == today_effective:
            today_rows.append(row)

    today_key = f"todays_predicted_orders_{variant}"
    inflow_cache.put(today_key, today_rows, len(today_rows))

    logger.info(
        "build_todays_predicted_orders(%s): %d orders for effective date %s",
        variant, len(today_rows), today_effective.isoformat(),
    )
    return len(today_rows)


def build_all_variants() -> dict[str, int]:
    """Build today's predicted orders for all 4 variants."""
    results: dict[str, int] = {}
    for variant in _VARIANTS:
        try:
            results[variant] = build_todays_predicted_orders(variant)
        except Exception:
            logger.exception(
                "Failed to build today's orders for variant %s", variant
            )
            results[variant] = 0
    return results
