from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret
from app.models.city import City
from app.models.location import Location, LocationHours, LocationItemType
from app.models.staff import LocationLoginToken, StaffMember
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


async def _seed_city(db, slug="brasov") -> City:
    city = City(slug=slug, name_ro="Brașov", name_en="Brasov")
    db.add(city)
    await db.commit()
    return city


def _create_payload(city_slug="brasov", name="Suvenire Test"):
    return {
        "name": name,
        "city_slug": city_slug,
        "address": "Str. Test 1",
        "lat": 45.6,
        "lng": 25.6,
        "item_types": [
            {"item_type": "bag", "daily_capacity": 20},
            {"item_type": "trolley", "daily_capacity": 10},
        ],
        "owner_name": "Owner Test",
        "owner_pin": "1234",
    }


async def test_create_location_requires_admin_session(client):
    resp = await client.post("/admin/locations", json=_create_payload())
    assert resp.status_code == 401


async def test_create_location_happy_path(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)

    resp = await client.post("/admin/locations", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "suvenire-test"
    assert len(body["location_login_token"]) >= 16

    result = await db.execute(select(Location).where(Location.slug == "suvenire-test"))
    location = result.scalar_one()
    assert location.revenue_share_pct == 40  # default

    item_types = (
        (
            await db.execute(
                select(LocationItemType).where(LocationItemType.location_id == location.id)
            )
        )
        .scalars()
        .all()
    )
    assert {i.item_type.value for i in item_types} == {"bag", "trolley"}

    hours = (
        (await db.execute(select(LocationHours).where(LocationHours.location_id == location.id)))
        .scalars()
        .all()
    )
    assert len(hours) == 7  # default weekly template

    login_token = (
        await db.execute(
            select(LocationLoginToken).where(LocationLoginToken.location_id == location.id)
        )
    ).scalar_one()
    assert login_token.revoked_at is None

    owner = (
        await db.execute(select(StaffMember).where(StaffMember.location_id == location.id))
    ).scalar_one()
    assert owner.role.value == "owner"
    assert owner.name == "Owner Test"


async def test_create_location_rejects_unknown_city(client, db):
    await _create_admin_and_login(client, db)

    resp = await client.post("/admin/locations", json=_create_payload(city_slug="nowhere"))
    assert resp.status_code == 400


async def test_create_location_rejects_duplicate_item_type(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)

    payload = _create_payload()
    payload["item_types"] = [
        {"item_type": "bag", "daily_capacity": 10},
        {"item_type": "bag", "daily_capacity": 20},
    ]
    resp = await client.post("/admin/locations", json=payload)
    assert resp.status_code == 422


async def test_create_location_slug_collision_gets_suffixed(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)

    first = await client.post("/admin/locations", json=_create_payload())
    assert first.status_code == 201
    assert first.json()["slug"] == "suvenire-test"

    second = await client.post("/admin/locations", json=_create_payload())
    assert second.status_code == 201
    assert second.json()["slug"] == "suvenire-test-2"


async def test_list_locations_requires_admin_session(client):
    resp = await client.get("/admin/locations")
    assert resp.status_code == 401


async def test_list_locations_returns_created_locations(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    await client.post("/admin/locations", json=_create_payload())

    resp = await client.get("/admin/locations")
    assert resp.status_code == 200
    names = [loc["name"] for loc in resp.json()]
    assert "Suvenire Test" in names
