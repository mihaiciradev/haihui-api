from datetime import UTC, date, datetime, timedelta

from app.core.security import generate_opaque_token, hash_secret
from app.models.city import City
from app.models.enums import ItemType, LocationStatus, StaffRole
from app.models.location import Location, LocationHours, LocationItemType, PriceListEntry
from app.models.magic_link import MagicLinkToken
from app.models.staff import LocationLoginToken, StaffMember


async def _seed_location_with_staff(db):
    city = City(slug="cluj", name_ro="Cluj-Napoca", name_en="Cluj-Napoca")
    db.add(city)
    await db.flush()

    location = Location(
        city_id=city.id,
        name="Partner Bookings Host",
        slug="partner-bookings-host",
        address="Str. Test 1",
        lat=46.7,
        lng=23.6,
        status=LocationStatus.active,
        utm_code="pbh",
    )
    db.add(location)
    await db.flush()

    db.add(LocationItemType(location_id=location.id, item_type=ItemType.bag, daily_capacity=10))
    for weekday in range(7):
        db.add(
            LocationHours(
                location_id=location.id, weekday=weekday, open_time="08:00", close_time="20:00"
            )
        )
    db.add(PriceListEntry(item_type=ItemType.bag, price_ron=16.0, valid_from=date.today()))

    raw_token, token_hash = generate_opaque_token()
    db.add(LocationLoginToken(location_id=location.id, token_hash=token_hash))

    staff = StaffMember(
        location_id=location.id, name="Staff", pin_hash=hash_secret("5678"), role=StaffRole.staff
    )
    db.add(staff)
    await db.flush()
    await db.commit()
    return location, raw_token, staff


async def _login_traveler(client, db, email="traveler@example.com"):
    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email=email, token_hash=hashed, expires_at=datetime.now(UTC) + timedelta(minutes=15)
        )
    )
    await db.commit()
    resp = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert resp.status_code == 200


async def _create_booking(client, db, location):
    await _login_traveler(client, db)
    resp = await client.post(
        "/bookings",
        json={
            "location_slug": location.slug,
            "storage_date": (date.today() + timedelta(days=1)).isoformat(),
            "items": [{"item_type": "bag", "qty": 1}],
            "guest_phone": "+40700000000",
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def test_partner_bookings_requires_session(client):
    resp = await client.get("/partner/bookings")
    assert resp.status_code == 401


async def test_partner_bookings_lists_own_location_bookings(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)

    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "5678"},
    )
    assert login.status_code == 200

    resp = await client.get("/partner/bookings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["code"] == booking["code"]
    assert body[0]["guest_email"] == "traveler@example.com"
    assert body[0]["items"][0]["item_type"] == "bag"
