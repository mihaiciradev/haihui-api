from datetime import date, timedelta

from app.core.security import generate_opaque_token, hash_secret
from app.models.city import City
from app.models.enums import ItemType, LocationStatus, StaffRole
from app.models.location import Location, LocationHours, LocationItemType
from app.models.staff import LocationLoginToken, StaffMember


async def _seed_location_with_owner_and_staff(db):
    city = City(slug="brasov", name_ro="Brașov", name_en="Brasov")
    db.add(city)
    await db.flush()

    location = Location(
        city_id=city.id,
        name="Test Panel Host",
        slug="test-panel-host",
        address="Str. Test 1",
        lat=45.0,
        lng=25.0,
        status=LocationStatus.active,
        utm_code="paneltest",
    )
    db.add(location)
    await db.flush()

    db.add(LocationItemType(location_id=location.id, item_type=ItemType.bag, daily_capacity=15))
    for weekday in range(7):
        db.add(
            LocationHours(
                location_id=location.id,
                weekday=weekday,
                open_time="08:00",
                close_time="20:00",
            )
        )

    raw_token, token_hash = generate_opaque_token()
    db.add(LocationLoginToken(location_id=location.id, token_hash=token_hash))

    owner = StaffMember(
        location_id=location.id, name="Owner", pin_hash=hash_secret("1234"), role=StaffRole.owner
    )
    staff = StaffMember(
        location_id=location.id, name="Staff", pin_hash=hash_secret("5678"), role=StaffRole.staff
    )
    db.add_all([owner, staff])
    await db.flush()
    await db.commit()
    return raw_token, owner, staff


async def test_location_profile_requires_session(client):
    resp = await client.get("/partner/location")
    assert resp.status_code == 401


async def test_location_profile_rejects_non_owner_staff(client, db):
    raw_token, owner, staff = await _seed_location_with_owner_and_staff(db)

    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "5678"},
    )
    assert login.status_code == 200

    resp = await client.get("/partner/location")
    assert resp.status_code == 403


async def test_location_profile_returns_full_profile_for_owner(client, db):
    raw_token, owner, staff = await _seed_location_with_owner_and_staff(db)

    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(owner.id), "pin": "1234"},
    )
    assert login.status_code == 200

    resp = await client.get("/partner/location")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Panel Host"
    assert body["city_slug"] == "brasov"
    assert len(body["item_types"]) == 1
    assert body["item_types"][0]["item_type"] == "bag"
    assert len(body["hours"]) == 7


async def _login_owner(client, db):
    raw_token, owner, staff = await _seed_location_with_owner_and_staff(db)
    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(owner.id), "pin": "1234"},
    )
    assert login.status_code == 200
    return owner, staff


async def test_overrides_requires_owner_session(client):
    resp = await client.get("/partner/location/overrides")
    assert resp.status_code == 401


async def test_overrides_rejects_non_owner_staff(client, db):
    raw_token, owner, staff = await _seed_location_with_owner_and_staff(db)
    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "5678"},
    )
    assert login.status_code == 200

    resp = await client.get("/partner/location/overrides")
    assert resp.status_code == 403


async def test_owner_can_set_and_list_closure(client, db):
    await _login_owner(client, db)
    target = date.today() + timedelta(days=5)

    resp = await client.post(
        "/partner/location/overrides", json={"date": target.isoformat(), "closed": True}
    )
    assert resp.status_code == 201
    assert resp.json()["closed"] is True

    listing = await client.get("/partner/location/overrides")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["date"] == target.isoformat()


async def test_owner_reposting_same_date_updates_in_place(client, db):
    await _login_owner(client, db)
    target = date.today() + timedelta(days=5)

    await client.post(
        "/partner/location/overrides", json={"date": target.isoformat(), "closed": True}
    )
    resp = await client.post(
        "/partner/location/overrides", json={"date": target.isoformat(), "closed": False}
    )
    assert resp.status_code == 201
    assert resp.json()["closed"] is False

    listing = await client.get("/partner/location/overrides")
    assert len(listing.json()) == 1


async def test_owner_can_delete_override(client, db):
    await _login_owner(client, db)
    target = date.today() + timedelta(days=5)

    await client.post(
        "/partner/location/overrides", json={"date": target.isoformat(), "closed": True}
    )
    resp = await client.delete(f"/partner/location/overrides/{target.isoformat()}")
    assert resp.status_code == 204

    listing = await client.get("/partner/location/overrides")
    assert listing.json() == []


async def test_delete_override_404_when_none_exists(client, db):
    await _login_owner(client, db)
    target = date.today() + timedelta(days=5)

    resp = await client.delete(f"/partner/location/overrides/{target.isoformat()}")
    assert resp.status_code == 404


async def test_override_rejects_hours_when_closed(client, db):
    await _login_owner(client, db)
    target = date.today() + timedelta(days=5)

    resp = await client.post(
        "/partner/location/overrides",
        json={
            "date": target.isoformat(),
            "closed": True,
            "open_time": "10:00:00",
            "close_time": "14:00:00",
        },
    )
    assert resp.status_code == 422


async def test_override_allows_special_hours_when_open(client, db):
    await _login_owner(client, db)
    target = date.today() + timedelta(days=5)

    resp = await client.post(
        "/partner/location/overrides",
        json={
            "date": target.isoformat(),
            "closed": False,
            "open_time": "10:00:00",
            "close_time": "14:00:00",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["open_time"] == "10:00:00"
    assert resp.json()["close_time"] == "14:00:00"


async def test_closure_set_via_api_actually_blocks_booking(client, db):
    from datetime import UTC, datetime

    from app.core.security import generate_opaque_token as gen_token
    from app.models.location import PriceListEntry
    from app.models.magic_link import MagicLinkToken

    raw_token, owner, staff = await _seed_location_with_owner_and_staff(db)
    db.add(PriceListEntry(item_type=ItemType.bag, price_ron=16.0, valid_from=date.today()))
    await db.commit()

    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(owner.id), "pin": "1234"},
    )
    assert login.status_code == 200

    target = date.today() + timedelta(days=5)
    override = await client.post(
        "/partner/location/overrides", json={"date": target.isoformat(), "closed": True}
    )
    assert override.status_code == 201

    raw, hashed = gen_token()
    db.add(
        MagicLinkToken(
            email="traveler@example.com",
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    await db.commit()
    await client.post("/auth/magic-link/verify", json={"token": raw})

    booking = await client.post(
        "/bookings",
        json={
            "location_slug": "test-panel-host",
            "storage_date": target.isoformat(),
            "items": [{"item_type": "bag", "qty": 1}],
            "guest_phone": "+40700000000",
        },
    )
    assert booking.status_code == 400
