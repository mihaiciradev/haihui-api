from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import AdminIdentity, DbSession, get_current_admin
from app.models.audit import Event
from app.schemas.event import EventOut

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


@router.get("", response_model=list[EventOut])
async def list_events(
    db: DbSession,
    admin: AdminIdentity = Depends(get_current_admin),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EventOut]:
    """The single append-only log every state change already writes to
    (bookings, staff/PIN/token changes, location creation, admin/staff/
    traveler logins) -- newest first.
    """
    result = await db.execute(select(Event).order_by(Event.created_at.desc()).limit(limit))
    return [
        EventOut(
            id=str(e.id),
            actor_type=e.actor_type.value,
            actor_id=str(e.actor_id) if e.actor_id else None,
            entity_type=e.entity_type,
            entity_id=str(e.entity_id),
            action=e.action,
            payload=e.payload,
            ip=e.ip,
            created_at=e.created_at.isoformat(),
        )
        for e in result.scalars().all()
    ]
