from datetime import UTC, datetime

import pyotp

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret
from app.models.user import User


async def test_admin_login_requires_totp_step(client, db):
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


async def _create_confirmed_admin(db, email: str, password: str) -> str:
    secret = generate_totp_secret()
    admin = User(
        email=email,
        is_admin=True,
        admin_password_hash=hash_secret(password),
        admin_totp_secret=secret,
        admin_totp_confirmed_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.commit()
    return secret


async def test_admin_me_requires_session(client):
    resp = await client.get("/admin/me")
    assert resp.status_code == 401


async def test_admin_me_returns_identity_after_full_login(client, db):
    secret = await _create_confirmed_admin(db, "me-check@haihui.ro", "supersecret1")

    login = await client.post(
        "/admin/auth/login", json={"email": "me-check@haihui.ro", "password": "supersecret1"}
    )
    assert login.status_code == 200

    verify = await client.post(
        "/admin/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()}
    )
    assert verify.status_code == 200

    me = await client.get("/admin/me")
    assert me.status_code == 200
    assert me.json()["email"] == "me-check@haihui.ro"


async def test_admin_me_rejects_pending_only_session(client, db):
    await _create_confirmed_admin(db, "pending-only@haihui.ro", "supersecret1")

    login = await client.post(
        "/admin/auth/login", json={"email": "pending-only@haihui.ro", "password": "supersecret1"}
    )
    assert login.status_code == 200
    assert "hh_admin_pending" in login.cookies

    # Only the pending 2FA cookie exists -- /admin/me must not treat that as
    # a real session.
    me = await client.get("/admin/me")
    assert me.status_code == 401


async def test_admin_totp_locks_out_after_five_failures(client, db):
    secret = await _create_confirmed_admin(db, "lockout@haihui.ro", "supersecret1")

    login = await client.post(
        "/admin/auth/login", json={"email": "lockout@haihui.ro", "password": "supersecret1"}
    )
    assert login.status_code == 200

    for _ in range(5):
        resp = await client.post("/admin/auth/totp/verify", json={"code": "000000"})
        assert resp.status_code == 401

    # 6th attempt, even with the correct code, must be locked out.
    resp = await client.post(
        "/admin/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()}
    )
    assert resp.status_code == 423
