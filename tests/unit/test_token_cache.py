"""Unit tests for Windows DPAPI encryption and ProtectedTokenCache persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.auth.token_cache import ProtectedTokenCache, dpapi_protect, dpapi_unprotect


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI test requires Windows")
def test_dpapi_encrypt_decrypt_roundtrip_hides_plaintext() -> None:
    secret_payload = b'{"AccessToken": {"key": {"secret": "eyJ.super_sensitive_token.sig"}}}'
    encrypted = dpapi_protect(secret_payload)

    assert encrypted != secret_payload
    assert b"super_sensitive_token" not in encrypted
    assert dpapi_unprotect(encrypted) == secret_payload


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI test requires Windows")
def test_protected_token_cache_persists_encrypted_and_clears(tmp_path: Path) -> None:
    cache_file = tmp_path / "auth" / "msal_token_cache.bin"
    cache = ProtectedTokenCache(cache_file)

    sample_state = json.dumps(
        {
            "Account": {
                "acc-1": {
                    "home_account_id": "oid.tid",
                    "environment": "login.microsoftonline.com",
                    "realm": "tid",
                    "local_account_id": "oid",
                    "username": "john.doe@contoso.com",
                    "authority_type": "MSSTS",
                }
            },
            "RefreshToken": {
                "rt-1": {
                    "secret": "sensitive_refresh_token_value_999",
                    "credential_type": "RefreshToken",
                }
            },
        }
    )
    cache.msal_cache.deserialize(sample_state)
    cache.save(force=True)

    assert cache_file.exists()
    raw_disk_bytes = cache_file.read_bytes()
    assert b"sensitive_refresh_token_value_999" not in raw_disk_bytes
    assert b"john.doe@contoso.com" not in raw_disk_bytes

    # Reload into a fresh instance simulating app restart
    reloaded = ProtectedTokenCache(cache_file)
    restored_data = json.loads(reloaded.msal_cache.serialize())
    assert "acc-1" in restored_data.get("Account", {})

    # Clear removes both disk file and in-memory state
    reloaded.clear()
    assert not cache_file.exists()
    assert json.loads(reloaded.msal_cache.serialize()).get("Account", {}) == {}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI test requires Windows")
def test_protected_token_cache_recovers_from_corrupt_file(tmp_path: Path) -> None:
    cache_file = tmp_path / "auth" / "corrupt_cache.bin"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"not-valid-dpapi-ciphertext")

    cache = ProtectedTokenCache(cache_file)
    assert json.loads(cache.msal_cache.serialize()).get("Account", {}) == {}
