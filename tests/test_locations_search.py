from datetime import date, time, timedelta

from sqlalchemy import select

from app.core.security import generate_opaque_token
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


async def _get_or_create_city(db, slug="cluj") -> City:
    result = await db.execute(select(City).where(City.slug == slug))
    city = result.scalar_one_or_none()
    if city is None:
        city = City(slug=slug, name_ro="Cluj-Napoca", name_en="Cluj-Napoca")
        db.add(city)
        await db.flush()
    return city


async def _seed_location(
    db,
    *,
    slug="search-host",
    city_slug="cluj",
    daily_capacity=5,
    item_types=(ItemType.bag,),
    bag_price=16.0,
) -> Location:
    city = await _get_or_create_city(db, city_slug)
    location = Location(
        city_id=city.id,
        name=f"Host {slug}",
        slug=slug,
        address="Str. Test 1",
        lat=46.7,
        lng=23.6,
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
    db.add(PriceListEntry(item_type=ItemType.bag, price_ron=bag_price, valid_from=date.today()))
    db.add(PriceListEntry(item_type=ItemType.trolley, price_ron=29.0, valid_from=date.today()))
    await db.commit()
    return location


async def _login_traveler(client, db, email="traveler@example.com"):
    from datetime import UTC, datetime

    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email=email, token_hash=hashed, expires_at=datetime.now(UTC) + timedelta(minutes=15)
        )
    )
    await db.commit()
    resp = await client.post("/auth/magic-link/verify", json={"token": raw})
    assert resp.status_code == 200


async def test_search_requires_at_least_one_item(client):
    tomorrow = date.today() + timedelta(days=1)
    resp = await client.get(
        "/locations/search", params={"storage_date": tomorrow.isoformat()}
    )
    assert resp.status_code == 400


async def test_search_rejects_malformed_item_spec(client):
    tomorrow = date.today() + timedelta(days=1)
    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "not-a-valid-spec"},
    )
    assert resp.status_code == 422


async def test_search_returns_location_that_fits(client, db):
    location = await _seed_location(db)
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "bag:2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == location.slug
    assert body[0]["total_price_ron"] == 32.0
    assert body[0]["nights"] == 1


async def test_search_excludes_location_missing_item_type(client, db):
    await _seed_location(db, slug="bag-only", item_types=(ItemType.bag,))
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "trolley:1"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_excludes_location_over_capacity(client, db):
    await _seed_location(db, daily_capacity=1)
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "bag:2"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_excludes_location_closed_that_day(client, db):
    location = await _seed_location(db)
    tomorrow = date.today() + timedelta(days=1)
    db.add(
        LocationOverride(
            location_id=location.id, date=tomorrow, closed=True, created_by="admin"
        )
    )
    await db.commit()

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "bag:1"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_excludes_location_already_booked_out(client, db):
    location = await _seed_location(db, daily_capacity=1)
    tomorrow = date.today() + timedelta(days=1)
    await _login_traveler(client, db)

    booked = await client.post(
        "/bookings",
        json={
            "location_slug": location.slug,
            "storage_date": tomorrow.isoformat(),
            "items": [{"item_type": "bag", "qty": 1}],
            "guest_phone": "+40700000000",
        },
    )
    assert booked.status_code == 201

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "bag:1"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_multi_day_totals_price_per_night(client, db):
    await _seed_location(db, bag_price=10.0)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)

    resp = await client.get(
        "/locations/search",
        params={
            "storage_date": start.isoformat(),
            "pickup_date": end.isoformat(),
            "items": "bag:1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["nights"] == 3
    assert body[0]["total_price_ron"] == 30.0


async def test_search_filters_by_city(client, db):
    await _seed_location(db, slug="cluj-host", city_slug="cluj")
    await _seed_location(db, slug="brasov-host", city_slug="brasov")
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "bag:1", "city": "brasov"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == "brasov-host"


async def test_search_sorts_cheapest_first(client, db):
    await _seed_location(db, slug="pricier", bag_price=20.0)
    await _seed_location(db, slug="cheaper", bag_price=5.0)
    tomorrow = date.today() + timedelta(days=1)

    resp = await client.get(
        "/locations/search",
        params={"storage_date": tomorrow.isoformat(), "items": "bag:1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [loc["slug"] for loc in body] == ["cheaper", "pricier"]
