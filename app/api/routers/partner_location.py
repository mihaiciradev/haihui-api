from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, StaffIdentity, require_owner
from app.models.city import City
from app.models.location import Location, LocationHours, LocationItemType
from app.schemas.location import DayHoursOut, ItemCapacityOut, LocationProfileResponse

router = APIRouter(prefix="/partner", tags=["partner-location"])


@router.get("/location", response_model=LocationProfileResponse)
async def get_location_profile(
    db: DbSession, identity: StaffIdentity = Depends(require_owner)  # noqa: B008
) -> LocationProfileResponse:
    """The owner's panel landing view: their location's full profile,
    accepted item types + capacity, and weekly hours template. Owner-only —
    staff scanning bags don't need this, per §3.2.
    """
    result = await db.execute(
        select(Location, City.slug)
        .join(City, City.id == Location.city_id)
        .where(Location.id == identity.location_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    location, city_slug = row

    item_types_result = await db.execute(
        select(LocationItemType).where(LocationItemType.location_id == location.id)
    )
    hours_result = await db.execute(
        select(LocationHours)
        .where(LocationHours.location_id == location.id)
        .order_by(LocationHours.weekday)
    )

    return LocationProfileResponse(
        id=str(location.id),
        name=location.name,
        slug=location.slug,
        city_slug=city_slug,
        address=location.address,
        lat=location.lat,
        lng=location.lng,
        description_ro=location.description_ro,
        description_en=location.description_en,
        photos=list(location.photos),
        status=location.status.value,
        revenue_share_pct=location.revenue_share_pct,
        utm_code=location.utm_code,
        google_maps_url=location.google_maps_url,
        google_review_url=location.google_review_url,
        strike_count=location.strike_count,
        item_types=[
            ItemCapacityOut(item_type=i.item_type.value, daily_capacity=i.daily_capacity)
            for i in item_types_result.scalars().all()
        ],
        hours=[
            DayHoursOut(
                weekday=h.weekday,
                open_time=h.open_time.isoformat(),
                close_time=h.close_time.isoformat(),
            )
            for h in hours_result.scalars().all()
        ],
    )
