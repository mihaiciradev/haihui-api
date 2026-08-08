from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import StaffRole


class StaffCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")
    role: StaffRole = StaffRole.staff


class StaffCreateResponse(BaseModel):
    staff_id: str
    name: str
    role: str


class PinResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class TokenRotateResponse(BaseModel):
    location_login_token: str
