"""Windows DPAPI-protected MSAL token cache persistence (BRD Section 8.2).

Tokens are encrypted using the current Windows user's DPAPI key via
`crypt32.CryptProtectData` and stored outside SQLite. Raw tokens are never
written in plaintext and never logged.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from pathlib import Path

import msal

from app.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def dpapi_protect(plaintext: bytes, *, description: str = "PowerBIValidationToolTokenCache") -> bytes:
    """Encrypt bytes with Windows DPAPI scoped to the current Windows user."""
    if sys.platform != "win32":
        raise AuthenticationError(
            "Windows DPAPI token protection is only supported on Windows.",
            user_message="Secure token cache protection requires Windows DPAPI.",
        )
    if not plaintext:
        return b""

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    in_blob, _buf = _make_blob(plaintext)
    out_blob = _DATA_BLOB()

    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        description,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        error_code = ctypes.get_last_error()
        raise AuthenticationError(
            f"Windows DPAPI CryptProtectData failed (error={error_code}).",
            user_message="Could not encrypt the local authentication cache.",
        )

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def dpapi_unprotect(ciphertext: bytes) -> bytes:
    """Decrypt bytes previously encrypted by Windows DPAPI for the current user."""
    if sys.platform != "win32":
        raise AuthenticationError(
            "Windows DPAPI token protection is only supported on Windows.",
            user_message="Secure token cache protection requires Windows DPAPI.",
        )
    if not ciphertext:
        return b""

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    in_blob, _buf = _make_blob(ciphertext)
    out_blob = _DATA_BLOB()
    desc_ptr = wintypes.LPWSTR()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        ctypes.byref(desc_ptr),
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        error_code = ctypes.get_last_error()
        raise AuthenticationError(
            f"Windows DPAPI CryptUnprotectData failed (error={error_code}).",
            user_message="Saved authentication session could not be decrypted. Please sign in again.",
        )

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
        if desc_ptr:
            kernel32.LocalFree(desc_ptr)


class ProtectedTokenCache:
    """DPAPI-encrypted persistent wrapper around `msal.SerializableTokenCache`."""

    def __init__(self, cache_path: Path) -> None:
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = msal.SerializableTokenCache()
        self.load()

    @property
    def msal_cache(self) -> msal.SerializableTokenCache:
        return self._cache

    def load(self) -> bool:
        """Load and decrypt an existing token cache if present.

        Returns True if a cache was restored, False if empty or reset after corruption.
        """
        if not self.cache_path.exists():
            return False

        try:
            encrypted = self.cache_path.read_bytes()
            if not encrypted:
                return False
            decrypted = dpapi_unprotect(encrypted).decode("utf-8")
            self._cache.deserialize(decrypted)
            logger.info("Loaded DPAPI-protected MSAL token cache from %s", self.cache_path)
            return True
        except Exception as exc:
            logger.warning(
                "Could not restore protected token cache at %s (%s); starting with empty cache.",
                self.cache_path,
                type(exc).__name__,
            )
            self._cache = msal.SerializableTokenCache()
            return False

    def save(self, *, force: bool = False) -> None:
        """Encrypt and persist the token cache atomically when state has changed."""
        if not force and not self._cache.has_state_changed:
            return

        serialized = self._cache.serialize().encode("utf-8")
        encrypted = dpapi_protect(serialized)

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.cache_path.with_suffix(f"{self.cache_path.suffix}.tmp")
        try:
            tmp_path.write_bytes(encrypted)
            os.replace(tmp_path, self.cache_path)
            logger.debug("Saved DPAPI-protected MSAL token cache to %s", self.cache_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def clear(self) -> None:
        """Wipe in-memory MSAL cache and remove the protected cache file from disk."""
        self._cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                self.cache_path.unlink()
                logger.info("Cleared protected MSAL token cache at %s", self.cache_path)
            except OSError as exc:
                raise AuthenticationError(
                    f"Failed to delete protected token cache {self.cache_path}: {exc}",
                    user_message="Could not clear the saved authentication cache from disk.",
                ) from exc
