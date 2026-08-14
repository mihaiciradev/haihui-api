from fastapi import APIRouter, Depends

from app.api.deps import AdminIdentity, DbSession, get_current_admin
from app.core.usage import compute_r2_usage
from app.schemas.usage import R2UsageOut, UsageOut

router = APIRouter(prefix="/admin/usage", tags=["admin-usage"])


@router.get("", response_model=UsageOut)
async def get_usage(
    db: DbSession, admin: AdminIdentity = Depends(get_current_admin)  # noqa: B008
) -> UsageOut:
    r2 = await compute_r2_usage(db)
    return UsageOut(r2=R2UsageOut(**r2))
