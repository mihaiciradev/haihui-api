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
    """The API is served from api.haihuistorage.ro, a subdomain of the same
    registrable domain as the frontend (www.haihuistorage.ro) -- same "site"
    per browser cookie rules, even though it's a different origin. That
    means SameSite=Lax works in production too, not just locally, and
    critically it's what stops browsers' third-party-cookie blocking from
    dropping the cookie entirely (that blocking is keyed on registrable
    domain, not origin -- SameSite=None cookies on a different registrable
    domain get treated as third-party and silently discarded by an
    increasing number of browsers regardless of the SameSite attribute).
    """
    settings = get_settings()
    return {
        "httponly": True,
        "secure": settings.env != "local",
        "samesite": "lax",
        "max_age": max_age_seconds,
        "path": "/",
    }
