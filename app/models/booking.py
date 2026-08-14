import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import BookingStatus, ItemType, Locale


class Booking(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "bookings"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    guest_email: Mapped[str] = mapped_column(CITEXT, nullable=False, index=True)
    guest_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False, index=True
    )
    storage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[BookingStatus] = mapped_column(
        default=BookingStatus.pending_payment, nullable=False, index=True
    )
    amount_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)

    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(128), nullable=True)

    locale: Mapped[Locale] = mapped_column(default=Locale.ro, nullable=False)

    # revenue-share % snapshotted from the location at booking time
    revenue_share_pct_snapshot: Mapped[int] = mapped_column(nullable=False)

    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    traveler_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kept_overnight: Mapped[bool] = mapped_column(default=False, nullable=False)

    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_members.id"), nullable=True
    )
    checked_out_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_members.id"), nullable=True
    )


class BookingItem(Base, UUIDPKMixin):
    __tablename__ = "booking_items"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True
    )
    item_type: Mapped[ItemType] = mapped_column(nullable=False)
    qty: Mapped[int] = mapped_column(nullable=False)
    unit_price_snapshot: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)


class BookingQrToken(Base, UUIDPKMixin, TimestampMixin):
    """The QR encodes only https://app.haihui.ro/s/{raw_token}; server looks up by hash."""

    __tablename__ = "booking_qr_tokens"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class BagPhoto(Base, UUIDPKMixin):
    __tablename__ = "bag_photos"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True
    )
    r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    taken_by_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_members.id"), nullable=False
    )
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)
