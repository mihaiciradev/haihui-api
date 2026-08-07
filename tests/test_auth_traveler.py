from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import generate_opaque_token
from app.models.magic_link import MagicLinkToken


async def test_magic_link_request_creates_token(client, db):
    resp = await client.post("/auth/magic-link", json={"email": "traveler@example.com"})
    assert resp.status_code == 200

    result = await db.execute(
        select(MagicLinkToken).where(MagicLinkToken.email == "traveler@example.com")
    )
    assert result.scalar_one_or_none() is not None


async def test_magic_link_verify_happy_path(client, db):
    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email="traveler@example.com",
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    await db.commit()

    resp = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "hh_traveler_session" in resp.cookies


async def test_magic_link_verify_rejects_unknown_token(client):
    resp = await client.post("/auth/magic-link/verify", json={"token": "totally-bogus-token-value"})
    assert resp.status_code == 400


async def test_magic_link_verify_rejects_expired_token(client, db):
    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email="expired@example.com",
            token_hash=hashed,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db.commit()

    resp = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert resp.status_code == 400


async def test_magic_link_verify_rejects_reused_token(client, db):
    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email="reuse@example.com",
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    await db.commit()

    first = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert first.status_code == 200

    second = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert second.status_code == 400


async def test_me_requires_session(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_returns_identity_after_login(client, db):
    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email="me-check@example.com",
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    await db.commit()

    verify = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert verify.status_code == 200

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "me-check@example.com"
