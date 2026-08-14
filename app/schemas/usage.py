from pydantic import BaseModel


class R2UsageOut(BaseModel):
    month: str
    storage_bytes: int
    storage_limit_bytes: int
    storage_pct: float
    uploads_this_month: int
    class_a_limit_month: int
    class_a_pct: float
    class_b_tracked: bool


class UsageOut(BaseModel):
    r2: R2UsageOut
