"""
Password hashing. Uses the `bcrypt` library directly (not passlib — passlib's
bcrypt backend detection is broken against bcrypt>=4.0 in some environments)
if available, otherwise falls back to Python's built-in hashlib.scrypt so the
database layer is testable anywhere. Production builds should keep `bcrypt`
in requirements.txt — it's the recommended algorithm per the Phase 1
security architecture.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

try:
    import bcrypt as _bcrypt

    _HAS_BCRYPT = True
except ImportError:  # pragma: no cover - fallback path
    _HAS_BCRYPT = False


_SCRYPT_PREFIX = "scrypt$"
_BCRYPT_MAX_BYTES = 72  # bcrypt silently ignores bytes beyond this; we reject instead


def hash_password(plain_password: str) -> str:
    if _HAS_BCRYPT:
        pw_bytes = plain_password.encode("utf-8")
        if len(pw_bytes) > _BCRYPT_MAX_BYTES:
            raise ValueError(f"Password too long for bcrypt ({_BCRYPT_MAX_BYTES} byte limit).")
        return _bcrypt.hashpw(pw_bytes, _bcrypt.gensalt()).decode("utf-8")
    # Fallback: scrypt with a random salt, encoded so it round-trips cleanly.
    salt = os.urandom(16)
    derived = hashlib.scrypt(plain_password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return _SCRYPT_PREFIX + base64.b64encode(salt).decode() + "$" + base64.b64encode(derived).decode()


def verify_password(plain_password: str, password_hash: str) -> bool:
    if password_hash.startswith(_SCRYPT_PREFIX):
        try:
            _, salt_b64, derived_b64 = password_hash.split("$", 2)
        except ValueError:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(derived_b64)
        candidate = hashlib.scrypt(plain_password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(candidate, expected)
    if _HAS_BCRYPT:
        try:
            return _bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False
    return False  # pragma: no cover - hash format from an unavailable backend
