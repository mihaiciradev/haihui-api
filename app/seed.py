"""Seed script for local/staging environments.

Creates: 3 cities, 4 demo hosts with hours + capacity, staff PINs, the
platform price list, and demo bookings in every status (§2.2).

Usage:
    python -m app.seed

Safe to re-run: it is idempotent per city/location slug and price_list
valid_from, but will add a fresh batch of demo bookings each run (each gets
a new random code) — run against a disposable DB, not production.
"""

import asyncio
import hashlib
import random
import secrets
import string
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from app.core.security import generate_opaque_token, hash_secret
from app.database import AsyncSessionLocal
from app.models.booking import BagPhoto, Booking, BookingItem, BookingQrToken
from app.models.city import City
from app.models.enums import (
    BookingStatus,
    ItemType,
    LocationStatus,
    PaymentStatus,
    RefundReason,
    StaffRole,
)
from app.models.location import Location, LocationHours, LocationItemType, PriceListEntry
from app.models.payment import Payment, Refund
from app.models.staff import LocationLoginToken, StaffMember

PRICES = {ItemType.bag: 16.00, ItemType.trolley: 29.00, ItemType.oversized: 39.00}

CITIES = [
    ("brasov", "Brașov", "Brasov"),
    ("bucuresti", "București", "Bucharest"),
    ("timisoara", "Timișoara", "Timisoara"),
]

LOCATIONS = [
    dict(
        city_slug="brasov",
        name="Suvenire Sfatului",
        slug="suvenire-sfatului-brasov",
        address="Piața Sfatului 12, Brașov",
        lat=45.6427,
        lng=25.5887,
    ),
    dict(
        city_slug="brasov",
        name="Minimarket Poarta Schei",
        slug="minimarket-poarta-schei-brasov",
        address="Str. Poarta Schei 3, Brașov",
        lat=45.6362,
        lng=25.5773,
    ),
    dict(
        city_slug="bucuresti",
        name="Pensiune Lipscani Central",
        slug="pensiune-lipscani-central-bucuresti",
        address="Str. Lipscani 45, București",
        lat=44.4308,
        lng=26.1015,
    ),
    dict(
        city_slug="timisoara",
        name="Chioșc Piața Unirii",
        slug="chiosc-piata-unirii-timisoara",
        address="Piața Unirii 8, Timișoara",
        lat=45.7563,
        lng=21.2258,
    ),
]


def _short_code() -> str:
    return "HH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


def _utm_code() -> str:
    return secrets.token_hex(4)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        cities_by_slug: dict[str, City] = {}
        for slug, name_ro, name_en in CITIES:
            city_result = await db.execute(select(City).where(City.slug == slug))
            city = city_result.scalar_one_or_none()
            if city is None:
                city = City(slug=slug, name_ro=name_ro, name_en=name_en)
                db.add(city)
                await db.flush()
            cities_by_slug[slug] = city

        today = date.today()
        for item_type, price in PRICES.items():
            price_result = await db.execute(
                select(PriceListEntry).where(
                    PriceListEntry.item_type == item_type, PriceListEntry.valid_from == today
                )
            )
            if price_result.scalar_one_or_none() is None:
                db.add(PriceListEntry(item_type=item_type, price_ron=price, valid_from=today))

        locations: list[Location] = []
        for spec in LOCATIONS:
            loc_result = await db.execute(select(Location).where(Location.slug == spec["slug"]))
            loc = loc_result.scalar_one_or_none()
            if loc is None:
                loc = Location(
                    city_id=cities_by_slug[str(spec["city_slug"])].id,
                    name=spec["name"],
                    slug=spec["slug"],
                    address=spec["address"],
                    lat=spec["lat"],
                    lng=spec["lng"],
                    description_ro=f"Depozitare bagaje sigură la {spec['name']}.",
                    description_en=f"Secure luggage storage at {spec['name']}.",
                    status=LocationStatus.active,
                    utm_code=_utm_code(),
                )
                db.add(loc)
                await db.flush()

                for weekday in range(7):
                    db.add(
                        LocationHours(
                            location_id=loc.id,
                            weekday=weekday,
                            open_time=time(8, 0),
                            close_time=time(20, 0),
                        )
                    )
                for item_type, capacity in (
                    (ItemType.bag, 20),
                    (ItemType.trolley, 10),
                    (ItemType.oversized, 4),
                ):
                    db.add(
                        LocationItemType(
                            location_id=loc.id, item_type=item_type, daily_capacity=capacity
                        )
                    )

                raw_token, token_hash = generate_opaque_token()
                db.add(LocationLoginToken(location_id=loc.id, token_hash=token_hash))
                print(f"[{spec['slug']}] login QR token (raw, print once): {raw_token}")

                owner = StaffMember(
                    location_id=loc.id,
                    name="Owner Demo",
                    pin_hash=hash_secret("1234"),
                    role=StaffRole.owner,
                )
                staff = StaffMember(
                    location_id=loc.id,
                    name="Staff Demo",
                    pin_hash=hash_secret("5678"),
                    role=StaffRole.staff,
                )
                db.add_all([owner, staff])
                await db.flush()
                print(f"[{spec['slug']}] owner PIN=1234 ({owner.id}), staff PIN=5678 ({staff.id})")

            locations.append(loc)

        await db.flush()
        await _seed_demo_bookings(db, locations)
        await db.commit()
        print("Seed complete.")


