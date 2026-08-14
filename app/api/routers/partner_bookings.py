import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import DbSession, StaffIdentity, get_current_staff
from app.core.events import write_event
from app.core.http import client_ip
from app.core.security import hash_opaque_token
from app.core.storage import StorageNotConfigured, presigned_get_url, upload_bytes
from app.models.booking import BagPhoto, Booking, BookingItem, BookingQrToken
from app.models.enums import ActorType, BookingStatus
from app.models.location import Location
from app.schemas.booking import BagPhotoOut, BookingItemOut, PartnerBookingOut

router = APIRouter(prefix="/partner", tags=["partner-bookings"])

_ALLOWED_PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_PHOTO_BYTES = 8 * 1024 * 1024


async def _build_partner_out(db: DbSession, bookings: list[Booking]) -> list[PartnerBookingOut]:
    if not bookings:
        return []
    booking_ids = [b.id for b in bookings]

    items_result = await db.execute(
        select(BookingItem).where(BookingItem.booking_id.in_(booking_ids))
    )
    items_by_booking: dict[uuid.UUID, list[BookingItem]] = {}
    for item in items_result.scalars().all():
        items_by_booking.setdefault(item.booking_id, []).append(item)

    photos_result = await db.execute(
        select(BagPhoto.booking_id).where(BagPhoto.booking_id.in_(booking_ids))
    )
    photo_counts: dict[uuid.UUID, int] = {}
    for booking_id in photos_result.scalars().all():
        photo_counts[booking_id] = photo_counts.get(booking_id, 0) + 1

    return [
        PartnerBookingOut(
            id=str(b.id),
            code=b.code,
            status=b.status.value,
            storage_date=b.storage_date.isoformat(),
            pickup_date=b.pickup_date.isoformat(),
            guest_email=b.guest_email,
            guest_phone=b.guest_phone,
            amount_total=float(b.amount_total),
            currency=b.currency,
            items=[
                BookingItemOut(
                    item_type=i.item_type.value,
                    qty=i.qty,
                    unit_price_snapshot=float(i.unit_price_snapshot),
                )
                for i in items_by_booking.get(b.id, [])
            ],
            created_at=b.created_at.isoformat(),
            checked_in_at=b.checked_in_at.isoformat() if b.checked_in_at else None,
            checked_out_at=b.released_at.isoformat() if b.released_at else None,
            photo_count=photo_counts.get(b.id, 0),
        )
        for b in bookings
    ]


async def list_location_bookings(db: DbSession, location_id: uuid.UUID) -> list[PartnerBookingOut]:
    """Shared by both the partner dashboard and the admin per-shop view --
    upcoming and recent bookings for a location, newest storage_date first.
    """
    bookings_result = await db.execute(
        select(Booking)
        .where(Booking.location_id == location_id)
        .order_by(Booking.storage_date.desc(), Booking.created_at.desc())
        .limit(200)
    )
    return await _build_partner_out(db, list(bookings_result.scalars().all()))


async def _get_scoped_booking(
    db: DbSession, booking_id: uuid.UUID, location_id: uuid.UUID
) -> Booking:
    """Every check-in/check-out/photo action must be scoped to the acting
    staff member's own location -- otherwise staff at one shop could act on
    another shop's bookings just by guessing a booking id.
    """
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id, Booking.location_id == location_id)
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return booking


async def _event_payload(db: DbSession, booking: Booking, location_id: uuid.UUID) -> dict:
    """Common context for booking-action audit events -- enough for the
    admin log to render a full sentence without a follow-up lookup.
    """
    location_result = await db.execute(select(Location.name).where(Location.id == location_id))
    items_result = await db.execute(
        select(BookingItem.item_type, BookingItem.qty).where(BookingItem.booking_id == booking.id)
    )
    return {
        "code": booking.code,
        "location_id": str(location_id),
        "location_name": location_result.scalar_one_or_none(),
        "guest_email": booking.guest_email,
        "items": [
            {"item_type": item_type.value, "qty": qty} for item_type, qty in items_result.all()
        ],
    }


@router.get("/bookings", response_model=list[PartnerBookingOut])
async def get_partner_bookings(
    db: DbSession, identity: StaffIdentity = Depends(get_current_staff)  # noqa: B008
) -> list[PartnerBookingOut]:
    """Any staff role can view -- owners and regular staff both need to see
    who's coming in, not just owners.
    """
    return await list_location_bookings(db, identity.location_id)


