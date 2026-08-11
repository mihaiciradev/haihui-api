from pydantic import BaseModel


class PublicItemType(BaseModel):
    item_type: str
    price_ron: float
    daily_capacity: int


class PublicDayHours(BaseModel):
    weekday: int
    open_time: str
    close_time: str


class LocationDetail(BaseModel):
    id: str
    name: str
    slug: str
    city_slug: str
    city_name_ro: str
    city_name_en: str
    address: str
    lat: float
    lng: float
    description_ro: str | None
    description_en: str | None
    photos: list[str]
    status: str
    utm_code: str
    google_maps_url: str | None
    google_review_url: str | None
    item_types: list[PublicItemType]
    hours: list[PublicDayHours]


class LocationListItem(BaseModel):
    id: str
    name: str
    slug: str
    city_slug: str
    address: str
    lat: float
    lng: float
    photos: list[str]
    from_price_ron: float | None
