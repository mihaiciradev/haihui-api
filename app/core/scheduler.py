from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.usage_alerts import check_and_alert_usage

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone=UTC)
    _scheduler.add_job(
        check_and_alert_usage,
        "interval",
        hours=24,
        next_run_time=datetime.now(UTC),
        id="usage_alerts",
    )
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
