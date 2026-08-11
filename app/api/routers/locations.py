from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.city import City
from app.models.enums import LocationStatus
from app.models.location import Location, LocationHours, LocationItemType, PriceListEntry
from app.schemas.location_public import (
    LocationDetail,
    LocationListItem,
    PublicDayHours,
    PublicItemType,
)

router = APIRouter(prefix="/locations", tags=["locations-public"])


async def _current_prices(db: DbSession) -> dict[str, float]:
    """Latest PriceListEntry per item_type where valid_from <= today --
    price_list is append-only (§4), this is "the price in effect right now".
    """
    result = await db.execute(
        select(PriceListEntry)
        .where(PriceListEntry.valid_from <= date.today())
        .order_by(PriceListEntry.valid_from.desc())
    )
    prices: dict[str, float] = {}
    for entry in result.scalars().all():
        prices.setdefault(entry.item_type.value, float(entry.price_ron))
    return prices


@router.get("/{slug}", response_model=LocationDetail)
async def get_location(slug: str, db: DbSession) -> LocationDetail:
    result = await db.execute(
        select(Location, City)
        .join(City, City.id == Location.city_id)
        .where(Location.slug == slug, Location.status == LocationStatus.active)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    location, city = row

    prices = await _current_prices(db)

    item_types_result = await db.execute(
        select(LocationItemType).where(LocationItemType.location_id == location.id)
    )
    hours_result = await db.execute(
        select(LocationHours)
        .where(LocationHours.location_id == location.id)
        .order_by(LocationHours.weekday)
    )

    return LocationDetail(
        id=str(location.id),
        name=location.name,
        slug=location.slug,
        city_slug=city.slug,
        city_name_ro=city.name_ro,
        city_name_en=city.name_en,
        address=location.address,
        lat=location.lat,
        lng=location.lng,
        description_ro=location.description_ro,
        description_en=location.description_en,
        photos=list(location.photos),
        status=location.status.value,
        utm_code=location.utm_code,
        google_maps_url=location.google_maps_url,
        google_review_url=location.google_review_url,
        item_types=[
            PublicItemType(
                item_type=i.item_type.value,
                price_ron=prices.get(i.item_type.value, 0.0),
                daily_capacity=i.daily_capacity,
            )
            for i in item_types_result.scalars().all()
        ],
        hours=[
            PublicDayHours(
                weekday=h.weekday,
                open_time=h.open_time.isoformat(),
                close_time=h.close_time.isoformat(),
            )
            for h in hours_result.scalars().all()
        ],
    )


@router.get("", response_model=list[LocationListItem])
async def list_public_locations(db: DbSession, city: str | None = None) -> list[LocationListItem]:
    """Homepage/city browse -- travelers finding a shop without a QR."""
    query = (
        select(Location, City)
        .join(City, City.id == Location.city_id)
        .where(Location.status == LocationStatus.active)
        .order_by(Location.name)
    )
    if city:
        query = query.where(City.slug == city)
    result = await db.execute(query)
    rows = result.all()

    prices = await _current_prices(db)
    lowest_price = min(prices.values()) if prices else None

    return [
        LocationListItem(
            id=str(location.id),
            name=location.name,
            slug=location.slug,
            city_slug=city_row.slug,
            address=location.address,
            lat=location.lat,
            lng=location.lng,
            photos=list(location.photos),
            from_price_ron=lowest_price,
        )
        for location, city_row in rows
    ]
