from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import DbSession, StaffIdentity, get_current_staff
from app.config import get_settings
from app.core.events import write_event
from app.core.http import client_ip
from app.core.rate_limit import check_rate_limit
from app.core.security import hash_opaque_token, verify_secret
from app.core.sessions import STAFF_COOKIE, cookie_kwargs, issue_session
from app.models.enums import ActorType
from app.models.staff import LocationLoginToken, StaffMember
from app.schemas.auth import StaffLoginRequest, StaffRosterRequest

router = APIRouter(prefix="/partner/auth", tags=["partner-auth"])
me_router = APIRouter(prefix="/partner", tags=["partner-auth"])


def _locked(entity) -> bool:
    return entity.locked_until is not None and entity.locked_until > datetime.now(UTC)


async def _resolve_location_token(db: DbSession, raw_token: str) -> LocationLoginToken:
    token_hash = hash_opaque_token(raw_token)
    result = await db.execute(
        select(LocationLoginToken).where(LocationLoginToken.token_hash == token_hash)
    )
    login_token = result.scalar_one_or_none()
    if not login_token or login_token.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid login QR")
    return login_token


@router.post("/roster")
async def staff_roster(body: StaffRosterRequest, request: Request, db: DbSession) -> dict:
    """After scanning the location QR, the PWA shows this list so staff can
    pick their name before entering a PIN — needed so a failed PIN can be
    attributed to one person (§3.2 per-staff lockout).
    """
    check_rate_limit(f"staff-roster:ip:{client_ip(request)}", max_attempts=30, window_seconds=900)
    login_token = await _resolve_location_token(db, body.location_token)
    if _locked(login_token):
        raise HTTPException(status.HTTP_423_LOCKED, "Location locked out, try again later")

    result = await db.execute(
        select(StaffMember).where(
            StaffMember.location_id == login_token.location_id,
            StaffMember.is_active.is_(True),
        )
    )
    staff = result.scalars().all()
    return {"staff": [{"id": str(s.id), "name": s.name} for s in staff]}


@router.post("/login")
async def staff_login(
    body: StaffLoginRequest, request: Request, response: Response, db: DbSession
) -> dict:
    settings = get_settings()
    check_rate_limit(f"staff-login:ip:{client_ip(request)}", max_attempts=20, window_seconds=900)

    login_token = await _resolve_location_token(db, body.location_token)
    if _locked(login_token):
        raise HTTPException(status.HTTP_423_LOCKED, "Location locked out, try again later")

    result = await db.execute(
        select(StaffMember).where(
            StaffMember.id == body.staff_id,
            StaffMember.location_id == login_token.location_id,
            StaffMember.is_active.is_(True),
        )
    )
    staff = result.scalar_one_or_none()
    if staff is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid PIN")

    if _locked(staff):
        raise HTTPException(status.HTTP_423_LOCKED, "Too many attempts, try again later")

    if not verify_secret(body.pin, staff.pin_hash):
        staff.failed_pin_attempts += 1
        login_token.failed_pin_attempts += 1
        if staff.failed_pin_attempts >= settings.pin_max_attempts:
            staff.locked_until = datetime.now(UTC) + timedelta(minutes=settings.pin_lockout_minutes)
        if login_token.failed_pin_attempts >= settings.pin_max_attempts:
            login_token.locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.pin_lockout_minutes
            )
        await write_event(
            db,
            actor_type=ActorType.system,
            actor_id=None,
            entity_type="staff_member",
            entity_id=staff.id,
            action="pin_login_failed",
            ip=client_ip(request),
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid PIN")

    staff.failed_pin_attempts = 0
    staff.locked_until = None
    staff.last_login_at = datetime.now(UTC)
    login_token.failed_pin_attempts = 0
    login_token.locked_until = None

    await write_event(
        db,
        actor_type=ActorType.staff,
        actor_id=staff.id,
        entity_type="staff_member",
        entity_id=staff.id,
        action="login",
        ip=client_ip(request),
    )

    session_token = issue_session(
        "staff",
        {
            "staff_id": str(staff.id),
            "location_id": str(staff.location_id),
            "role": staff.role.value,
        },
    )
    response.set_cookie(
        STAFF_COOKIE,
        session_token,
        **cookie_kwargs(max_age_seconds=settings.staff_session_ttl_hours * 3600),
    )
    await db.commit()
    return {"status": "ok", "staff_id": str(staff.id), "role": staff.role.value}


@router.post("/logout")
async def staff_logout(response: Response) -> dict:
    response.delete_cookie(STAFF_COOKIE, path="/")
    return {"status": "ok"}


@me_router.get("/me")
async def get_me(
    db: DbSession, identity: StaffIdentity = Depends(get_current_staff)  # noqa: B008
) -> dict:
    result = await db.execute(select(StaffMember).where(StaffMember.id == identity.staff_id))
    staff = result.scalar_one_or_none()
    if staff is None or not staff.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return {
        "staff_id": str(staff.id),
        "location_id": str(staff.location_id),
        "role": staff.role.value,
        "name": staff.name,
    }
