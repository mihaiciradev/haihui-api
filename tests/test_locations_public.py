from datetime import date, time

from sqlalchemy import select

from app.models.city import City
from app.models.enums import ItemType, LocationStatus
from app.models.location import Location, LocationHours, LocationItemType, PriceListEntry


async def _get_or_create_city(db, slug="brasov") -> City:
    result = await db.execute(select(City).where(City.slug == slug))
    city = result.scalar_one_or_none()
    if city is None:
        city = City(slug=slug, name_ro="Brașov", name_en="Brasov")
        db.add(city)
        await db.flush()
    return city


async def _seed_full_location(
    db, *, name="Public Test Host", slug="public-test-host", status=LocationStatus.active
) -> Location:
    city = await _get_or_create_city(db)
    location = Location(
        city_id=city.id,
        name=name,
        slug=slug,
        address="Str. Test 1",
        lat=45.6,
        lng=25.6,
        status=status,
        utm_code=f"utm-{slug}",
    )
    db.add(location)
    await db.flush()

    db.add(LocationItemType(location_id=location.id, item_type=ItemType.bag, daily_capacity=5))
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
    await db.commit()
    return location


async def test_get_location_happy_path(client, db):
    await _seed_full_location(db)

    resp = await client.get("/locations/public-test-host")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Public Test Host"
    assert body["city_slug"] == "brasov"
    assert len(body["item_types"]) == 1
    assert body["item_types"][0]["price_ron"] == 16.0
    assert len(body["hours"]) == 7


async def test_get_location_404_unknown_slug(client):
    resp = await client.get("/locations/does-not-exist")
    assert resp.status_code == 404


async def test_get_location_404_when_delisted(client, db):
    await _seed_full_location(
        db, name="Delisted Host", slug="delisted-host", status=LocationStatus.delisted
    )

    resp = await client.get("/locations/delisted-host")
    assert resp.status_code == 404


async def test_browse_locations_filters_by_city(client, db):
    brasov = await _get_or_create_city(db, "brasov")
    timisoara = await _get_or_create_city(db, "timisoara")

    db.add(
        Location(
            city_id=brasov.id,
            name="Brasov Host",
            slug="brasov-host",
            address="A",
            lat=1,
            lng=1,
            status=LocationStatus.active,
            utm_code="utm-b",
        )
    )
    db.add(
        Location(
            city_id=timisoara.id,
            name="Timisoara Host",
            slug="timisoara-host",
            address="B",
            lat=1,
            lng=1,
            status=LocationStatus.active,
            utm_code="utm-t",
        )
    )
    await db.commit()

    resp = await client.get("/locations", params={"city": "brasov"})
    assert resp.status_code == 200
    names = [loc["name"] for loc in resp.json()]
    assert names == ["Brasov Host"]


async def test_browse_locations_excludes_inactive(client, db):
    city = await _get_or_create_city(db)
    db.add(
        Location(
            city_id=city.id,
            name="Paused Host",
            slug="paused-host",
            address="A",
            lat=1,
            lng=1,
            status=LocationStatus.paused,
            utm_code="utm-paused",
        )
    )
    await db.commit()

    resp = await client.get("/locations")
    assert resp.status_code == 200
    names = [loc["name"] for loc in resp.json()]
    assert "Paused Host" not in names
