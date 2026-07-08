import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MagicLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class MagicLinkVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=512)


class StaffRosterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_token: str = Field(min_length=16, max_length=512)


class StaffLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_token: str = Field(min_length=16, max_length=512)
    staff_id: uuid.UUID
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class AdminTotpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
