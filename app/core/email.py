"""Thin Resend wrapper. Every send is recorded in email_log (§5.8).

In local/staging without a configured RESEND_API_KEY, sends are logged
instead of dispatched, so the flow is testable without real email delivery.
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.email_log import EmailLog
from app.models.enums import EmailStatus

logger = logging.getLogger("haihui.email")

RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(
    db: AsyncSession,
    *,
    to: str,
    subject: str,
    html: str,
    template: str,
    related_booking_id=None,
    related_ticket_id=None,
) -> EmailLog:
    settings = get_settings()
    log = EmailLog(
        to=to,
        template=template,
        status=EmailStatus.queued,
        related_booking_id=related_booking_id,
        related_ticket_id=related_ticket_id,
    )
    db.add(log)
    await db.flush()

    if not settings.resend_api_key:
        logger.info("email(dev-noop) to=%s template=%s subject=%s", to, template, subject)
        log.status = EmailStatus.sent
        return log

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
        )
    if resp.status_code >= 400:
        log.status = EmailStatus.failed
        logger.error("resend send failed to=%s status=%s body=%s", to, resp.status_code, resp.text)
    else:
        log.status = EmailStatus.sent
        log.provider_message_id = resp.json().get("id")
    return log
