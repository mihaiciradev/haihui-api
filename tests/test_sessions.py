"""The API is served from api.haihuistorage.ro, a subdomain of the same
registrable domain as the frontend (www.haihuistorage.ro), so session
cookies are same-site in every environment -- SameSite=Lax works everywhere,
and is required to avoid browsers' third-party-cookie blocking silently
dropping the cookie (that blocking is keyed on registrable domain, not on
the SameSite attribute itself).
"""

from unittest.mock import patch

from app.config import get_settings
from app.core.sessions import cookie_kwargs


def test_local_env_uses_lax_and_insecure():
    settings = get_settings()
    with patch.object(settings, "env", "local"):
        kwargs = cookie_kwargs(max_age_seconds=60)
    assert kwargs["samesite"] == "lax"
    assert kwargs["secure"] is False


def test_non_local_env_uses_lax_and_secure():
    settings = get_settings()
    for env in ("staging", "production"):
        with patch.object(settings, "env", env):
            kwargs = cookie_kwargs(max_age_seconds=60)
        assert kwargs["samesite"] == "lax", f"env={env}"
        assert kwargs["secure"] is True, f"env={env}"
