import uuid
from datetime import date

from sqlalchemy import select

from app.api.deps import DbSession
from app.models.location import LocationOverride


async def is_location_open(db: DbSession, location_id: uuid.UUID, day: date) -> bool:
    """Openness for a given date is: no override, or an override that isn't
    marked closed (§5.6 -- override beats the weekly template, and every
    location always has all 7 weekdays populated in the weekly template).
    """
    result = await db.execute(
        select(LocationOverride).where(
            LocationOverride.location_id == location_id,
            LocationOverride.date == day,
        )
    )
    override = result.scalar_one_or_none()
    if override is not None and override.closed:
        return False
    return True
