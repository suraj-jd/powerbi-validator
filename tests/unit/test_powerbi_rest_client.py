"""Unit tests for PowerBIRestClient using httpx.MockTransport."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from app.core.config import AppConfig
from app.core.logging_config import setup_logging
from app.integrations.powerbi.rest_client import PowerBIHttpError, PowerBIRestClient


def test_rest_client_attaches_bearer_token_and_never_logs_it(tmp_path: Path) -> None:
    log_path = setup_logging(AppConfig(log_level="DEBUG"), tmp_path / "logs", include_console=False)
    secret_token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.superSecretPowerBiToken999"
    captured_auth_header: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_header.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"value": [{"id": "ws-1", "name": "Analytics"}]})

    client = PowerBIRestClient(
        token_provider=lambda: secret_token,
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = client.get_json("/groups")
        assert payload["value"][0]["name"] == "Analytics"
        assert captured_auth_header == [f"Bearer {secret_token}"]
    finally:
        client.close()

    for h in logging.getLogger().handlers:
        h.flush()
    assert secret_token not in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "status_code,expected_phrase",
    [
        (401, "401"),
        (403, "403"),
        (404, "404"),
        (503, "503"),
    ],
)
def test_rest_client_maps_http_error_statuses_clearly(status_code: int, expected_phrase: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"code": "PowerBIError", "message": "Detailed API reason"}},
        )

    client = PowerBIRestClient(
        token_provider=lambda: "tok",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(PowerBIHttpError) as exc_info:
            client.get_json("/groups")
        assert exc_info.value.status_code == status_code
        assert expected_phrase in exc_info.value.user_message
    finally:
        client.close()


def test_rest_client_retries_on_429_respecting_retry_after() -> None:
    attempts = {"count": 0}
    slept: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json={"value": []})

    client = PowerBIRestClient(
        token_provider=lambda: "tok",
        max_retries=2,
        transport=httpx.MockTransport(handler),
        sleep_fn=slept.append,
    )
    try:
        result = client.get_json("/groups")
        assert result == {"value": []}
        assert attempts["count"] == 2
        assert slept == [1.5]
    finally:
        client.close()


def test_rest_client_raises_429_after_retries_exhausted() -> None:
    slept: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"})

    client = PowerBIRestClient(
        token_provider=lambda: "tok",
        max_retries=1,
        transport=httpx.MockTransport(handler),
        sleep_fn=slept.append,
    )
    try:
        with pytest.raises(PowerBIHttpError) as exc_info:
            client.get_json("/groups")
        assert exc_info.value.status_code == 429
        assert slept == [2.0]
    finally:
        client.close()


def test_rest_client_maps_timeout_to_friendly_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timed out", request=request)

    client = PowerBIRestClient(
        token_provider=lambda: "tok",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(PowerBIHttpError) as exc_info:
            client.get_json("/groups")
        assert "timed out" in exc_info.value.user_message.lower()
    finally:
        client.close()


def test_rest_client_post_and_get_methods() -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"status": "created", "id": 101})
        return httpx.Response(200, json={"status": "ok"})

    client = PowerBIRestClient(
        token_provider=lambda: "auth_token_xyz",
        transport=httpx.MockTransport(handler),
    )
    try:
        # 1. Test client.post
        resp_post = client.post("/items", json={"name": "test_item"}, timeout=15)
        assert isinstance(resp_post, httpx.Response)
        assert resp_post.status_code == 200
        assert resp_post.json() == {"status": "created", "id": 101}
        assert captured[0].method == "POST"
        assert captured[0].headers["Authorization"] == "Bearer auth_token_xyz"

        # 2. Test client.get
        resp_get = client.get("/items/101")
        assert isinstance(resp_get, httpx.Response)
        assert resp_get.status_code == 200
        assert resp_get.json() == {"status": "ok"}
        assert captured[1].method == "GET"

        # 3. Test client.post_json
        json_res = client.post_json("/items", json_body={"name": "json_item"})
        assert json_res == {"status": "created", "id": 101}
    finally:
        client.close()
