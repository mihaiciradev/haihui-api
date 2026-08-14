import uuid
from datetime import date as date_type

from sqlalchemy import select

from app.api.deps import DbSession
from app.models.location import LocationOverride
from app.schemas.location_override import OverrideCreateRequest, OverrideOut


def _to_out(o: LocationOverride) -> OverrideOut:
    return OverrideOut(
        date=o.date.isoformat(),
        closed=o.closed,
        open_time=o.open_time.isoformat() if o.open_time else None,
        close_time=o.close_time.isoformat() if o.close_time else None,
        created_by=o.created_by,
    )


async def upsert_override(
    db: DbSession, location_id: uuid.UUID, body: OverrideCreateRequest, *, created_by: str
) -> OverrideOut:
    """One row per (location, date) -- re-posting the same date updates it
    in place rather than erroring, so correcting a mistake doesn't require
    a separate delete-then-recreate round trip.
    """
    result = await db.execute(
        select(LocationOverride).where(
            LocationOverride.location_id == location_id, LocationOverride.date == body.date
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        override = LocationOverride(location_id=location_id, date=body.date)
        db.add(override)

    override.closed = body.closed
    override.open_time = body.open_time
    override.close_time = body.close_time
    override.created_by = created_by
    await db.flush()
    return _to_out(override)


async def list_overrides(
    db: DbSession, location_id: uuid.UUID, *, upcoming_only: bool = True
) -> list[OverrideOut]:
    query = select(LocationOverride).where(LocationOverride.location_id == location_id)
    if upcoming_only:
        query = query.where(LocationOverride.date >= date_type.today())
    query = query.order_by(LocationOverride.date)
    result = await db.execute(query)
    return [_to_out(o) for o in result.scalars().all()]


async def delete_override(db: DbSession, location_id: uuid.UUID, target_date: date_type) -> bool:
    result = await db.execute(
        select(LocationOverride).where(
            LocationOverride.location_id == location_id, LocationOverride.date == target_date
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        return False
    await db.delete(override)
    await db.flush()
    return True
