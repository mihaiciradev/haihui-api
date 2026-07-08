import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ActorType


class Event(Base, UUIDPKMixin, TimestampMixin):
    """Append-only audit log. Every state change in the system writes here.

    This single table is the user-activity log, the dispute evidence trail,
    and the source for the weekly photo-enforcement audit query.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_entity", "entity_type", "entity_id"),
        Index("ix_events_created_at", "created_at"),
    )

    actor_type: Mapped[ActorType] = mapped_column(nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
