"""Server-signed, httpOnly session cookies for the three actor types.

Not a JWT: fixed alg (HMAC-SHA256 via itsdangerous), no client-chosen header,
and payload is minimal (ids + role only, no PII). Booking tokens and location
login tokens are a separate, DB-revocable mechanism (see core/security.py) —
these session cookies are for "who is currently logged in", not for the
QR/PIN artifacts themselves.
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

TRAVELER_COOKIE = "hh_traveler_session"
STAFF_COOKIE = "hh_staff_session"
ADMIN_COOKIE = "hh_admin_session"


def _serializer(salt: str) -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


def issue_session(salt: str, payload: dict) -> str:
    return _serializer(salt).dumps(payload)


def read_session(salt: str, token: str, max_age_seconds: int) -> dict | None:
    try:
        return _serializer(salt).loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def cookie_kwargs(*, max_age_seconds: int) -> dict:
    settings = get_settings()
    return {
        "httponly": True,
        "secure": settings.env != "local",
        "samesite": "lax",
        "max_age": max_age_seconds,
        "path": "/",
    }
