import asyncio
from datetime import UTC, date, datetime, time, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import generate_opaque_token
from app.main import app
from app.models.city import City
from app.models.enums import ItemType, LocationStatus
from app.models.location import (
    Location,
    LocationHours,
    LocationItemType,
    LocationOverride,
    PriceListEntry,
)
from app.models.magic_link import MagicLinkToken


async def _get_or_create_city(db, slug="brasov") -> City:
    result = await db.execute(select(City).where(City.slug == slug))
    city = result.scalar_one_or_none()
    if city is None:
        city = City(slug=slug, name_ro="Brașov", name_en="Brasov")
        db.add(city)
        await db.flush()
    return city


async def _seed_bookable_location(
    db, *, slug="bookable-host", daily_capacity=5, item_types=(ItemType.bag,)
) -> Location:
    city = await _get_or_create_city(db)
    location = Location(
        city_id=city.id,
        name="Bookable Host",
        slug=slug,
        address="Str. Test 1",
        lat=45.6,
        lng=25.6,
        status=LocationStatus.active,
        utm_code=f"utm-{slug}",
    )
    db.add(location)
    await db.flush()

    for item_type in item_types:
        db.add(
            LocationItemType(
                location_id=location.id, item_type=item_type, daily_capacity=daily_capacity
            )
        )
    for weekday in range(7):
        db.add(
            LocationHours(
                location_id=location.id,
                weekday=weekday,
                open_time=time(8, 0),
                close_time=time(20, 0),
            )
        )
    db.add(PriceListEntry(item_type=ItemType.bag, price_ron=16.0, valid_from=date.today()))
    db.add(PriceListEntry(item_type=ItemType.trolley, price_ron=29.0, valid_from=date.today()))
    await db.commit()
    return location


def _payload(location_slug, storage_date, qty=1, item_type="bag", pickup_date=None):
    payload = {
        "location_slug": location_slug,
        "storage_date": storage_date.isoformat(),
        "items": [{"item_type": item_type, "qty": qty}],
        "guest_phone": "+40700000000",
    }
    if pickup_date is not None:
        payload["pickup_date"] = pickup_date.isoformat()
    return payload


async def _login_traveler(client, db, email="traveler@example.com"):
    """Bookings require a verified traveler session -- login is deferred to
    finalize time (§ product decision), so every booking test must first
    prove email ownership via the same magic-link flow a real traveler
    would use, rather than posting a booking anonymously.
    """
    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email=email, token_hash=hashed, expires_at=datetime.now(UTC) + timedelta(minutes=15)
        )
    )
    await db.commit()
    resp = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert resp.status_code == 200


