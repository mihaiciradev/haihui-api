import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select

from app.models.city import City
from app.models.enums import ItemType, LocationStatus
from app.models.location import (
    Location,
    LocationHours,
    LocationItemType,
    LocationOverride,
    PriceListEntry,
)


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


def _payload(location_slug, storage_date, qty=1, item_type="bag"):
    return {
        "location_slug": location_slug,
        "storage_date": storage_date.isoformat(),
        "items": [{"item_type": item_type, "qty": qty}],
        "guest_email": "traveler@example.com",
        "guest_phone": "+40700000000",
    }


async def test_create_booking_happy_path(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["amount_total"] == 16.0
    assert len(body["booking_token"]) >= 16
    assert body["code"].startswith("HH-")


async def test_create_booking_rejects_past_date(client, db):
    location = await _seed_bookable_location(db)
    yesterday = date.today() - timedelta(days=1)

    resp = await client.post("/bookings", json=_payload(location.slug, yesterday))
    assert resp.status_code == 400


async def test_create_booking_rejects_too_far_ahead(client, db):
    location = await _seed_bookable_location(db)
    too_far = date.today() + timedelta(days=32)

    resp = await client.post("/bookings", json=_payload(location.slug, too_far))
    assert resp.status_code == 400


async def test_create_booking_rejects_unknown_location(client):
    resp = await client.post(
        "/bookings", json=_payload("does-not-exist", date.today() + timedelta(days=1))
    )
    assert resp.status_code == 404


async def test_create_booking_rejects_unaccepted_item_type(client, db):
    location = await _seed_bookable_location(db, item_types=(ItemType.bag,))
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.post(
        "/bookings", json=_payload(location.slug, tomorrow, item_type="trolley")
    )
    assert resp.status_code == 400


async def test_create_booking_rejects_when_location_closed_that_day(client, db):
    location = await _seed_bookable_location(db)
    target = date.today() + timedelta(days=1)
    db.add(LocationOverride(location_id=location.id, date=target, closed=True, created_by="admin"))
    await db.commit()

    resp = await client.post("/bookings", json=_payload(location.slug, target))
    assert resp.status_code == 400


async def test_create_booking_rejects_duplicate_item_type_in_request(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)
    payload = _payload(location.slug, tomorrow)
    payload["items"] = [{"item_type": "bag", "qty": 1}, {"item_type": "bag", "qty": 2}]

    resp = await client.post("/bookings", json=payload)
    assert resp.status_code == 422


async def test_create_booking_rejects_over_capacity(client, db):
    location = await _seed_bookable_location(db, daily_capacity=2)
    tomorrow = date.today() + timedelta(days=1)

    first = await client.post("/bookings", json=_payload(location.slug, tomorrow, qty=2))
    assert first.status_code == 201

    second = await client.post("/bookings", json=_payload(location.slug, tomorrow, qty=1))
    assert second.status_code == 400


async def test_get_booking_by_token(client, db):
    location = await _seed_bookable_location(db)
    tomorrow = date.today() + timedelta(days=1)

    created = await client.post("/bookings", json=_payload(location.slug, tomorrow))
    token = created.json()["booking_token"]

    resp = await client.get(f"/bookings/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == created.json()["code"]
    assert body["location_name"] == "Bookable Host"
    assert body["items"][0]["item_type"] == "bag"


async def test_get_booking_404_unknown_token(client):
    resp = await client.get("/bookings/totally-bogus-token")
    assert resp.status_code == 404


async def test_capacity_race_exactly_one_wins_last_slot(client, db):
    """§5.4/§9: fire parallel bookings at the last remaining slot, exactly
    one must succeed. Requests hit the API through separate DB connections
    (NullPool, one per request), so this genuinely exercises Postgres row
    locking, not just Python-level serialization.
    """
    location = await _seed_bookable_location(db, daily_capacity=1)
    tomorrow = date.today() + timedelta(days=1)

    results = await asyncio.gather(
        *[client.post("/bookings", json=_payload(location.slug, tomorrow)) for _ in range(5)]
    )
    statuses = [r.status_code for r in results]
    assert statuses.count(201) == 1, f"expected exactly one 201, got {statuses}"
    assert statuses.count(400) == 4
