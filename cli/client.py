"""HTTP client wrapper for the Quant API."""

from __future__ import annotations

from typing import Any

import httpx

from cli.config import get_api_url

_TIMEOUT = 30.0


def _url(path: str) -> str:
    return f"{get_api_url()}{path}"


def get(path: str, params: dict[str, Any] | None = None) -> dict:
    """Sync GET request. Returns parsed JSON or exits on error."""
    try:
        resp = httpx.get(_url(path), params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise SystemExit(f"Connection refused — is the API running at {get_api_url()}?")
    except httpx.HTTPStatusError as exc:
        raise SystemExit(f"API error {exc.response.status_code}: {exc.response.text}")
    except httpx.TimeoutException:
        raise SystemExit(f"Request timed out after {_TIMEOUT}s")


def post(path: str, json_body: dict[str, Any] | None = None) -> dict:
    """Sync POST request. Returns parsed JSON or exits on error."""
    try:
        resp = httpx.post(_url(path), json=json_body, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise SystemExit(f"Connection refused — is the API running at {get_api_url()}?")
    except httpx.HTTPStatusError as exc:
        raise SystemExit(f"API error {exc.response.status_code}: {exc.response.text}")
    except httpx.TimeoutException:
        raise SystemExit(f"Request timed out after {_TIMEOUT}s")
