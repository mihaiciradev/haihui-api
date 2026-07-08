from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class MagicLinkToken(Base, UUIDPKMixin, TimestampMixin):
    """Single-use, 15-minute traveler login link. §8: no passwords to leak."""

    __tablename__ = "magic_link_tokens"

    email: Mapped[str] = mapped_column(CITEXT, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
