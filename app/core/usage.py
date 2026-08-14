"""R2 usage is self-tracked from our own upload records rather than
Cloudflare's account-level analytics API, since the R2 API token we hold is
scoped to the bucket itself (S3-compatible credentials), not the broader
account-level Analytics permission a Cloudflare API token would need. This
is accurate for storage bytes and write count because our API is the only
writer to the bucket -- it is not accurate for reads (class B operations),
since those happen directly against R2 via presigned URLs and never touch
our server, so they cannot be counted this way.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BagPhoto

R2_STORAGE_LIMIT_BYTES = 10 * 1024**3
R2_CLASS_A_LIMIT_MONTH = 1_000_000
WARN_THRESHOLD_PCT = 80.0


async def compute_r2_usage(db: AsyncSession) -> dict:
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    storage_result = await db.execute(select(func.coalesce(func.sum(BagPhoto.size_bytes), 0)))
    storage_bytes = int(storage_result.scalar_one())

    uploads_result = await db.execute(
        select(func.count(BagPhoto.id)).where(BagPhoto.taken_at >= month_start)
    )
    uploads_this_month = int(uploads_result.scalar_one())

    return {
        "month": month_start.strftime("%Y-%m"),
        "storage_bytes": storage_bytes,
        "storage_limit_bytes": R2_STORAGE_LIMIT_BYTES,
        "storage_pct": round(storage_bytes / R2_STORAGE_LIMIT_BYTES * 100, 1),
        "uploads_this_month": uploads_this_month,
        "class_a_limit_month": R2_CLASS_A_LIMIT_MONTH,
        "class_a_pct": round(uploads_this_month / R2_CLASS_A_LIMIT_MONTH * 100, 1),
        "class_b_tracked": False,
    }
