import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import Event
from app.models.enums import ActorType


async def write_event(
    db: AsyncSession,
    *,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    payload: dict | None = None,
    ip: str | None = None,
) -> Event:
    """Append an audit event. Does not commit — caller controls the transaction
    boundary so an event can be written atomically alongside the state change
    it records.
    """
    event = Event(
        actor_type=actor_type,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        payload=payload or {},
        ip=ip,
    )
    db.add(event)
    await db.flush()
    return event
