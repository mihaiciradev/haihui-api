from pydantic import BaseModel


class CityOut(BaseModel):
    slug: str
    name_ro: str
    name_en: str
