from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_ACCEPT_HEADER = "application/json;version=2025-06-24"

# Stay safely under the Inflow API's 60 requests/minute limit
_MAX_REQUESTS = 45
_WINDOW_SECONDS = 60
_MAX_RETRIES = 3


class InflowClientError(Exception):
    """Raised when the Inflow API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Inflow API {status_code}: {detail}")


class _RateLimiter:
    """Sliding-window rate limiter: at most `max_requests` in `window` seconds."""

    def __init__(self, max_requests: int = _MAX_REQUESTS, window: float = _WINDOW_SECONDS) -> None:
        self._max = max_requests
        self._window = window
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Drop timestamps outside the window
            while self._timestamps and now - self._timestamps[0] >= self._window:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max:
                wait = self._window - (now - self._timestamps[0])
                logger.info("Rate limiter: waiting %.1fs before next request", wait)
                await asyncio.sleep(wait)
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self._window:
                    self._timestamps.popleft()

            self._timestamps.append(time.monotonic())


class InflowClient:
    """Async HTTP client for the inFlow Inventory Cloud API."""

    def __init__(self) -> None:
        self._base_url = settings.inflow_api_url.rstrip("/")
        self._company_id = settings.inflow_company_id
        self._headers = {
            "Authorization": f"Bearer {settings.inflow_api_key}",
            "Accept": _ACCEPT_HEADER,
        }
        self._rate_limiter = _RateLimiter()

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._base_url}/{self._company_id}/{path}"

    async def _handle_response(self, resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            detail = resp.text[:500]
            logger.error("Inflow API error %s: %s", resp.status_code, detail)
            raise InflowClientError(resp.status_code, detail)

        if resp.status_code == 204:
            return None
        return resp.json()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Send a request with rate-limiting, retry on 429, and transport error handling."""
        for attempt in range(_MAX_RETRIES):
            await self._rate_limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.request(
                        method, self._url(path), headers=self._headers,
                        params=params, json=json,
                    )
            except httpx.TimeoutException:
                raise InflowClientError(504, f"Request to Inflow API timed out: {method} {path}")
            except httpx.HTTPError as exc:
                raise InflowClientError(502, f"Could not reach Inflow API: {exc}")

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                logger.warning(
                    "Inflow rate-limited (attempt %d/%d) – retrying after %ds",
                    attempt + 1, _MAX_RETRIES, retry_after,
                )
                await asyncio.sleep(retry_after)
                continue

            return resp

        # All retries exhausted on 429
        raise InflowClientError(429, "Inflow API rate limit exceeded after retries")

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._request("GET", path, params=params)
        return await self._handle_response(resp)

    async def get_paged(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[Any, int | None]:
        """GET that also returns the X-listCount header value."""
        resp = await self._request("GET", path, params=params)
        list_count = resp.headers.get("X-listCount")
        body = await self._handle_response(resp)
        return body, int(list_count) if list_count else None

    async def put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._request("PUT", path, json=json)
        return await self._handle_response(resp)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._request("POST", path, json=json)
        return await self._handle_response(resp)

    async def delete(self, path: str) -> Any:
        resp = await self._request("DELETE", path)
        return await self._handle_response(resp)


# Module-level singleton
inflow_client = InflowClient()
