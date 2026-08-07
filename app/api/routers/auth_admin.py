import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import AdminIdentity, DbSession, get_current_admin
from app.config import get_settings
from app.core.events import write_event
from app.core.http import client_ip
from app.core.rate_limit import check_rate_limit
from app.core.security import verify_secret
from app.core.sessions import ADMIN_COOKIE, cookie_kwargs, issue_session, read_session
from app.core.totp import verify_totp
from app.models.enums import ActorType
from app.models.user import User
from app.schemas.auth import AdminLoginRequest, AdminTotpVerifyRequest

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
me_router = APIRouter(prefix="/admin", tags=["admin-auth"])

PENDING_2FA_COOKIE = "hh_admin_pending"
PENDING_2FA_TTL_SECONDS = 5 * 60


@router.post("/login")
async def admin_login(
    body: AdminLoginRequest, request: Request, response: Response, db: DbSession
) -> dict:
    check_rate_limit(f"admin-login:ip:{client_ip(request)}", max_attempts=10, window_seconds=900)
    check_rate_limit(f"admin-login:email:{body.email}", max_attempts=10, window_seconds=900)

    admin_result = await db.execute(
        select(User).where(User.email == body.email, User.is_admin.is_(True))
    )
    admin = admin_result.scalar_one_or_none()

    # Same generic error whether the email doesn't exist, the password is
    # wrong, or 2FA setup was never completed — no admin account can be used
    # without 2FA, so an unenrolled account is treated as unusable.
    if (
        admin is None
        or not admin.admin_password_hash
        or not verify_secret(body.password, admin.admin_password_hash)
        or admin.admin_totp_confirmed_at is None
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    pending_token = issue_session("admin-pending", {"admin_user_id": str(admin.id)})
    response.set_cookie(
        PENDING_2FA_COOKIE, pending_token, **cookie_kwargs(max_age_seconds=PENDING_2FA_TTL_SECONDS)
    )
    return {"status": "totp_required"}


@router.post("/totp/verify")
async def admin_totp_verify(
    body: AdminTotpVerifyRequest,
    request: Request,
    response: Response,
    db: DbSession,
    hh_admin_pending: str | None = Cookie(default=None, alias=PENDING_2FA_COOKIE),
) -> dict:
    check_rate_limit(f"admin-totp:ip:{client_ip(request)}", max_attempts=10, window_seconds=900)

    if not hh_admin_pending:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login again")
    data = read_session("admin-pending", hh_admin_pending, PENDING_2FA_TTL_SECONDS)
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login again")

    admin_id = uuid.UUID(data["admin_user_id"])
    admin_result = await db.execute(
        select(User).where(User.id == admin_id, User.is_admin.is_(True))
    )
    admin = admin_result.scalar_one_or_none()
    if admin is None or not admin.admin_totp_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login again")

    settings = get_settings()
    if admin.admin_totp_locked_until is not None and admin.admin_totp_locked_until > datetime.now(
        UTC
    ):
        raise HTTPException(status.HTTP_423_LOCKED, "Too many attempts, try again later")

    if not verify_totp(admin.admin_totp_secret, body.code):
        admin.admin_failed_totp_attempts += 1
        if admin.admin_failed_totp_attempts >= settings.pin_max_attempts:
            admin.admin_totp_locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.pin_lockout_minutes
            )
        await write_event(
            db,
            actor_type=ActorType.system,
            actor_id=None,
            entity_type="user",
            entity_id=admin.id,
            action="admin_totp_failed",
            ip=client_ip(request),
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")

    admin.admin_failed_totp_attempts = 0
    admin.admin_totp_locked_until = None

    session_token = issue_session("admin", {"admin_user_id": str(admin.id), "totp_verified": True})
    response.set_cookie(
        ADMIN_COOKIE,
        session_token,
        **cookie_kwargs(max_age_seconds=settings.admin_session_ttl_hours * 3600),
    )
    response.delete_cookie(PENDING_2FA_COOKIE, path="/")

    await write_event(
        db,
        actor_type=ActorType.admin,
        actor_id=admin.id,
        entity_type="user",
        entity_id=admin.id,
        action="admin_login",
        ip=client_ip(request),
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/logout")
async def admin_logout(response: Response) -> dict:
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"status": "ok"}


@me_router.get("/me")
async def get_me(
    db: DbSession, identity: AdminIdentity = Depends(get_current_admin)  # noqa: B008
) -> dict:
    result = await db.execute(
        select(User).where(User.id == identity.admin_user_id, User.is_admin.is_(True))
    )
    admin = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return {"admin_user_id": str(admin.id), "email": admin.email}
