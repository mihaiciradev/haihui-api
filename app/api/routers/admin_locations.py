import re
import secrets
from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import AdminIdentity, DbSession, get_current_admin
from app.core.events import write_event
from app.core.http import client_ip
from app.core.security import generate_opaque_token, hash_secret
from app.models.city import City
from app.models.enums import ActorType, LocationStatus, StaffRole
from app.models.location import Location, LocationHours, LocationItemType
from app.models.staff import LocationLoginToken, StaffMember
from app.schemas.location import (
    DayHours,
    LocationCreateRequest,
    LocationCreateResponse,
    LocationSummary,
)

router = APIRouter(prefix="/admin/locations", tags=["admin-locations"])

_DEFAULT_OPEN = time(8, 0)
_DEFAULT_CLOSE = time(20, 0)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "location"


async def _unique_slug(db: DbSession, base: str) -> str:
    candidate = base
    suffix = 2
    while True:
        result = await db.execute(select(Location.id).where(Location.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


@router.post("", response_model=LocationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_location(
    body: LocationCreateRequest,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> LocationCreateResponse:
    """Admin onboards a new partner business: the location itself, its
    accepted item types + daily capacity, its weekly hours template, a
    printable login QR token, and its first owner login (name + PIN).
    """
    city_result = await db.execute(select(City).where(City.slug == body.city_slug))
    city = city_result.scalar_one_or_none()
    if city is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown city_slug: {body.city_slug}")

    slug = await _unique_slug(db, _slugify(body.name))
    utm_code = secrets.token_hex(4)

    location = Location(
        city_id=city.id,
        name=body.name,
        slug=slug,
        address=body.address,
        lat=body.lat,
        lng=body.lng,
        description_ro=body.description_ro,
        description_en=body.description_en,
        google_maps_url=body.google_maps_url,
        google_review_url=body.google_review_url,
        status=LocationStatus.active,
        revenue_share_pct=body.revenue_share_pct,
        utm_code=utm_code,
        created_by_admin=admin.admin_user_id,
    )
    db.add(location)
    await db.flush()

    for item in body.item_types:
        db.add(
            LocationItemType(
                location_id=location.id,
                item_type=item.item_type,
                daily_capacity=item.daily_capacity,
            )
        )

    hours = body.hours or [
        DayHours(weekday=w, open_time=_DEFAULT_OPEN, close_time=_DEFAULT_CLOSE)
        for w in range(7)
    ]
    for h in hours:
        db.add(
            LocationHours(
                location_id=location.id,
                weekday=h.weekday,
                open_time=h.open_time,
                close_time=h.close_time,
            )
        )

    raw_token, token_hash = generate_opaque_token()
    db.add(LocationLoginToken(location_id=location.id, token_hash=token_hash))

    owner = StaffMember(
        location_id=location.id,
        name=body.owner_name,
        pin_hash=hash_secret(body.owner_pin),
        role=StaffRole.owner,
    )
    db.add(owner)
    await db.flush()

    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="location",
        entity_id=location.id,
        action="location_created",
        payload={"name": body.name, "city_slug": body.city_slug},
        ip=client_ip(request),
    )

    await db.commit()
    return LocationCreateResponse(
        id=str(location.id),
        slug=location.slug,
        utm_code=location.utm_code,
        location_login_token=raw_token,
        owner_staff_id=str(owner.id),
    )


@router.get("", response_model=list[LocationSummary])
async def list_locations(
    db: DbSession, admin: AdminIdentity = Depends(get_current_admin)  # noqa: B008
) -> list[LocationSummary]:
    result = await db.execute(
        select(Location, City.slug)
        .join(City, City.id == Location.city_id)
        .order_by(Location.created_at.desc())
    )
    return [
        LocationSummary(
            id=str(loc.id),
            name=loc.name,
            slug=loc.slug,
            city_slug=city_slug,
            status=loc.status.value,
            created_at=loc.created_at.isoformat(),
        )
        for loc, city_slug in result.all()
    ]
