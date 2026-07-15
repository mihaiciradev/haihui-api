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
    """Frontend and API are on different registrable domains in every
    non-local environment (Vercel/custom domain vs *.fly.dev), which makes
    every request cross-site rather than merely cross-origin. Browsers will
    not send/accept SameSite=Lax cookies on cross-site fetch/XHR, so those
    environments need SameSite=None (which itself requires Secure). Locally,
    frontend and API differ only by port on localhost -- same "site" per the
    registrable-domain definition -- so Lax works and lets cookies flow over
    plain http during dev.
    """
    settings = get_settings()
    cross_site = settings.env != "local"
    return {
        "httponly": True,
        "secure": cross_site,
        "samesite": "none" if cross_site else "lax",
        "max_age": max_age_seconds,
        "path": "/",
    }
