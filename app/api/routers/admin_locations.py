import re
import secrets
import uuid
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select

from app.api.deps import AdminIdentity, DbSession, get_current_admin
from app.api.routers.partner_bookings import list_location_bookings
from app.core.events import write_event
from app.core.http import client_ip
from app.core.location_overrides import delete_override, list_overrides, upsert_override
from app.core.security import generate_opaque_token, hash_secret
from app.models.city import City
from app.models.enums import ActorType, LocationStatus, StaffRole
from app.models.location import Location, LocationHours, LocationItemType
from app.models.staff import LocationLoginToken, StaffMember
from app.schemas.booking import PartnerBookingOut
from app.schemas.location import (
    DayHours,
    DayHoursOut,
    ItemCapacityOut,
    LocationCreateRequest,
    LocationCreateResponse,
    LocationProfileResponse,
    LocationSummary,
    LocationUpdateRequest,
)
from app.schemas.location_override import OverrideCreateRequest, OverrideOut
from app.schemas.staff import (
    PinResetRequest,
    StaffCreateRequest,
    StaffCreateResponse,
    TokenRotateResponse,
)

router = APIRouter(prefix="/admin/locations", tags=["admin-locations"])
staff_router = APIRouter(prefix="/admin/staff", tags=["admin-locations"])

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


