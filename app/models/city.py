from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class City(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "cities"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name_ro: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Bucharest", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
