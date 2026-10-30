"""
Small things several parts of Clip Radar share for talking to the outside world safely:

  protect / unprotect   sign-in tokens (Twitch, GitHub) are stored encrypted for your user account:
                        Windows DPAPI ("dpapi:"), or on macOS with a key kept in your login Keychain
                        ("keychain:"). The format ("dpapi:", "keychain:" or "plain:" + base64) is the
                        same one used before 4.4, so saved sign-ins keep working.
  ssl_context           HTTPS with certifi's certificates as well, for PCs with stale root certificates
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import ssl
import subprocess
import sys


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT = "Clip Radar", "storage-key"
_mac_key: list = []


def _keychain_key(create: bool) -> bytes:
    """macOS: Clip Radar's 32-byte storage key from the login Keychain, made the first time. b'' if the
    Keychain can't be used (then sign-ins are stored as before 4.4: base64, readable by your user only)."""
    if _mac_key:
        return _mac_key[0]
    sec = "/usr/bin/security"
    try:
        p = subprocess.run([sec, "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, stdin=subprocess.DEVNULL)
        key = bytes.fromhex(p.stdout.strip()) if p.returncode == 0 else b""
        if len(key) != 32 and create:
            key = os.urandom(32)
            p = subprocess.run([sec, "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
                                "-l", "Clip Radar sign-ins", "-w", key.hex()],
                               capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
            if p.returncode != 0:
                key = b""
    except (OSError, ValueError, subprocess.SubprocessError):
        key = b""
    if len(key) == 32:
        _mac_key[:] = [key]
        return key
    return b""


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out, i = bytearray(), 0
    while len(out) < n:
        out += hmac.new(key, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return bytes(out[:n])


def _seal(key: bytes, data: bytes) -> bytes:
    """Encrypt-then-MAC with HMAC-SHA256 (counter-mode keystream), standard library only."""
    ek, mk = hmac.new(key, b"enc", hashlib.sha256).digest(), hmac.new(key, b"mac", hashlib.sha256).digest()
    nonce = os.urandom(16)
    ct = bytes(a ^ b for a, b in zip(data, _stream(ek, nonce, len(data))))
    return nonce + ct + hmac.new(mk, nonce + ct, hashlib.sha256).digest()


def _open(key: bytes, raw: bytes) -> bytes:
    ek, mk = hmac.new(key, b"enc", hashlib.sha256).digest(), hmac.new(key, b"mac", hashlib.sha256).digest()
    nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
    if len(raw) < 48 or not hmac.compare_digest(tag, hmac.new(mk, nonce + ct, hashlib.sha256).digest()):
        raise OSError("The saved sign-in doesn't match this Mac's Keychain key")
    return bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct))))


def protect(data: bytes) -> bytes:
    if sys.platform == "darwin":
        key = _keychain_key(create=True)
        if key:
            return b"keychain:" + base64.b64encode(_seal(key, data))
    if sys.platform != "win32":
        return b"plain:" + base64.b64encode(data)
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    src = BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "Clip Radar", None, None, None, 0x1,
                                                  ctypes.byref(out)):
        raise OSError("CryptProtectData failed")
    try:
        return b"dpapi:" + base64.b64encode(ctypes.string_at(out.pbData, out.cbData))
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def unprotect(blob: bytes) -> bytes:
    kind, _, b64 = blob.partition(b":")
    raw = base64.b64decode(b64)
    if kind == b"plain":
        return raw
    if kind == b"keychain":
        key = _keychain_key(create=False)
        if not key:
            raise OSError("Couldn't read Clip Radar's key from the Keychain")
        return _open(key, raw)
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    src = BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0x1,
                                                    ctypes.byref(out)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)
