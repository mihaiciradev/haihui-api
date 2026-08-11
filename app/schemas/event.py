from pydantic import BaseModel


class EventOut(BaseModel):
    id: str
    actor_type: str
    actor_id: str | None
    entity_type: str
    entity_id: str
    action: str
    payload: dict
    ip: str | None
    created_at: str
