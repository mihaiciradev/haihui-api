import random
import string
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.api.routers.locations import _current_prices
from app.config import get_settings
from app.core.email import send_email
from app.core.email_templates import render_email
from app.core.events import write_event
from app.core.http import client_ip
from app.core.rate_limit import check_rate_limit
from app.core.security import generate_opaque_token, hash_opaque_token
from app.models.booking import Booking, BookingItem, BookingQrToken
from app.models.enums import ActorType, BookingStatus, LocationStatus
from app.models.location import Location, LocationItemType, LocationOverride
from app.schemas.booking import (
    BookingCreateRequest,
    BookingCreateResponse,
    BookingDetail,
    BookingItemOut,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])

MAX_DAYS_AHEAD = 31


def _generate_code() -> str:
    return "HH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


async def _unique_code(db: DbSession) -> str:
    for _ in range(10):
        candidate = _generate_code()
        result = await db.execute(select(Booking.id).where(Booking.code == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not allocate booking code")


async def _is_location_open(db: DbSession, location_id, storage_date: date) -> bool:
    """Openness for a given date is: no override, or an override that isn't
    marked closed (§5.6 -- override beats the weekly template, and every
    location always has all 7 weekdays populated in the weekly template).
    """
    result = await db.execute(
        select(LocationOverride).where(
            LocationOverride.location_id == location_id,
            LocationOverride.date == storage_date,
        )
    )
    override = result.scalar_one_or_none()
    if override is not None and override.closed:
        return False
    return True


@router.post("", response_model=BookingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: BookingCreateRequest, request: Request, db: DbSession
) -> BookingCreateResponse:
    """Guest checkout, no auth required (§3.1). Payment is not wired up yet
    -- bookings are confirmed immediately on creation rather than starting
    in pending_payment, by explicit product decision. Capacity is enforced
    race-safely via a row lock on each requested LocationItemType (§5.4).
    """
    check_rate_limit(
        f"booking-create:ip:{client_ip(request)}", max_attempts=20, window_seconds=3600
    )

    today = date.today()
    if body.storage_date < today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "storage_date cannot be in the past")
    if body.storage_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"storage_date must be within {MAX_DAYS_AHEAD} days"
        )

    location_result = await db.execute(
        select(Location).where(
            Location.slug == body.location_slug, Location.status == LocationStatus.active
        )
    )
    location = location_result.scalar_one_or_none()
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")

    if not await _is_location_open(db, location.id, body.storage_date):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Location is closed on that date")

    prices = await _current_prices(db)

    # Lock each requested item type's capacity row for the duration of the
    # transaction so concurrent bookings for the last remaining slot can't
    # both succeed (§5.4). Order by item_type name to avoid deadlocks
    # between two requests locking the same rows in different orders.
    for item in sorted(body.items, key=lambda i: i.item_type.value):
        capacity_result = await db.execute(
            select(LocationItemType)
            .where(
                LocationItemType.location_id == location.id,
                LocationItemType.item_type == item.item_type,
            )
            .with_for_update()
        )
        capacity_row = capacity_result.scalar_one_or_none()
        if capacity_row is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"This location does not accept item_type={item.item_type.value}",
            )
        if item.item_type.value not in prices:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"No current price for {item.item_type.value}"
            )

        used_result = await db.execute(
            select(BookingItem.qty, Booking.status)
            .join(Booking, Booking.id == BookingItem.booking_id)
            .where(
                Booking.location_id == location.id,
                Booking.storage_date == body.storage_date,
                BookingItem.item_type == item.item_type,
                Booking.status.notin_([BookingStatus.cancelled, BookingStatus.expired]),
            )
        )
        used = sum(qty for qty, _ in used_result.all())
        if used + item.qty > capacity_row.daily_capacity:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Not enough capacity for {item.item_type.value} on {body.storage_date}",
            )

    amount_total = sum(prices[item.item_type.value] * item.qty for item in body.items)
    code = await _unique_code(db)

    booking = Booking(
        code=code,
        guest_email=body.guest_email,
        guest_phone=body.guest_phone,
        location_id=location.id,
        storage_date=body.storage_date,
        status=BookingStatus.confirmed,
        amount_total=amount_total,
        currency="RON",
        source=body.source,
        utm_campaign=body.utm_campaign,
        utm_source=body.utm_source,
        utm_medium=body.utm_medium,
        locale=body.locale,
        revenue_share_pct_snapshot=location.revenue_share_pct,
    )
    db.add(booking)
    await db.flush()

    items_out = []
    for item in body.items:
        unit_price = prices[item.item_type.value]
        db.add(
            BookingItem(
                booking_id=booking.id,
                item_type=item.item_type,
                qty=item.qty,
                unit_price_snapshot=unit_price,
            )
        )
        items_out.append(
            BookingItemOut(
                item_type=item.item_type.value, qty=item.qty, unit_price_snapshot=unit_price
            )
        )

    raw_token, token_hash = generate_opaque_token()
    db.add(BookingQrToken(booking_id=booking.id, token_hash=token_hash, active=True))

    await write_event(
        db,
        actor_type=ActorType.user if booking.user_id else ActorType.system,
        actor_id=booking.user_id,
        entity_type="booking",
        entity_id=booking.id,
        action="booking_created",
        payload={"location_id": str(location.id), "storage_date": body.storage_date.isoformat()},
        ip=client_ip(request),
    )

    await _send_confirmation_email(db, booking, location, raw_token, items_out)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Booking could not be created, try again"
        ) from exc

    return BookingCreateResponse(
        code=booking.code,
        booking_token=raw_token,
        status=booking.status.value,
        storage_date=booking.storage_date.isoformat(),
        amount_total=float(booking.amount_total),
        currency=booking.currency,
        items=items_out,
    )


