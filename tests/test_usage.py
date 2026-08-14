import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret
from app.core.usage import compute_r2_usage
from app.core.usage_alerts import check_and_alert_usage
from app.models.audit import Event
from app.models.booking import BagPhoto, Booking
from app.models.city import City
from app.models.email_log import EmailLog
from app.models.enums import BookingStatus, LocationStatus, StaffRole
from app.models.location import Location
from app.models.staff import StaffMember
from app.models.user import User


async def _get_or_create_city(db, slug="usage-city") -> City:
    result = await db.execute(select(City).where(City.slug == slug))
    city = result.scalar_one_or_none()
    if city is None:
        city = City(slug=slug, name_ro="Oraș", name_en="City")
        db.add(city)
        await db.flush()
    return city


async def _seed_bag_photo(db, *, size_bytes: int, taken_at: datetime) -> BagPhoto:
    city = await _get_or_create_city(db)
    unique = uuid.uuid4().hex[:10]

    location = Location(
        city_id=city.id,
        name="Usage Test Host",
        slug=f"usage-test-host-{unique}",
        address="Str. Test 1",
        lat=45.0,
        lng=25.0,
        status=LocationStatus.active,
        utm_code=f"usage-{unique}",
    )
    db.add(location)
    await db.flush()

    staff = StaffMember(
        location_id=location.id, name="Staff", pin_hash=hash_secret("1234"), role=StaffRole.staff
    )
    db.add(staff)
    await db.flush()

    booking = Booking(
        code=f"HH-{unique.upper()}",
        guest_email="traveler@example.com",
        guest_phone="+40700000000",
        location_id=location.id,
        storage_date=date.today(),
        pickup_date=date.today(),
        status=BookingStatus.stored,
        amount_total=16.0,
        currency="RON",
        revenue_share_pct_snapshot=40,
    )
    db.add(booking)
    await db.flush()

    photo = BagPhoto(
        booking_id=booking.id,
        r2_key="test-key",
        taken_by_staff_id=staff.id,
        taken_at=taken_at,
        sha256="a" * 64,
        size_bytes=size_bytes,
    )
    db.add(photo)
    await db.commit()
    return photo


async def _create_admin_and_login(client, db, email="admin@haihui.ro") -> None:
    import pyotp

    secret = generate_totp_secret()
    admin = User(
        email=email,
        is_admin=True,
        admin_password_hash=hash_secret("supersecret1"),
        admin_totp_secret=secret,
        admin_totp_confirmed_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.commit()

    login = await client.post(
        "/admin/auth/login", json={"email": email, "password": "supersecret1"}
    )
    assert login.status_code == 200
    verify = await client.post("/admin/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200


async def test_compute_r2_usage_sums_storage_and_counts_this_month_uploads(db):
    now = datetime.now(UTC)
    await _seed_bag_photo(db, size_bytes=1000, taken_at=now)
    await _seed_bag_photo(db, size_bytes=2000, taken_at=now - timedelta(days=400))

    usage = await compute_r2_usage(db)
    assert usage["storage_bytes"] == 3000
    assert usage["uploads_this_month"] == 1
    assert usage["class_b_tracked"] is False


async def test_admin_usage_requires_admin_session(client):
    resp = await client.get("/admin/usage")
    assert resp.status_code == 401


async def test_admin_usage_returns_current_totals(client, db):
    await _seed_bag_photo(db, size_bytes=5000, taken_at=datetime.now(UTC))
    await _create_admin_and_login(client, db)

    resp = await client.get("/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["r2"]["storage_bytes"] == 5000
    assert body["r2"]["storage_limit_bytes"] == 10 * 1024**3


async def test_usage_alert_sends_once_when_over_threshold(db):
    # size_bytes is a 32-bit column (a single photo is capped at 8MB by the
    # upload endpoint) -- spread the 9GB total across several rows so no
    # single row overflows an int32, unlike a real one-photo-per-upload row.
    for _ in range(5):
        await _seed_bag_photo(db, size_bytes=1_800_000_000, taken_at=datetime.now(UTC))

    await check_and_alert_usage()

    events = await db.execute(select(Event).where(Event.entity_type == "usage_alert"))
    assert len(events.scalars().all()) == 1

    emails = await db.execute(select(EmailLog).where(EmailLog.template == "usage_alert"))
    assert len(emails.scalars().all()) == 1

    # running again the same day must not send a second alert
    await check_and_alert_usage()
    events_after = await db.execute(select(Event).where(Event.entity_type == "usage_alert"))
    assert len(events_after.scalars().all()) == 1


async def test_usage_alert_does_not_send_when_under_threshold(db):
    await _seed_bag_photo(db, size_bytes=1000, taken_at=datetime.now(UTC))

    await check_and_alert_usage()

    events = await db.execute(select(Event).where(Event.entity_type == "usage_alert"))
    assert len(events.scalars().all()) == 0
