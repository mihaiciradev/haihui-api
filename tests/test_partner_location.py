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
