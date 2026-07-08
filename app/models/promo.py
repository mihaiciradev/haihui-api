import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class PromoCode(Base, UUIDPKMixin, TimestampMixin):
    """Used for the 25 RON host-closed credit and future promo/discount codes."""

    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    amount_ron: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    pct: Mapped[int | None] = mapped_column(nullable=True)
    single_use: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    issued_to_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_on_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
