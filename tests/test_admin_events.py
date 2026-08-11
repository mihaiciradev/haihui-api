from datetime import UTC, datetime

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret
from app.models.audit import Event
from app.models.enums import ActorType
from app.models.user import User


async def _create_admin_and_login(client, db, email="admin@haihui.ro") -> None:
    import pyotp

    secret = generate_totp_secret()
    admin = User(
        email=email,
        is_admin=True,
        admin_password_hash=hash_secret("supersecret1"),
        admin_totp_secret=secret,
        admin_totp_confirmed_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.commit()

    login = await client.post(
        "/admin/auth/login", json={"email": email, "password": "supersecret1"}
    )
    assert login.status_code == 200
    verify = await client.post("/admin/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200


async def test_list_events_requires_admin_session(client):
    resp = await client.get("/admin/events")
    assert resp.status_code == 401


async def test_list_events_returns_newest_first(client, db):
    await _create_admin_and_login(client, db)

    import uuid

    entity_id = uuid.uuid4()
    for action in ("first_action", "second_action"):
        db.add(
            Event(
                actor_type=ActorType.system,
                actor_id=None,
                entity_type="test_entity",
                entity_id=entity_id,
                action=action,
                payload={},
            )
        )
        # separate transactions so Postgres now() actually advances between
        # rows -- both inserts in one transaction would tie on created_at
        await db.commit()

    resp = await client.get("/admin/events?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["action"] == "second_action"
    assert body[1]["action"] == "first_action"
