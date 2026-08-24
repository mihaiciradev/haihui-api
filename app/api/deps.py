import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.sessions import ADMIN_COOKIE, STAFF_COOKIE, TRAVELER_COOKIE, read_session
from app.database import get_db
from app.models.staff import StaffMember

DbSession = Annotated[AsyncSession, Depends(get_db)]


@dataclass
class TravelerIdentity:
    user_id: uuid.UUID


@dataclass
class StaffIdentity:
    staff_id: uuid.UUID
    location_id: uuid.UUID
    role: str


@dataclass
class AdminIdentity:
    admin_user_id: uuid.UUID


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_traveler(
    hh_traveler_session: str | None = Cookie(default=None, alias=TRAVELER_COOKIE),
) -> TravelerIdentity:
    settings = get_settings()
    if not hh_traveler_session:
        raise _unauthorized("Not logged in")
    data = read_session("traveler", hh_traveler_session, settings.traveler_session_ttl_hours * 3600)
    if not data:
        raise _unauthorized("Session expired")
    return TravelerIdentity(user_id=uuid.UUID(data["user_id"]))


async def get_current_staff(
    db: DbSession,
    hh_staff_session: str | None = Cookie(default=None, alias=STAFF_COOKIE),
) -> StaffIdentity:
    settings = get_settings()
    if not hh_staff_session:
        raise _unauthorized("Not logged in")
    data = read_session("staff", hh_staff_session, settings.staff_session_ttl_hours * 3600)
    if not data:
        raise _unauthorized("Session expired")

    # Checked live (not just decoded from the cookie) so an admin deactivating
    # a staff member revokes access immediately, not only after the session
    # cookie's TTL naturally expires (up to staff_session_ttl_hours later).
    staff_id = uuid.UUID(data["staff_id"])
    result = await db.execute(select(StaffMember.is_active).where(StaffMember.id == staff_id))
    is_active = result.scalar_one_or_none()
    if is_active is not True:
        raise _unauthorized("Session expired")

    return StaffIdentity(
        staff_id=staff_id,
        location_id=uuid.UUID(data["location_id"]),
        role=data["role"],
    )


def require_owner(identity: StaffIdentity = Depends(get_current_staff)) -> StaffIdentity:  # noqa: B008
    if identity.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner role required")
    return identity


def location_scoped(location_id: uuid.UUID, identity: StaffIdentity) -> None:
    """Every partner endpoint must call this: staff can only ever touch their
    own location's data (§8 authorization requirement).
    """
    if identity.location_id != location_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your location")


async def get_current_admin(
    hh_admin_session: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> AdminIdentity:
    settings = get_settings()
    if not hh_admin_session:
        raise _unauthorized("Not logged in")
    data = read_session("admin", hh_admin_session, settings.admin_session_ttl_hours * 3600)
    if not data or not data.get("totp_verified"):
        raise _unauthorized("Session expired")
    return AdminIdentity(admin_user_id=uuid.UUID(data["admin_user_id"]))
