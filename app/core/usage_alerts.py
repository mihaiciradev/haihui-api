import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.core.email import send_email
from app.core.email_templates import render_email
from app.core.events import write_event
from app.core.usage import WARN_THRESHOLD_PCT, compute_r2_usage
from app.database import AsyncSessionLocal
from app.models.audit import Event
from app.models.enums import ActorType

logger = logging.getLogger("haihui.usage_alerts")


async def check_and_alert_usage() -> None:
    """Runs on a daily interval (see core/scheduler.py). Emails
    settings.email_reply_to when R2 storage or this month's upload count
    crosses WARN_THRESHOLD_PCT of the free-tier limit, at most once a day
    so a sustained overage doesn't spam the inbox on every run.
    """
    async with AsyncSessionLocal() as db:
        usage = await compute_r2_usage(db)
        if max(usage["storage_pct"], usage["class_a_pct"]) < WARN_THRESHOLD_PCT:
            return

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        already_sent = await db.execute(
            select(Event.id)
            .where(
                Event.entity_type == "usage_alert",
                Event.action == "usage_alert_sent",
                Event.created_at >= today_start,
            )
            .limit(1)
        )
        if already_sent.scalar_one_or_none() is not None:
            return

        settings = get_settings()
        to = settings.email_reply_to or "haihuistorage@proton.me"
        storage_gb = usage["storage_bytes"] / (1024**3)
        body_html = (
            "<p>Utilizarea spațiului de stocare R2 a atins "
            f"<strong>{usage['storage_pct']}%</strong> "
            f"din limita gratuită ({storage_gb:.2f} GB din 10 GB).</p>"
            f"<p>Operațiunile de scriere din luna {usage['month']} au atins "
            f"<strong>{usage['class_a_pct']}%</strong> din limita gratuită "
            f"({usage['uploads_this_month']} din {usage['class_a_limit_month']}).</p>"
            "<p>Detalii în panoul de utilizare din contul de admin.</p>"
        )
        html = render_email(
            preheader="Utilizare stocare aproape de limita gratuită",
            heading="Alertă utilizare stocare",
            body_html=body_html,
            locale="ro",
        )
        try:
            await send_email(
                db,
                to=to,
                subject="Alertă utilizare stocare R2 - HaiHui Storage",
                html=html,
                template="usage_alert",
            )
        except Exception:
            logger.exception("failed to send usage alert email")

        await write_event(
            db,
            actor_type=ActorType.system,
            actor_id=None,
            entity_type="usage_alert",
            entity_id=uuid.uuid4(),
            action="usage_alert_sent",
            payload=usage,
        )
        await db.commit()
