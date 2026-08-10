from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import DbSession, TravelerIdentity, get_current_traveler
from app.config import get_settings
from app.core.email import send_email
from app.core.email_templates import render_email
from app.core.events import write_event
from app.core.http import client_ip
from app.core.rate_limit import check_rate_limit
from app.core.security import generate_opaque_token, hash_opaque_token
from app.core.sessions import TRAVELER_COOKIE, cookie_kwargs, issue_session
from app.models.enums import ActorType
from app.models.magic_link import MagicLinkToken
from app.models.user import User
from app.schemas.auth import MagicLinkRequest, MagicLinkVerify

router = APIRouter(prefix="/auth", tags=["traveler-auth"])


@router.post("/magic-link")
async def request_magic_link(body: MagicLinkRequest, request: Request, db: DbSession) -> dict:
    check_rate_limit(f"magic-link:ip:{client_ip(request)}", max_attempts=10, window_seconds=3600)
    check_rate_limit(f"magic-link:email:{body.email}", max_attempts=5, window_seconds=3600)

    settings = get_settings()
    raw, hashed = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.magic_link_ttl_minutes)
    db.add(MagicLinkToken(email=body.email, token_hash=hashed, expires_at=expires_at))

    link = f"{settings.public_base_url}/auth/verify?token={raw}"
    body_html = (
        "<p>Salut!</p>"
        "<p>Apasă butonul de mai jos pentru a te conecta la contul tău HaiHui – Storage. "
        f"Linkul este valabil <strong>{settings.magic_link_ttl_minutes} minute</strong> "
        "și poate fi folosit o singură dată.</p>"
        "<p style=\"font-size:13px; color:#5c5e66;\">Dacă nu ai cerut acest email, "
        "îl poți ignora în siguranță — contul tău rămâne neschimbat.</p>"
    )
    html = render_email(
        preheader="Linkul tău de conectare HaiHui – Storage",
        heading="Conectează-te la contul tău",
        body_html=body_html,
        locale="ro",
        cta_label="Conectează-te",
        cta_url=link,
    )
    await send_email(
        db,
        to=body.email,
        subject="Linkul tău de conectare — HaiHui Storage",
        html=html,
        template="magic_link",
    )
    await db.commit()
    # Always return 200 regardless of whether the email exists as a user yet —
    # do not leak account existence.
    return {"status": "sent"}


@router.post("/magic-link/verify")
async def verify_magic_link(
    body: MagicLinkVerify, request: Request, response: Response, db: DbSession
) -> dict:
    check_rate_limit(
        f"magic-link-verify:ip:{client_ip(request)}", max_attempts=20, window_seconds=3600
    )

    token_hash = hash_opaque_token(body.token)
    link_result = await db.execute(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
    )
    link = link_result.scalar_one_or_none()

    now = datetime.now(UTC)
    if not link or link.consumed_at is not None or link.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")

    link.consumed_at = now

    user_result = await db.execute(select(User).where(User.email == link.email))
    user = user_result.scalar_one_or_none()
    if user is None:
        user = User(email=link.email)
        db.add(user)
        await db.flush()

    await write_event(
        db,
        actor_type=ActorType.user,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="magic_link_login",
        ip=client_ip(request),
    )

    settings = get_settings()
    session_token = issue_session("traveler", {"user_id": str(user.id)})
    response.set_cookie(
        TRAVELER_COOKIE,
        session_token,
        **cookie_kwargs(max_age_seconds=settings.traveler_session_ttl_hours * 3600),
    )
    await db.commit()
    return {"status": "ok", "user_id": str(user.id)}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(TRAVELER_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
async def get_me(
    db: DbSession, identity: TravelerIdentity = Depends(get_current_traveler)  # noqa: B008
) -> dict:
    result = await db.execute(select(User).where(User.id == identity.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return {"user_id": str(user.id), "email": user.email, "locale": user.locale.value}
