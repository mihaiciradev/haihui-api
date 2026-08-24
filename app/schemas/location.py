from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ItemType, LocationStatus


class ItemCapacity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_type: ItemType
    daily_capacity: int = Field(gt=0, le=1000)


class DayHours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int = Field(ge=0, le=6)  # 0=Mon .. 6=Sun
    open_time: time
    close_time: time


class LocationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    city_slug: str = Field(min_length=1, max_length=64)
    address: str = Field(min_length=1, max_length=500)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    description_ro: str | None = Field(default=None, max_length=4000)
    description_en: str | None = Field(default=None, max_length=4000)
    google_maps_url: str | None = Field(default=None, max_length=1000)
    google_review_url: str | None = Field(default=None, max_length=1000)
    revenue_share_pct: int = Field(default=40, ge=0, le=100)

    item_types: list[ItemCapacity] = Field(min_length=1)
    hours: list[DayHours] | None = Field(
        default=None,
        description="Weekly template. Omit for a default of 08:00-20:00 every day.",
    )

    owner_name: str = Field(min_length=1, max_length=255)
    owner_pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")

    @field_validator("item_types")
    @classmethod
    def _unique_item_types(cls, v: list[ItemCapacity]) -> list[ItemCapacity]:
        types = [i.item_type for i in v]
        if len(types) != len(set(types)):
            raise ValueError("item_types must not repeat the same item_type")
        return v

    @field_validator("hours")
    @classmethod
    def _unique_weekdays(cls, v: list[DayHours] | None) -> list[DayHours] | None:
        if v is None:
            return v
        days = [h.weekday for h in v]
        if len(days) != len(set(days)):
            raise ValueError("hours must not repeat the same weekday")
        return v


class LocationUpdateRequest(BaseModel):
    """A partial update -- any field omitted entirely is left unchanged.
    item_types and hours, when given, fully replace the existing set rather
    than merging (matches how they're supplied on create).
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    description_ro: str | None = Field(default=None, max_length=4000)
    description_en: str | None = Field(default=None, max_length=4000)
    google_maps_url: str | None = Field(default=None, max_length=1000)
    google_review_url: str | None = Field(default=None, max_length=1000)
    revenue_share_pct: int | None = Field(default=None, ge=0, le=100)
    status: LocationStatus | None = None
    item_types: list[ItemCapacity] | None = Field(default=None, min_length=1)
    hours: list[DayHours] | None = None

    @field_validator("item_types")
    @classmethod
    def _unique_item_types(cls, v: list[ItemCapacity] | None) -> list[ItemCapacity] | None:
        if v is None:
            return v
        types = [i.item_type for i in v]
        if len(types) != len(set(types)):
            raise ValueError("item_types must not repeat the same item_type")
        return v

    @field_validator("hours")
    @classmethod
    def _unique_weekdays(cls, v: list[DayHours] | None) -> list[DayHours] | None:
        if v is None:
            return v
        days = [h.weekday for h in v]
        if len(days) != len(set(days)):
            raise ValueError("hours must not repeat the same weekday")
        return v


class LocationCreateResponse(BaseModel):
    id: str
    slug: str
    utm_code: str
    location_login_token: str
    owner_staff_id: str


class LocationSummary(BaseModel):
    id: str
    name: str
    slug: str
    city_slug: str
    status: str
    created_at: str


class ItemCapacityOut(BaseModel):
    item_type: str
    daily_capacity: int


class DayHoursOut(BaseModel):
    weekday: int
    open_time: str
    close_time: str


class LocationProfileResponse(BaseModel):
    """The owner-facing profile/panel view of their own location."""

    id: str
    name: str
    slug: str
    city_slug: str
    address: str
    lat: float
    lng: float
    description_ro: str | None
    description_en: str | None
    photos: list[str]
    status: str
    revenue_share_pct: int
    utm_code: str
    google_maps_url: str | None
    google_review_url: str | None
    strike_count: int
    item_types: list[ItemCapacityOut]
    hours: list[DayHoursOut]
