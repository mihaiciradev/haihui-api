from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.city import City
from app.schemas.city import CityOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("", response_model=list[CityOut])
async def list_cities(db: DbSession) -> list[CityOut]:
    """Public, unauthenticated -- used by the admin location-creation form's
    city dropdown, and eventually the public site's city selector.
    """
    result = await db.execute(select(City).where(City.is_active.is_(True)).order_by(City.name_en))
    return [
        CityOut(slug=c.slug, name_ro=c.name_ro, name_en=c.name_en) for c in result.scalars().all()
    ]
