import uuid
from datetime import date, time

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ItemType, LocationStatus


class Location(Base, UUIDPKMixin, TimestampMixin):
    """A partner host business."""

    __tablename__ = "locations"

    city_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    lat: Mapped[float] = mapped_column(nullable=False)
    lng: Mapped[float] = mapped_column(nullable=False)
    description_ro: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    description_en: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    photos: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    status: Mapped[LocationStatus] = mapped_column(
        default=LocationStatus.active, nullable=False, index=True
    )
    strike_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    revenue_share_pct: Mapped[int] = mapped_column(SmallInteger, default=40, nullable=False)
    utm_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    google_maps_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    google_review_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_admin: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class LocationHours(Base, UUIDPKMixin):
    """Weekly opening-hours template. Admin-set only."""

    __tablename__ = "location_hours"
    __table_args__ = (UniqueConstraint("location_id", "weekday", name="uq_location_hours_day"),)

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False, index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Mon .. 6=Sun
    open_time: Mapped[time] = mapped_column(Time, nullable=False)
    close_time: Mapped[time] = mapped_column(Time, nullable=False)


class LocationOverride(Base, UUIDPKMixin):
    """One row per date; overrides the weekly template. Owner or admin can create."""

    __tablename__ = "location_overrides"
    __table_args__ = (UniqueConstraint("location_id", "date", name="uq_location_override_date"),)

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)  # "owner" | "admin"


class LocationItemType(Base, UUIDPKMixin):
    """Which item types a host accepts and daily capacity. Admin-set only."""

    __tablename__ = "location_item_types"
    __table_args__ = (UniqueConstraint("location_id", "item_type", name="uq_location_item_type"),)

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False, index=True
    )
    item_type: Mapped[ItemType] = mapped_column(nullable=False)
    daily_capacity: Mapped[int] = mapped_column(nullable=False)


class PriceListEntry(Base, UUIDPKMixin, TimestampMixin):
    """Platform-wide, admin-managed. Append-only so booking snapshots stay accurate."""

    __tablename__ = "price_list"

    item_type: Mapped[ItemType] = mapped_column(nullable=False, index=True)
    price_ron: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
