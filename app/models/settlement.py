import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Settlement(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "settlements"

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False, index=True
    )
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # first day of month
    totals_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_report_r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