async def _seed_demo_bookings(db, locations: list[Location]) -> None:
    now = datetime.now(UTC)
    loc = locations[0]

    result = await db.execute(select(StaffMember).where(StaffMember.location_id == loc.id))
    staff_member = result.scalars().first()

    def make_booking(status: BookingStatus, storage_date: date, **overrides) -> Booking:
        qty = 1
        unit_price = PRICES[ItemType.bag]
        booking = Booking(
            code=_short_code(),
            guest_email="demo.traveler@example.com",
            guest_phone="+40700000000",
            location_id=loc.id,
            storage_date=storage_date,
            status=status,
            amount_total=unit_price * qty,
            revenue_share_pct_snapshot=loc.revenue_share_pct,
            **overrides,
        )
        db.add(booking)
        return booking

    scenarios = [
        (BookingStatus.pending_payment, today_plus(1), {}),
        (BookingStatus.confirmed, today_plus(2), {}),
        (BookingStatus.stored, today_plus(0), {}),
        (BookingStatus.released, today_plus(0), {"released_at": now}),
        (
            BookingStatus.closed,
            today_plus(-1),
            {
                "released_at": now - timedelta(days=1),
                "traveler_confirmed_at": now - timedelta(hours=20),
            },
        ),
        (BookingStatus.expired, today_plus(-2), {}),
        (BookingStatus.cancelled, today_plus(3), {}),
        (BookingStatus.no_show, today_plus(-1), {}),
    ]

    for status, storage_date, overrides in scenarios:
        booking = make_booking(status, storage_date, **overrides)
        await db.flush()
        db.add(
            BookingItem(
                booking_id=booking.id,
                item_type=ItemType.bag,
                qty=1,
                unit_price_snapshot=PRICES[ItemType.bag],
            )
        )

        if status != BookingStatus.pending_payment:
            _, token_hash = generate_opaque_token()
            db.add(
                BookingQrToken(
                    booking_id=booking.id,
                    token_hash=token_hash,
                    active=status
                    not in (BookingStatus.released, BookingStatus.closed, BookingStatus.cancelled),
                )
            )

        if status in (
            BookingStatus.confirmed,
            BookingStatus.stored,
            BookingStatus.released,
            BookingStatus.closed,
            BookingStatus.expired,
            BookingStatus.no_show,
        ):
            db.add(
                Payment(
                    booking_id=booking.id,
                    stripe_checkout_session_id=f"cs_test_{secrets.token_hex(8)}",
                    payment_intent_id=f"pi_test_{secrets.token_hex(8)}",
                    status=PaymentStatus.succeeded,
                    amount=booking.amount_total,
                )
            )

        if status == BookingStatus.cancelled:
            db.add(
                Refund(
                    booking_id=booking.id,
                    amount=booking.amount_total,
                    reason=RefundReason.traveler_cancel,
                    stripe_refund_id=f"re_test_{secrets.token_hex(8)}",
                    initiated_by="traveler",
                )
            )

        if (
            status in (BookingStatus.stored, BookingStatus.released, BookingStatus.closed)
            and staff_member
        ):
            db.add(
                BagPhoto(
                    booking_id=booking.id,
                    r2_key=f"demo/{booking.id}/bag-1.jpg",
                    taken_by_staff_id=staff_member.id,
                    taken_at=now,
                    sha256=hashlib.sha256(str(booking.id).encode()).hexdigest(),
                )
            )


def today_plus(days: int) -> date:
    return date.today() + timedelta(days=days)


if __name__ == "__main__":
    asyncio.run(main())
