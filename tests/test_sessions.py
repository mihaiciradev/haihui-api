"""Frontend and API are on different registrable domains in every deployed
environment (custom domain vs *.fly.dev), so session cookies must be
SameSite=None; Secure there -- SameSite=Lax silently drops the cookie on
cross-site fetch/XHR, which looks like "requests succeed but the user is
never logged in" rather than a loud error.
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


def test_non_local_env_uses_none_and_secure():
    settings = get_settings()
    for env in ("staging", "production"):
        with patch.object(settings, "env", env):
            kwargs = cookie_kwargs(max_age_seconds=60)
        assert kwargs["samesite"] == "none", f"env={env}"
        assert kwargs["secure"] is True, f"env={env}"
