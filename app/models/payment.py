import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import PaymentStatus, RefundReason


class Payment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True
    )
    stripe_checkout_session_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[PaymentStatus] = mapped_column(default=PaymentStatus.pending, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)


class Refund(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "refunds"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[RefundReason] = mapped_column(nullable=False)
    stripe_refund_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    initiated_by: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # system|admin:<id>|traveler
