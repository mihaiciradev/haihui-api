from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.capacity import MAX_STORAGE_SPAN_DAYS
from app.models.enums import ItemType, Locale


class BookingItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_type: ItemType
    qty: int = Field(gt=0, le=20)


class BookingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_slug: str = Field(min_length=1, max_length=255)
    storage_date: date
    pickup_date: date | None = Field(
        default=None, description="Defaults to storage_date for a same-day booking."
    )
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

    @model_validator(mode="after")
    def _resolve_and_validate_pickup_date(self) -> "BookingCreateRequest":
        if self.pickup_date is None:
            self.pickup_date = self.storage_date
        if self.pickup_date < self.storage_date:
            raise ValueError("pickup_date cannot be before storage_date")
        if (self.pickup_date - self.storage_date).days > MAX_STORAGE_SPAN_DAYS:
            raise ValueError(f"storage span cannot exceed {MAX_STORAGE_SPAN_DAYS + 1} days")
        return self


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
    pickup_date: str
    amount_total: float
    currency: str
    items: list[BookingItemOut]


class BookingDetail(BaseModel):
    code: str
    qr_url: str
    status: str
    storage_date: str
    pickup_date: str
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
    pickup_date: str
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
