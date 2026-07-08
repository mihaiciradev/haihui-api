import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import TicketAuthor, TicketStatus


class Ticket(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tickets"

    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        default=TicketStatus.open, nullable=False, index=True
    )
    reply_token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )


class TicketMessage(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "ticket_messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False, index=True
    )
    author: Mapped[TicketAuthor] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
