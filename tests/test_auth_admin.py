from datetime import UTC

import pyotp

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret
from app.models.user import User


async def test_admin_login_requires_totp_step(client, db):
    from datetime import datetime

    secret = generate_totp_secret()
    admin = User(
        email="admin@haihui.ro",
        is_admin=True,
        admin_password_hash=hash_secret("supersecret1"),
        admin_totp_secret=secret,
        admin_totp_confirmed_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.commit()

    resp = await client.post(
        "/admin/auth/login", json={"email": "admin@haihui.ro", "password": "supersecret1"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "totp_required"
    assert "hh_admin_pending" in resp.cookies
    assert "hh_admin_session" not in resp.cookies

    code = pyotp.TOTP(secret).now()
    resp2 = await client.post("/admin/auth/totp/verify", json={"code": code})
    assert resp2.status_code == 200
    assert "hh_admin_session" in resp2.cookies


async def test_admin_login_rejects_account_without_totp_confirmed(client, db):
    secret = generate_totp_secret()
    admin = User(
        email="unconfirmed@haihui.ro",
        is_admin=True,
        admin_password_hash=hash_secret("supersecret1"),
        admin_totp_secret=secret,
        admin_totp_confirmed_at=None,
    )
    db.add(admin)
    await db.commit()

    resp = await client.post(
        "/admin/auth/login", json={"email": "unconfirmed@haihui.ro", "password": "supersecret1"}
    )
    assert resp.status_code == 401


async def test_admin_login_rejects_wrong_password(client, db):
    from datetime import datetime

    admin = User(
        email="admin2@haihui.ro",
        is_admin=True,
        admin_password_hash=hash_secret("supersecret1"),
        admin_totp_secret=generate_totp_secret(),
        admin_totp_confirmed_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.commit()

    resp = await client.post(
        "/admin/auth/login", json={"email": "admin2@haihui.ro", "password": "wrongpass"}
    )
    assert resp.status_code == 401
