from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_ACCEPT_HEADER = "application/json;version=2025-06-24"


class InflowClientError(Exception):
    """Raised when the Inflow API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Inflow API {status_code}: {detail}")


class InflowClient:
    """Async HTTP client for the inFlow Inventory Cloud API."""

    def __init__(self) -> None:
        self._base_url = settings.inflow_api_url.rstrip("/")
        self._company_id = settings.inflow_company_id
        self._headers = {
            "Authorization": f"Bearer {settings.inflow_api_key}",
            "Accept": _ACCEPT_HEADER,
        }

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._base_url}/{self._company_id}/{path}"

    async def _handle_response(self, resp: httpx.Response) -> Any:
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            logger.warning("Inflow rate-limited – retrying after %ss", retry_after)
            await asyncio.sleep(retry_after)
            raise InflowClientError(429, "Rate limited – caller should retry")

        if resp.status_code >= 400:
            detail = resp.text[:500]
            logger.error("Inflow API error %s: %s", resp.status_code, detail)
            raise InflowClientError(resp.status_code, detail)

        if resp.status_code == 204:
            return None
        return resp.json()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._url(path), headers=self._headers, params=params)
            return await self._handle_response(resp)

    async def put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(self._url(path), headers=self._headers, json=json)
            return await self._handle_response(resp)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._url(path), headers=self._headers, json=json)
            return await self._handle_response(resp)

    async def delete(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(self._url(path), headers=self._headers)
            return await self._handle_response(resp)


# Module-level singleton
inflow_client = InflowClient()
