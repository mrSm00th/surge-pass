from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JoinQueueResponse(BaseSchema):
    ticket_id: str


class QueueStatusResponse(BaseSchema):
    admitted: bool
    sale_started: bool
    position: int | None = None
    total_waiting: int | None = None
    estimated_wait_seconds: int | None = None
    opens_in_seconds: int | None = None
    # sending access_token as an httponly cookie
