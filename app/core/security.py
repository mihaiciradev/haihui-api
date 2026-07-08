"""Password/PIN hashing (argon2id) and opaque CSPRNG tokens.

Booking tokens and location login tokens are >=128-bit CSPRNG values, stored
only as a hash. The raw value is never persisted and is shown to the caller
exactly once (embedded in a QR / printed card / link).
"""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings

_ph = PasswordHasher()


def hash_secret(raw: str) -> str:
    """Argon2id hash for PINs and admin passwords."""
    return _ph.hash(raw)


def verify_secret(raw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, raw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_opaque_token(n_bytes: int | None = None) -> tuple[str, str]:
    """Returns (raw_token, token_hash). Store only the hash; hand the raw value
    to the caller once. Hashing is a fast, deterministic SHA-256 keyed with the
    app secret (not argon2 — these are high-entropy random tokens, not
    low-entropy human secrets, so a fast keyed hash is appropriate and lets us
    look them up by exact match).
    """
    settings = get_settings()
    raw = secrets.token_urlsafe(n_bytes or settings.booking_token_bytes)
    return raw, hash_opaque_token(raw)


def hash_opaque_token(raw: str) -> str:
    settings = get_settings()
    return hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