async def test_create_booking_requires_traveler_session(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert resp.status_code == 401


async def test_create_booking_happy_path(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    resp = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["amount_total"] == 16.0
    assert len(body["booking_token"]) >= 16
    assert body["code"].startswith("HH-")
    assert body["qr_url"].endswith(f"/bookings/{body['booking_token']}/qr.png")


async def test_create_booking_rejects_past_date(client, db):
    location = await _seed_bookable_location(db)
    yesterday = date.today() - timedelta(days=1)
    await _login_traveler(client, db)

    resp = await client.post("/bookings", json=_payload(location.slug, yesterday))
    assert resp.status_code == 400


async def test_create_booking_rejects_too_far_ahead(client, db):
    location = await _seed_bookable_location(db)
    too_far = date.today() + timedelta(days=32)
    await _login_traveler(client, db)

    resp = await client.post("/bookings", json=_payload(location.slug, too_far))
    assert resp.status_code == 400


async def test_create_booking_rejects_unknown_location(client, db):
    await _login_traveler(client, db)
    resp = await client.post(
        "/bookings", json=_payload("does-not-exist", date.today() + timedelta(days=1))
    )
    assert resp.status_code == 404


async def test_create_booking_rejects_unaccepted_item_type(client, db):
    location = await _seed_bookable_location(db, item_types=(ItemType.bag,))
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    resp = await client.post(
        "/bookings", json=_payload(location.slug, tomorrow, item_type="trolley")
    )
    assert resp.status_code == 400


async def test_create_booking_rejects_when_location_closed_that_day(client, db):
    location = await _seed_bookable_location(db)
    target = date.today() + timedelta(days=1)
    db.add(LocationOverride(location_id=location.id, date=target, closed=True, created_by="admin"))
    await db.commit()
    await _login_traveler(client, db)

    resp = await client.post("/bookings", json=_payload(location.slug, target))
    assert resp.status_code == 400


async def test_create_booking_rejects_duplicate_item_type_in_request(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)
    payload = _payload(location.slug, tomorrow)
    payload["items"] = [{"item_type": "bag", "qty": 1}, {"item_type": "bag", "qty": 2}]

    resp = await client.post("/bookings", json=payload)
    assert resp.status_code == 422


async def test_create_booking_rejects_over_capacity(client, db):
    location = await _seed_bookable_location(db, daily_capacity=2)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    first = await client.post("/bookings", json=_payload(location.slug, tomorrow, qty=2))
    assert first.status_code == 201

    second = await client.post("/bookings", json=_payload(location.slug, tomorrow, qty=1))
    assert second.status_code == 400


async def test_get_booking_by_token(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    created = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    token = created.json()["booking_token"]

    resp = await client.get(f"/bookings/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == created.json()["code"]
    assert body["location_name"] == "Bookable Host"
    assert body["items"][0]["item_type"] == "bag"
    assert body["qr_url"].endswith(f"/bookings/{token}/qr.png")


async def test_get_booking_404_unknown_token(client):
    resp = await client.get("/bookings/totally-bogus-token")
    assert resp.status_code == 404


async def test_get_booking_qr_png(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    created = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    token = created.json()["booking_token"]

    resp = await client.get(f"/bookings/{token}/qr.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


async def test_get_booking_qr_png_404_unknown_token(client):
    resp = await client.get("/bookings/totally-bogus-token/qr.png")
    assert resp.status_code == 404


async def test_create_booking_defaults_pickup_date_to_storage_date(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    resp = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert resp.status_code == 201
    body = resp.json()
    assert body["pickup_date"] == tomorrow.isoformat()
    assert body["amount_total"] == 16.0


async def test_create_multi_day_booking_charges_per_night(client, db):
    location = await _seed_bookable_location(db)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)
    await _login_traveler(client, db)

    resp = await client.post("/bookings", json=_payload(location.slug, start, pickup_date=end))
    assert resp.status_code == 201
    body = resp.json()
    assert body["storage_date"] == start.isoformat()
    assert body["pickup_date"] == end.isoformat()
    # 3 calendar days (start, start+1, end) at 16 RON/day
    assert body["amount_total"] == 48.0


async def test_create_booking_rejects_pickup_before_storage(client, db):
    location = await _seed_bookable_location(db)
    start = date.today() + timedelta(days=2)
    earlier = start - timedelta(days=1)
    await _login_traveler(client, db)

    resp = await client.post(
        "/bookings", json=_payload(location.slug, start, pickup_date=earlier)
    )
    assert resp.status_code == 422


async def test_create_booking_rejects_span_over_max(client, db):
    location = await _seed_bookable_location(db)
    start = date.today() + timedelta(days=1)
    too_long = start + timedelta(days=20)
    await _login_traveler(client, db)

    resp = await client.post(
        "/bookings", json=_payload(location.slug, start, pickup_date=too_long)
    )
    assert resp.status_code == 422


async def test_multi_day_bookings_block_only_on_overlapping_days(client, db):
    """A 2-capacity item: one multi-day booking uses 1 slot across days 1-3.
    A second booking for day 4 only (no overlap) must still succeed even
    though the first booking is still active, since day 4 isn't shared.
    """
    location = await _seed_bookable_location(db, daily_capacity=1)
    day1 = date.today() + timedelta(days=1)
    day3 = day1 + timedelta(days=2)
    day4 = day1 + timedelta(days=3)
    await _login_traveler(client, db)

    first = await client.post(
        "/bookings", json=_payload(location.slug, day1, pickup_date=day3)
    )
    assert first.status_code == 201

    non_overlapping = await client.post(
        "/bookings", json=_payload(location.slug, day4, pickup_date=day4)
    )
    assert non_overlapping.status_code == 201

    overlapping = await client.post(
        "/bookings", json=_payload(location.slug, day3, pickup_date=day3)
    )
    assert overlapping.status_code == 400


async def test_list_my_bookings_requires_session(client):
    resp = await client.get("/bookings")
    assert resp.status_code == 401


async def test_list_my_bookings_returns_own_bookings_only(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)

    await _login_traveler(client, db, email="mine@example.com")
    mine = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert mine.status_code == 201

    # a different traveler's booking must not show up in the first one's history
    await _login_traveler(client, db, email="someone-else@example.com")
    other = await client.post(
        "/bookings", json=_payload(location.slug, tomorrow + timedelta(days=1))
    )
    assert other.status_code == 201

    await _login_traveler(client, db, email="mine@example.com")
    resp = await client.get("/bookings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["code"] == mine.json()["code"]
    assert body[0]["location_name"] == "Bookable Host"
    assert "booking_token" not in body[0]


async def test_resend_booking_link_requires_session(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)
    created = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert created.status_code == 201
    booking_id = (await client.get("/bookings")).json()[0]["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.post(f"/bookings/{booking_id}/resend")
        assert resp.status_code == 401


async def test_resend_booking_link_issues_working_new_qr(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)
    created = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    old_token = created.json()["booking_token"]
    booking_id = (await client.get("/bookings")).json()[0]["id"]

    resp = await client.post(f"/bookings/{booking_id}/resend")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"

    # the original link must still work -- resend only adds a new token
    old_still_works = await client.get(f"/bookings/{old_token}")
    assert old_still_works.status_code == 200


async def test_resend_booking_link_rejects_other_travelers_booking(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db, email="owner@example.com")
    created = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert created.status_code == 201
    booking_id = (await client.get("/bookings")).json()[0]["id"]

    await _login_traveler(client, db, email="intruder@example.com")
    resp = await client.post(f"/bookings/{booking_id}/resend")
    assert resp.status_code == 404


async def test_capacity_race_exactly_one_wins_last_slot(client, db):
    """§5.4/§9: fire parallel bookings at the last remaining slot, exactly
    one must succeed. Requests hit the API through separate DB connections
    (NullPool, one per request), so this genuinely exercises Postgres row
    locking, not just Python-level serialization.
    """
    location = await _seed_bookable_location(db, daily_capacity=1)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    results = await asyncio.gather(
        *[client.post("/bookings", json=_payload(location.slug, tomorrow)) for _ in range(5)]
    )
    statuses = [r.status_code for r in results]
    assert statuses.count(201) == 1, f"expected exactly one 201, got {statuses}"
    assert statuses.count(400) == 4