async def _send_confirmation_email(db, booking, location, raw_token, items_out) -> None:
    settings = get_settings()
    link = f"{settings.public_base_url}/booking/{raw_token}"
    items_lines = "".join(
        f"<li>{i.qty} x {i.item_type} &mdash; {i.unit_price_snapshot:.2f} RON/zi</li>"
        for i in items_out
    )
    body_html = (
        f"<p>Rezervarea ta la <strong>{location.name}</strong> este confirmată.</p>"
        f"<p><strong>Cod rezervare:</strong> {booking.code}<br>"
        f"<strong>Data depozitării:</strong> {booking.storage_date.isoformat()}<br>"
        f"<strong>Adresă:</strong> {location.address}</p>"
        f"<ul style=\"padding-left:18px;\">{items_lines}</ul>"
        f"<p><strong>Total: {float(booking.amount_total):.2f} RON</strong></p>"
        "<p>Arată codul QR de mai jos la sosire.</p>"
    )
    html = render_email(
        preheader=f"Rezervarea ta {booking.code} este confirmată",
        heading="Rezervare confirmată",
        body_html=body_html,
        locale=booking.locale.value,
        cta_label="Vezi rezervarea",
        cta_url=link,
    )
    await send_email(
        db,
        to=booking.guest_email,
        subject=f"Rezervare confirmată {booking.code} — HaiHui Storage",
        html=html,
        template="booking_confirmation",
        related_booking_id=booking.id,
    )


@router.get("/{token}", response_model=BookingDetail)
async def get_booking(token: str, db: DbSession) -> BookingDetail:
    """The traveler's own permanent booking link (§5.1) -- looked up by the
    long, unguessable QR token, not the short human code, since the code
    alone isn't a secure access credential.
    """
    token_hash = hash_opaque_token(token)
    result = await db.execute(select(BookingQrToken).where(BookingQrToken.token_hash == token_hash))
    qr_token = result.scalar_one_or_none()
    if qr_token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    booking_result = await db.execute(select(Booking).where(Booking.id == qr_token.booking_id))
    booking = booking_result.scalar_one()

    location_result = await db.execute(select(Location).where(Location.id == booking.location_id))
    location = location_result.scalar_one()

    items_result = await db.execute(select(BookingItem).where(BookingItem.booking_id == booking.id))
    items = [
        BookingItemOut(
            item_type=i.item_type.value, qty=i.qty, unit_price_snapshot=float(i.unit_price_snapshot)
        )
        for i in items_result.scalars().all()
    ]

    return BookingDetail(
        code=booking.code,
        status=booking.status.value,
        storage_date=booking.storage_date.isoformat(),
        amount_total=float(booking.amount_total),
        currency=booking.currency,
        items=items,
        location_name=location.name,
        location_address=location.address,
        location_slug=location.slug,
        created_at=booking.created_at.isoformat(),
    )
