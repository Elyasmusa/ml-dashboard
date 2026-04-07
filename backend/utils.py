"""Shared utilities used across backend services."""
from __future__ import annotations

from typing import Any

# Country values that count as North America (USA + Canada).
# Used by order_matrix_service and na_orders_service.
NA_COUNTRIES: frozenset[str] = frozenset({
    "us", "usa", "united states", "united states of america",
    "ca", "canada",
})


def safe_value(v: Any) -> Any:
    """Convert numpy arrays / scalars back to plain Python objects.

    Parquet round-trips can turn nested dicts/lists into numpy arrays.
    Calling ``.tolist()`` on them returns the original Python type.
    """
    if hasattr(v, "tolist"):
        return v.tolist()
    return v
