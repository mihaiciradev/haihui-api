from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import Locale


class User(Base, UUIDPKMixin, TimestampMixin):
    """Self-registerable traveler account. Auth is passwordless (magic link)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[Locale] = mapped_column(default=Locale.ro, nullable=False)

    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    marketing_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Placeholder hook for future account-level discounts; unused in V1.
    discount_pct: Mapped[int] = mapped_column(default=0, nullable=False)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Only set when is_admin is True. Admins never use magic-link auth.
    admin_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    admin_totp_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