@router.get("/bookings/lookup", response_model=PartnerBookingOut)
async def lookup_booking(
    db: DbSession,
    identity: StaffIdentity = Depends(get_current_staff),  # noqa: B008
    token: str | None = Query(default=None, description="Raw token from the scanned QR"),
    code: str | None = Query(default=None, description="Human booking code, e.g. HH-AB12C"),
) -> PartnerBookingOut:
    """Staff resolves a booking either by scanning the traveler's QR (token)
    or typing the short code as a fallback when a scan fails. Only ever
    returns bookings for the staff member's own location.
    """
    if not token and not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide either token or code")

    booking: Booking | None = None
    if token:
        token_hash = hash_opaque_token(token)
        qr_result = await db.execute(
            select(BookingQrToken).where(BookingQrToken.token_hash == token_hash)
        )
        qr_token = qr_result.scalar_one_or_none()
        if qr_token is not None:
            result = await db.execute(
                select(Booking).where(
                    Booking.id == qr_token.booking_id, Booking.location_id == identity.location_id
                )
            )
            booking = result.scalar_one_or_none()
    elif code:
        result = await db.execute(
            select(Booking).where(
                Booking.code == code.strip().upper(), Booking.location_id == identity.location_id
            )
        )
        booking = result.scalar_one_or_none()

    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return (await _build_partner_out(db, [booking]))[0]


@router.post("/bookings/{booking_id}/check-in", response_model=PartnerBookingOut)
async def check_in_booking(
    booking_id: uuid.UUID,
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(get_current_staff),  # noqa: B008
) -> PartnerBookingOut:
    booking = await _get_scoped_booking(db, booking_id, identity.location_id)
    if booking.status != BookingStatus.confirmed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Booking cannot be checked in from status '{booking.status.value}'",
        )

    booking.status = BookingStatus.stored
    booking.checked_in_at = datetime.now(UTC)
    booking.checked_in_staff_id = identity.staff_id

    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="booking",
        entity_id=booking.id,
        action="booking_checked_in",
        payload=await _event_payload(db, booking, identity.location_id),
        ip=client_ip(request),
    )
    await db.commit()
    return (await _build_partner_out(db, [booking]))[0]


@router.post("/bookings/{booking_id}/check-out", response_model=PartnerBookingOut)
async def check_out_booking(
    booking_id: uuid.UUID,
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(get_current_staff),  # noqa: B008
) -> PartnerBookingOut:
    booking = await _get_scoped_booking(db, booking_id, identity.location_id)
    if booking.status != BookingStatus.stored:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Booking cannot be checked out from status '{booking.status.value}'",
        )

    booking.status = BookingStatus.released
    booking.released_at = datetime.now(UTC)
    booking.checked_out_staff_id = identity.staff_id

    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="booking",
        entity_id=booking.id,
        action="booking_checked_out",
        payload=await _event_payload(db, booking, identity.location_id),
        ip=client_ip(request),
    )
    await db.commit()
    return (await _build_partner_out(db, [booking]))[0]


@router.post(
    "/bookings/{booking_id}/photos", response_model=BagPhotoOut, status_code=status.HTTP_201_CREATED
)
async def upload_bag_photo(
    booking_id: uuid.UUID,
    request: Request,
    db: DbSession,
    identity: StaffIdentity = Depends(get_current_staff),  # noqa: B008
    photo: UploadFile = File(...),  # noqa: B008
) -> BagPhotoOut:
    """Photo evidence taken at drop-off, attributed to the staff member who
    took it -- the audit trail for storage disputes (§3.2).
    """
    booking = await _get_scoped_booking(db, booking_id, identity.location_id)

    ext = _ALLOWED_PHOTO_TYPES.get(photo.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo must be JPEG, PNG, or WEBP")

    data = await photo.read()
    if len(data) > _MAX_PHOTO_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo must be under 8MB")

    key = f"bookings/{booking.id}/{uuid.uuid4()}.{ext}"
    try:
        upload_bytes(key, data, photo.content_type or "application/octet-stream")
    except StorageNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Photo storage is not configured yet"
        ) from exc

    bag_photo = BagPhoto(
        booking_id=booking.id,
        r2_key=key,
        taken_by_staff_id=identity.staff_id,
        taken_at=datetime.now(UTC),
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )
    db.add(bag_photo)
    await db.flush()

    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=identity.staff_id,
        entity_type="booking",
        entity_id=booking.id,
        action="bag_photo_uploaded",
        payload={
            "code": booking.code,
            "location_id": str(identity.location_id),
            "size_bytes": len(data),
        },
        ip=client_ip(request),
    )
    await db.commit()

    return BagPhotoOut(
        id=str(bag_photo.id),
        url=presigned_get_url(key),
        taken_at=bag_photo.taken_at.isoformat(),
    )


@router.get("/bookings/{booking_id}/photos", response_model=list[BagPhotoOut])
async def list_bag_photos(
    booking_id: uuid.UUID,
    db: DbSession,
    identity: StaffIdentity = Depends(get_current_staff),  # noqa: B008
) -> list[BagPhotoOut]:
    booking = await _get_scoped_booking(db, booking_id, identity.location_id)
    result = await db.execute(
        select(BagPhoto).where(BagPhoto.booking_id == booking.id).order_by(BagPhoto.taken_at)
    )
    photos = result.scalars().all()
    try:
        return [
            BagPhotoOut(
                id=str(p.id), url=presigned_get_url(p.r2_key), taken_at=p.taken_at.isoformat()
            )
            for p in photos
        ]
    except StorageNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Photo storage is not configured yet"
        ) from exc
