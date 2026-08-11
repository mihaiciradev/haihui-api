import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DbSession, StaffIdentity, get_current_staff
from app.models.booking import Booking, BookingItem
from app.schemas.booking import BookingItemOut, PartnerBookingOut

router = APIRouter(prefix="/partner", tags=["partner-bookings"])


async def list_location_bookings(db: DbSession, location_id: uuid.UUID) -> list[PartnerBookingOut]:
    """Shared by both the partner dashboard and the admin per-shop view --
    upcoming and recent bookings for a location, newest storage_date first,
    regardless of check-in state (that isn't tracked yet).
    """
    bookings_result = await db.execute(
        select(Booking)
        .where(Booking.location_id == location_id)
        .order_by(Booking.storage_date.desc(), Booking.created_at.desc())
        .limit(200)
    )
    bookings = bookings_result.scalars().all()
    if not bookings:
        return []

    items_result = await db.execute(
        select(BookingItem).where(BookingItem.booking_id.in_([b.id for b in bookings]))
    )
    items_by_booking: dict[uuid.UUID, list[BookingItem]] = {}
    for item in items_result.scalars().all():
        items_by_booking.setdefault(item.booking_id, []).append(item)

    return [
        PartnerBookingOut(
            id=str(b.id),
            code=b.code,
            status=b.status.value,
            storage_date=b.storage_date.isoformat(),
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
        )
        for b in bookings
    ]


@router.get("/bookings", response_model=list[PartnerBookingOut])
async def get_partner_bookings(
    db: DbSession, identity: StaffIdentity = Depends(get_current_staff)  # noqa: B008
) -> list[PartnerBookingOut]:
    """Any staff role can view -- owners and regular staff both need to see
    who's coming in, not just owners (§ per product ask).
    """
    return await list_location_bookings(db, identity.location_id)
