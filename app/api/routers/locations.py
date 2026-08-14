from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.capacity import MAX_DAYS_AHEAD, MAX_STORAGE_SPAN_DAYS, daily_usage, date_range
from app.core.hours import is_location_open
from app.core.http import client_ip
from app.core.rate_limit import check_rate_limit
from app.models.booking import Booking, BookingItem
from app.models.city import City
from app.models.enums import BookingStatus, ItemType, LocationStatus
from app.models.location import Location, LocationHours, LocationItemType, PriceListEntry
from app.schemas.location_public import (
    LocationDetail,
    LocationListItem,
    LocationSearchResult,
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


def _parse_item_spec(spec: str) -> tuple[ItemType, int]:
    try:
        item_type_str, qty_str = spec.split(":", 1)
        item_type = ItemType(item_type_str.strip().lower())
        qty = int(qty_str)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Invalid items value {spec!r}, expected 'item_type:qty' e.g. 'bag:2'",
        ) from exc
    if qty <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"qty must be positive: {spec!r}"
        )
    return item_type, qty


@router.get("/search", response_model=list[LocationSearchResult])
async def search_locations(
    request: Request,
    db: DbSession,
    storage_date: date,
    pickup_date: date | None = None,
    city: str | None = None,
    items: list[str] = Query(default=[]),  # noqa: B008
) -> list[LocationSearchResult]:
    """Only locations that can actually take every requested item for the
    whole stay -- not just active locations in the city. This is a
    best-effort read, not row-locked like POST /bookings, so a location
    shown here can still lose the last slot to someone else before the
    traveler finishes booking; POST /bookings is the source of truth and
    returns 400 if that happens.
    """
    check_rate_limit(
        f"location-search:ip:{client_ip(request)}", max_attempts=60, window_seconds=3600
    )

    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one item is required")

    requirements: dict[ItemType, int] = {}
    for spec in items:
        item_type, qty = _parse_item_spec(spec)
        if item_type in requirements:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "items must not repeat the same item_type"
            )
        requirements[item_type] = qty

    today = date.today()
    if storage_date < today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "storage_date cannot be in the past")
    if storage_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"storage_date must be within {MAX_DAYS_AHEAD} days"
        )

    resolved_pickup_date = pickup_date or storage_date
    if resolved_pickup_date < storage_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "pickup_date cannot be before storage_date"
        )
    if (resolved_pickup_date - storage_date).days > MAX_STORAGE_SPAN_DAYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"storage span cannot exceed {MAX_STORAGE_SPAN_DAYS + 1} days",
        )

    nights = (resolved_pickup_date - storage_date).days + 1
    prices = await _current_prices(db)
    if any(item_type.value not in prices for item_type in requirements):
        return []

    query = (
        select(Location, City)
        .join(City, City.id == Location.city_id)
        .where(Location.status == LocationStatus.active)
        .order_by(Location.name)
    )
    if city:
        query = query.where(City.slug == city)
    candidates = (await db.execute(query)).all()

    results: list[LocationSearchResult] = []
    for location, city_row in candidates:
        capacity_result = await db.execute(
            select(LocationItemType).where(LocationItemType.location_id == location.id)
        )
        capacity_by_type = {
            row.item_type: row.daily_capacity for row in capacity_result.scalars().all()
        }

        if any(item_type not in capacity_by_type for item_type in requirements):
            continue
        if any(qty > capacity_by_type[item_type] for item_type, qty in requirements.items()):
            continue

        if not await is_location_open(db, location.id, storage_date):
            continue
        if resolved_pickup_date != storage_date and not await is_location_open(
            db, location.id, resolved_pickup_date
        ):
            continue

        fits = True
        for item_type, qty in requirements.items():
            overlap_result = await db.execute(
                select(Booking.storage_date, Booking.pickup_date, BookingItem.qty)
                .join(Booking, Booking.id == BookingItem.booking_id)
                .where(
                    Booking.location_id == location.id,
                    BookingItem.item_type == item_type,
                    Booking.status.notin_([BookingStatus.cancelled, BookingStatus.expired]),
                    Booking.storage_date <= resolved_pickup_date,
                    Booking.pickup_date >= storage_date,
                )
            )
            overlap_rows = [(s, e, q) for s, e, q in overlap_result.all()]
            usage = daily_usage(overlap_rows, storage_date, resolved_pickup_date)
            for day in date_range(storage_date, resolved_pickup_date):
                if usage.get(day, 0) + qty > capacity_by_type[item_type]:
                    fits = False
                    break
            if not fits:
                break
        if not fits:
            continue

        total_price = sum(
            prices[item_type.value] * qty * nights for item_type, qty in requirements.items()
        )
        results.append(
            LocationSearchResult(
                id=str(location.id),
                name=location.name,
                slug=location.slug,
                city_slug=city_row.slug,
                city_name_ro=city_row.name_ro,
                city_name_en=city_row.name_en,
                address=location.address,
                lat=location.lat,
                lng=location.lng,
                photos=list(location.photos),
                total_price_ron=total_price,
                nights=nights,
            )
        )

    results.sort(key=lambda r: r.total_price_ron)
    return results


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
