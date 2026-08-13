from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.security import generate_opaque_token, hash_secret
from app.models.booking import Booking
from app.models.city import City
from app.models.enums import ItemType, LocationStatus, StaffRole
from app.models.location import Location, LocationHours, LocationItemType, PriceListEntry
from app.models.magic_link import MagicLinkToken
from app.models.staff import LocationLoginToken, StaffMember


async def _get_or_create_city(db, slug="cluj") -> City:
    result = await db.execute(select(City).where(City.slug == slug))
    city = result.scalar_one_or_none()
    if city is None:
        city = City(slug=slug, name_ro="Cluj-Napoca", name_en="Cluj-Napoca")
        db.add(city)
        await db.flush()
    return city


async def _seed_location_with_staff(db, *, slug="partner-bookings-host", utm_code="pbh"):
    city = await _get_or_create_city(db)

    location = Location(
        city_id=city.id,
        name="Partner Bookings Host",
        slug=slug,
        address="Str. Test 1",
        lat=46.7,
        lng=23.6,
        status=LocationStatus.active,
        utm_code=utm_code,
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


async def _login_staff(client, raw_token, staff, pin="5678"):
    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": pin},
    )
    assert login.status_code == 200


async def test_partner_bookings_requires_session(client):
    resp = await client.get("/partner/bookings")
    assert resp.status_code == 401


async def test_partner_bookings_lists_own_location_bookings(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    resp = await client.get("/partner/bookings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["code"] == booking["code"]
    assert body[0]["guest_email"] == "traveler@example.com"
    assert body[0]["items"][0]["item_type"] == "bag"
    assert body[0]["checked_in_at"] is None
    assert body[0]["checked_out_at"] is None
    assert body[0]["photo_count"] == 0


async def test_lookup_by_code_finds_booking(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    resp = await client.get("/partner/bookings/lookup", params={"code": booking["code"].lower()})
    assert resp.status_code == 200
    assert resp.json()["code"] == booking["code"]


async def test_lookup_by_token_finds_booking(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    resp = await client.get(
        "/partner/bookings/lookup", params={"token": booking["booking_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == booking["code"]


async def test_lookup_requires_token_or_code(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    await _login_staff(client, raw_token, staff)

    resp = await client.get("/partner/bookings/lookup")
    assert resp.status_code == 400


async def test_lookup_does_not_leak_other_locations_booking(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)

    other_location, other_raw_token, other_staff = await _seed_location_with_staff(
        db, slug="other-host", utm_code="other"
    )
    await _login_staff(client, other_raw_token, other_staff)

    resp = await client.get("/partner/bookings/lookup", params={"code": booking["code"]})
    assert resp.status_code == 404


async def test_check_in_then_check_out_happy_path(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    lookup = await client.get("/partner/bookings/lookup", params={"code": booking["code"]})
    booking_id = lookup.json()["id"]

    check_in = await client.post(f"/partner/bookings/{booking_id}/check-in")
    assert check_in.status_code == 200
    assert check_in.json()["status"] == "stored"
    assert check_in.json()["checked_in_at"] is not None

    check_out = await client.post(f"/partner/bookings/{booking_id}/check-out")
    assert check_out.status_code == 200
    assert check_out.json()["status"] == "released"
    assert check_out.json()["checked_out_at"] is not None


async def test_check_in_rejects_wrong_status(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    lookup = await client.get("/partner/bookings/lookup", params={"code": booking["code"]})
    booking_id = lookup.json()["id"]
    await client.post(f"/partner/bookings/{booking_id}/check-in")

    second_check_in = await client.post(f"/partner/bookings/{booking_id}/check-in")
    assert second_check_in.status_code == 400


async def test_check_out_rejects_before_check_in(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    lookup = await client.get("/partner/bookings/lookup", params={"code": booking["code"]})
    booking_id = lookup.json()["id"]

    resp = await client.post(f"/partner/bookings/{booking_id}/check-out")
    assert resp.status_code == 400


async def test_check_in_requires_session(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)

    # deliberately not logged in as staff
    result = await db.execute(select(Booking.id).where(Booking.code == booking["code"]))
    booking_id = result.scalar_one()

    resp = await client.post(f"/partner/bookings/{booking_id}/check-in")
    assert resp.status_code == 401


async def test_bag_photo_upload_without_storage_configured_returns_503(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    lookup = await client.get("/partner/bookings/lookup", params={"code": booking["code"]})
    booking_id = lookup.json()["id"]

    resp = await client.post(
        f"/partner/bookings/{booking_id}/photos",
        files={"photo": ("bag.jpg", b"\xff\xd8\xff\xe0fake-jpeg-bytes", "image/jpeg")},
    )
    assert resp.status_code == 503


async def test_bag_photo_upload_rejects_bad_content_type(client, db):
    location, raw_token, staff = await _seed_location_with_staff(db)
    booking = await _create_booking(client, db, location)
    await _login_staff(client, raw_token, staff)

    lookup = await client.get("/partner/bookings/lookup", params={"code": booking["code"]})
    booking_id = lookup.json()["id"]

    resp = await client.post(
        f"/partner/bookings/{booking_id}/photos",
        files={"photo": ("bag.txt", b"not a photo", "text/plain")},
    )
    assert resp.status_code == 400
