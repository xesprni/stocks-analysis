from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx


class HttpClient:
    def __init__(self, timeout_seconds: int, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HttpClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/xml,application/xml,text/plain,*/*",
            },
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_text(self, url: str, params: Optional[Dict[str, str]] = None) -> str:
        response = await self._request(url=url, params=params)
        return response.text

    async def get_json(self, url: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        text = await self.get_text(url=url, params=params)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(text[start : end + 1])

    async def _request(self, url: str, params: Optional[Dict[str, str]] = None) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("HttpClient must be used as an async context manager.")
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response
