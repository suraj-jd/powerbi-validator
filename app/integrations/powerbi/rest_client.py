"""Reusable HTTP client for Microsoft Power BI Service REST APIs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.exceptions import PowerBIApiError

logger = logging.getLogger(__name__)

POWERBI_API_BASE_URL = "https://api.powerbi.com/v1.0/myorg"


class PowerBIHttpError(PowerBIApiError):
    """Typed Power BI REST API error carrying HTTP status and API error code."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        user_message: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds


def _extract_pbi_error_detail(response: httpx.Response) -> tuple[str | None, str]:
    """Parse Power BI's standard `{"error": {"code": ..., "message": ...}}` error body."""
    try:
        payload = response.json()
    except ValueError:
        return None, (response.text or "").strip()[:300]

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "") or None
            message = str(err.get("message") or "")
            pbi_info = err.get("pbi.error")
            if not message and isinstance(pbi_info, dict):
                code = code or str(pbi_info.get("code") or "") or None
                details = pbi_info.get("details")
                if isinstance(details, list) and details:
                    first = details[0]
                    if isinstance(first, dict):
                        message = str(first.get("detail", {}).get("value") or "")
            return code, message.strip()
    return None, ""


def _parse_retry_after(header_value: str | None) -> float | None:
    if not header_value:
        return None
    try:
        seconds = float(header_value.strip())
        return max(0.0, min(seconds, 60.0))
    except ValueError:
        return None


class PowerBIRestClient:
    """Authenticated HTTP client for Power BI REST API calls with safe retries and timeouts."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        base_url: str = POWERBI_API_BASE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
        self._max_retries = max(0, max_retries)
        self._sleep = sleep_fn
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        json_body: Any = None,
        timeout: float | httpx.Timeout | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Issue an authenticated HTTP request with retries, 429 throttling backoff, and error mapping."""
        normalized_path = path if path.startswith("/") else f"/{path}"
        token = self._token_provider()
        req_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        body = json if json is not None else json_body
        req_timeout = httpx.Timeout(timeout) if isinstance(timeout, (int, float)) else (timeout or self._timeout)

        attempt = 0
        while True:
            try:
                logger.debug("Power BI REST %s %s (attempt=%d)", method, normalized_path, attempt + 1)
                response = self._client.request(
                    method,
                    normalized_path,
                    params=params,
                    json=body,
                    headers=req_headers,
                    timeout=req_timeout,
                )
            except httpx.TimeoutException as exc:
                raise PowerBIHttpError(
                    f"Power BI API request timed out for {method} {normalized_path}.",
                    user_message=(
                        "The Power BI Service request timed out. Please check your network "
                        "connection and try again."
                    ),
                ) from exc
            except httpx.RequestError as exc:
                raise PowerBIHttpError(
                    f"Network error contacting Power BI Service ({type(exc).__name__}).",
                    user_message=(
                        "Could not reach the Power BI Service. Please check your internet "
                        "connection, VPN, or corporate proxy settings."
                    ),
                ) from exc

            status = response.status_code

            # Handle API throttling (HTTP 429) using Retry-After / bounded backoff
            if status == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if attempt < self._max_retries:
                    delay = retry_after if retry_after is not None else float(2**attempt)
                    logger.warning(
                        "Power BI API throttled (429) on %s; retrying in %.1fs.",
                        normalized_path,
                        delay,
                    )
                    self._sleep(delay)
                    attempt += 1
                    continue
                raise PowerBIHttpError(
                    f"Power BI API rate limit exceeded (429) for {normalized_path}.",
                    status_code=429,
                    error_code="TooManyRequests",
                    retry_after_seconds=retry_after,
                    user_message=(
                        "Power BI Service is currently throttling requests (HTTP 429). "
                        "Please wait a moment and try again."
                    ),
                )

            if 200 <= status < 300:
                return response

            error_code, detail = _extract_pbi_error_detail(response)
            raise self._map_http_error(status, normalized_path, error_code, detail)

    def post(
        self,
        path: str,
        *,
        json: Any = None,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Issue an authenticated POST request and return the raw httpx.Response."""
        body = json if json is not None else json_body
        return self.request("POST", path, json=body, params=params, timeout=timeout)

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Issue an authenticated GET request and return the raw httpx.Response."""
        return self.request("GET", path, params=params, timeout=timeout)

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Issue an authenticated GET request and return parsed JSON."""
        resp = self.get(path, params=params, timeout=timeout)
        if not resp.content:
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"value": data}
        except ValueError as exc:
            raise PowerBIHttpError(
                f"Power BI API returned non-JSON payload for GET {path}.",
                status_code=resp.status_code,
                user_message="Power BI Service returned an unexpected response format.",
            ) from exc

    def post_json(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Issue an authenticated POST request and return parsed JSON."""
        body = json if json is not None else json_body
        resp = self.post(path, json=body, params=params, timeout=timeout)
        if not resp.content:
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"value": data}
        except ValueError as exc:
            raise PowerBIHttpError(
                f"Power BI API returned non-JSON payload for POST {path}.",
                status_code=resp.status_code,
                user_message="Power BI Service returned an unexpected response format.",
            ) from exc

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        resp = self.request(method, path, params=params, json=json_body, timeout=timeout)
        if not resp.content:
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"value": data}
        except ValueError as exc:
            raise PowerBIHttpError(
                f"Power BI API returned non-JSON payload for {method} {path}.",
                status_code=resp.status_code,
                user_message="Power BI Service returned an unexpected response format.",
            ) from exc

    @staticmethod
    def _map_http_error(
        status: int,
        path: str,
        error_code: str | None,
        detail: str,
    ) -> PowerBIHttpError:
        suffix = f" ({error_code})" if error_code else ""
        if status == 401:
            return PowerBIHttpError(
                f"HTTP 401 Unauthorized on {path}{suffix}: {detail}",
                status_code=401,
                error_code=error_code,
                user_message=(
                    "Your Microsoft session is unauthorized or expired (HTTP 401). "
                    "Please sign in again."
                ),
            )
        if status == 403:
            return PowerBIHttpError(
                f"HTTP 403 Forbidden on {path}{suffix}: {detail}",
                status_code=403,
                error_code=error_code,
                user_message=(
                    "Access denied by Power BI (HTTP 403). Verify that your signed-in account "
                    "has workspace/dataset permissions and that tenant Power BI API access is enabled."
                ),
            )
        if status == 404:
            return PowerBIHttpError(
                f"HTTP 404 Not Found on {path}{suffix}: {detail}",
                status_code=404,
                error_code=error_code,
                user_message=(
                    "The requested Power BI workspace, dataset, or report was not found (HTTP 404), "
                    "or your account does not have access to it."
                ),
            )
        if 500 <= status < 600:
            return PowerBIHttpError(
                f"HTTP {status} Power BI Service error on {path}{suffix}: {detail}",
                status_code=status,
                error_code=error_code,
                user_message=(
                    f"Power BI Service returned a temporary server error (HTTP {status}). "
                    "Please try again shortly."
                ),
            )
        return PowerBIHttpError(
            f"HTTP {status} error on {path}{suffix}: {detail}",
            status_code=status,
            error_code=error_code,
            user_message=f"Power BI Service request failed (HTTP {status}){suffix}.",
        )
