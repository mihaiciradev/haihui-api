import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EmailStatus


class EmailLog(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "email_log"

    to: Mapped[str] = mapped_column(CITEXT, nullable=False, index=True)
    template: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[EmailStatus] = mapped_column(default=EmailStatus.queued, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
    related_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=True
    )
