from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import DbSession, StaffIdentity, require_owner
from app.core.events import write_event
from app.core.http import client_ip
from app.core.location_overrides import delete_override, list_overrides, upsert_override
from app.core.location_photos import (
    add_location_photo,
    public_photo_urls,
    remove_location_photo,
    to_photo_outs,
)
from app.core.storage import StorageNotConfigured
from app.models.city import City
from app.models.enums import ActorType
from app.models.location import Location, LocationHours, LocationItemType
from app.schemas.location import DayHoursOut, ItemCapacityOut, LocationProfileResponse
from app.schemas.location_override import OverrideCreateRequest, OverrideOut
from app.schemas.location_photo import LocationPhotoOut

router = APIRouter(prefix="/partner", tags=["partner-location"])


async def _get_own_location(db: DbSession, identity: StaffIdentity) -> Location:
    result = await db.execute(select(Location).where(Location.id == identity.location_id))
    location = result.scalar_one_or_none()
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return location


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
        photos=public_photo_urls(location),
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


@router.get("/location/overrides", response_model=list[OverrideOut])
async def get_location_overrides(
    db: DbSession, identity: StaffIdentity = Depends(require_owner)  # noqa: B008
) -> list[OverrideOut]:
    return await list_overrides(db, identity.location_id)


@router.post("/location/overrides", response_model=OverrideOut, status_code=status.HTTP_201_CREATED)
async def set_location_override(
    body: OverrideCreateRequest,
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(require_owner),  # noqa: B008
) -> OverrideOut:
    """A holiday closure or special hours for one date -- overrides the
    weekly template for that date only (§5.6). Owner-managed so a shop
    doesn't need to contact admin every time they close for a day.
    """
    result = await upsert_override(db, identity.location_id, body, created_by="owner")
    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="location",
        entity_id=identity.location_id,
        action="schedule_override_set",
        payload={"date": body.date.isoformat(), "closed": body.closed},
        ip=client_ip(request),
    )
    await db.commit()
    return result


@router.delete("/location/overrides/{target_date}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_location_override(
    target_date: date,
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(require_owner),  # noqa: B008
) -> None:
    removed = await delete_override(db, identity.location_id, target_date)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No override for that date")
    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="location",
        entity_id=identity.location_id,
        action="schedule_override_removed",
        payload={"date": target_date.isoformat()},
        ip=client_ip(request),
    )
    await db.commit()


@router.get("/location/photos", response_model=list[LocationPhotoOut])
async def list_location_photos(
    db: DbSession, identity: StaffIdentity = Depends(require_owner)  # noqa: B008
) -> list[LocationPhotoOut]:
    location = await _get_own_location(db, identity)
    try:
        return to_photo_outs(location)
    except StorageNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Photo storage is not configured yet"
        ) from exc


@router.post(
    "/location/photos", response_model=LocationPhotoOut, status_code=status.HTTP_201_CREATED
)
async def upload_location_photo(
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(require_owner),  # noqa: B008
    photo: UploadFile = File(...),  # noqa: B008
) -> LocationPhotoOut:
    """Marketing photos shown on the public listing/search pages -- distinct
    from bag-photo evidence, which is private per-booking proof, not public.
    """
    location = await _get_own_location(db, identity)
    data = await photo.read()
    try:
        await add_location_photo(location, photo.content_type, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StorageNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Photo storage is not configured yet"
        ) from exc

    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="location",
        entity_id=identity.location_id,
        action="location_photo_uploaded",
        payload={"location_name": location.name},
        ip=client_ip(request),
    )
    await db.commit()
    return to_photo_outs(location)[-1]


@router.delete("/location/photos/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location_photo(
    key: str,
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(require_owner),  # noqa: B008
) -> None:
    location = await _get_own_location(db, identity)
    if not remove_location_photo(location, key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")

    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="location",
        entity_id=identity.location_id,
        action="location_photo_removed",
        payload={"location_name": location.name},
        ip=client_ip(request),
    )
    await db.commit()