@router.patch("/{location_id}", response_model=LocationProfileResponse)
async def update_location(
    location_id: uuid.UUID,
    body: LocationUpdateRequest,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> LocationProfileResponse:
    """Everything set at creation is otherwise permanent -- capacity, item
    types, hours, address, revenue share, even whether the location is
    still active. Any field omitted from the body is left unchanged;
    item_types/hours, when given, fully replace the existing set rather
    than merging, same as on create.
    """
    result = await db.execute(
        select(Location, City.slug)
        .join(City, City.id == Location.city_id)
        .where(Location.id == location_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    location, city_slug = row

    fields_set = body.model_fields_set
    changed: list[str] = []
    for field in (
        "name",
        "address",
        "lat",
        "lng",
        "description_ro",
        "description_en",
        "google_maps_url",
        "google_review_url",
        "revenue_share_pct",
        "status",
    ):
        if field in fields_set:
            setattr(location, field, getattr(body, field))
            changed.append(field)

    if "item_types" in fields_set and body.item_types is not None:
        await db.execute(
            delete(LocationItemType).where(LocationItemType.location_id == location_id)
        )
        for item in body.item_types:
            db.add(
                LocationItemType(
                    location_id=location_id,
                    item_type=item.item_type,
                    daily_capacity=item.daily_capacity,
                )
            )
        changed.append("item_types")

    if "hours" in fields_set and body.hours is not None:
        await db.execute(delete(LocationHours).where(LocationHours.location_id == location_id))
        for h in body.hours:
            db.add(
                LocationHours(
                    location_id=location_id,
                    weekday=h.weekday,
                    open_time=h.open_time,
                    close_time=h.close_time,
                )
            )
        changed.append("hours")

    if not changed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="location",
        entity_id=location_id,
        action="location_updated",
        payload={"location_name": location.name, "fields": changed},
        ip=client_ip(request),
    )
    await db.commit()

    item_types_result = await db.execute(
        select(LocationItemType).where(LocationItemType.location_id == location_id)
    )
    hours_result = await db.execute(
        select(LocationHours)
        .where(LocationHours.location_id == location_id)
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


@router.post(
    "/{location_id}/staff",
    response_model=StaffCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_staff(
    location_id: uuid.UUID,
    body: StaffCreateRequest,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> StaffCreateResponse:
    """Location creation only sets up the first owner login -- real
    businesses need more than one staff member so scans stay attributable
    to a specific person (§3.2), hence this separate endpoint.
    """
    location_result = await db.execute(select(Location).where(Location.id == location_id))
    location = location_result.scalar_one_or_none()
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")

    staff = StaffMember(
        location_id=location_id,
        name=body.name,
        pin_hash=hash_secret(body.pin),
        role=body.role,
    )
    db.add(staff)
    await db.flush()

    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="staff_member",
        entity_id=staff.id,
        action="staff_added",
        payload={
            "location_id": str(location_id),
            "location_name": location.name,
            "staff_name": staff.name,
            "role": body.role.value,
        },
        ip=client_ip(request),
    )
    await db.commit()
    return StaffCreateResponse(staff_id=str(staff.id), name=staff.name, role=staff.role.value)


@staff_router.post("/{staff_id}/reset-pin", status_code=status.HTTP_204_NO_CONTENT)
async def reset_staff_pin(
    staff_id: uuid.UUID,
    body: PinResetRequest,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> None:
    """§3.2: 'PIN reset only via admin' -- also clears any active lockout,
    since a forgotten-PIN reset should unstick the account too.
    """
    result = await db.execute(select(StaffMember).where(StaffMember.id == staff_id))
    staff = result.scalar_one_or_none()
    if staff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")

    staff.pin_hash = hash_secret(body.new_pin)
    staff.failed_pin_attempts = 0
    staff.locked_until = None

    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="staff_member",
        entity_id=staff.id,
        action="pin_reset",
        payload={"staff_name": staff.name, "location_id": str(staff.location_id)},
        ip=client_ip(request),
    )
    await db.commit()


@router.post("/{location_id}/rotate-token", response_model=TokenRotateResponse)
async def rotate_location_token(
    location_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> TokenRotateResponse:
    """§3.2: 'admin can rotate a location's login token instantly if a card
    leaks'. Revokes every currently-active token for the location and issues
    a fresh one -- the old QR card stops working the moment this runs.
    """
    location_result = await db.execute(select(Location).where(Location.id == location_id))
    location = location_result.scalar_one_or_none()
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")

    active_tokens = await db.execute(
        select(LocationLoginToken).where(
            LocationLoginToken.location_id == location_id,
            LocationLoginToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for token in active_tokens.scalars().all():
        token.revoked_at = now

    raw_token, token_hash = generate_opaque_token()
    db.add(LocationLoginToken(location_id=location_id, token_hash=token_hash))

    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="location",
        entity_id=location_id,
        action="login_token_rotated",
        payload={"location_name": location.name},
        ip=client_ip(request),
    )
    await db.commit()
    return TokenRotateResponse(location_login_token=raw_token)


@router.get("/{location_id}/bookings", response_model=list[PartnerBookingOut])
async def admin_list_location_bookings(
    location_id: uuid.UUID,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> list[PartnerBookingOut]:
    """Same data the location's own partner dashboard sees, surfaced to
    admin so support/ops can look into a specific shop without needing its
    login PIN.
    """
    location_result = await db.execute(select(Location.id).where(Location.id == location_id))
    if location_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return await list_location_bookings(db, location_id)


@router.get("/{location_id}/overrides", response_model=list[OverrideOut])
async def admin_get_location_overrides(
    location_id: uuid.UUID,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> list[OverrideOut]:
    location_result = await db.execute(select(Location.id).where(Location.id == location_id))
    if location_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return await list_overrides(db, location_id)


@router.post(
    "/{location_id}/overrides", response_model=OverrideOut, status_code=status.HTTP_201_CREATED
)
async def admin_set_location_override(
    location_id: uuid.UUID,
    body: OverrideCreateRequest,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> OverrideOut:
    """Same as the owner-facing endpoint -- exists so support can set a
    closure on a partner's behalf without needing their login PIN.
    """
    location_result = await db.execute(select(Location.id).where(Location.id == location_id))
    if location_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")

    result = await upsert_override(db, location_id, body, created_by="admin")
    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="location",
        entity_id=location_id,
        action="schedule_override_set",
        payload={"date": body.date.isoformat(), "closed": body.closed},
        ip=client_ip(request),
    )
    await db.commit()
    return result


@router.delete("/{location_id}/overrides/{target_date}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_remove_location_override(
    location_id: uuid.UUID,
    target_date: date,
    request: Request,
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
) -> None:
    removed = await delete_override(db, location_id, target_date)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No override for that date")
    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.admin_user_id,
        entity_type="location",
        entity_id=location_id,
        action="schedule_override_removed",
        payload={"date": target_date.isoformat()},
        ip=client_ip(request),
    )
    await db.commit()
