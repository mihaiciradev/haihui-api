from datetime import date, time

from pydantic import BaseModel, ConfigDict, model_validator


class OverrideCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    closed: bool = False
    open_time: time | None = None
    close_time: time | None = None

    @model_validator(mode="after")
    def _hours_only_when_open(self) -> "OverrideCreateRequest":
        if self.closed and (self.open_time is not None or self.close_time is not None):
            raise ValueError("open_time/close_time cannot be set when closed is true")
        if (self.open_time is None) != (self.close_time is None):
            raise ValueError("open_time and close_time must be given together")
        if self.open_time is not None and self.close_time is not None:
            if self.open_time >= self.close_time:
                raise ValueError("open_time must be before close_time")
        return self


class OverrideOut(BaseModel):
    date: str
    closed: bool
    open_time: str | None
    close_time: str | None
    created_by: str
