from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ItemType, Locale


class BookingItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_type: ItemType
    qty: int = Field(gt=0, le=20)


class BookingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_slug: str = Field(min_length=1, max_length=255)
    storage_date: date
    items: list[BookingItemRequest] = Field(min_length=1)
    guest_phone: str = Field(min_length=5, max_length=32)
    locale: Locale = Locale.ro

    source: str | None = Field(default=None, max_length=64)
    utm_source: str | None = Field(default=None, max_length=128)
    utm_medium: str | None = Field(default=None, max_length=128)
    utm_campaign: str | None = Field(default=None, max_length=128)

    @field_validator("items")
    @classmethod
    def _unique_item_types(cls, v: list[BookingItemRequest]) -> list[BookingItemRequest]:
        types = [i.item_type for i in v]
        if len(types) != len(set(types)):
            raise ValueError("items must not repeat the same item_type")
        return v


class BookingItemOut(BaseModel):
    item_type: str
    qty: int
    unit_price_snapshot: float


class BookingCreateResponse(BaseModel):
    code: str
    booking_token: str
    qr_url: str
    status: str
    storage_date: str
    amount_total: float
    currency: str
    items: list[BookingItemOut]


class BookingDetail(BaseModel):
    code: str
    qr_url: str
    status: str
    storage_date: str
    amount_total: float
    currency: str
    items: list[BookingItemOut]
    location_name: str
    location_address: str
    location_slug: str
    created_at: str


class PartnerBookingOut(BaseModel):
    id: str
    code: str
    status: str
    storage_date: str
    guest_email: str
    guest_phone: str
    amount_total: float
    currency: str
    items: list[BookingItemOut]
    created_at: str
    checked_in_at: str | None
    checked_out_at: str | None
    photo_count: int


class BagPhotoOut(BaseModel):
    id: str
    url: str
    taken_at: str
