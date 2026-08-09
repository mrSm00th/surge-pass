import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, configDict, model_validator

from src.app.modules.events.models import EventStatus


class BaseSchema(BaseModel):
    model_config = configDict(
        from_attributes=True,
    )


class EventCreate(BaseSchema):
    title: Annotated[str, Field(max_length=255)]
    description: Annotated[str | None, Field(None, max_length=1000)]

    venue_name: Annotated[str, Field(max_length=255)]
    venue_address: Annotated[str | None, Field(None, max_length=255)]
    city: Annotated[str, Field(max_length=100)]

    event_start_time: Annotated[datetime, Field(description="Event start time")]
    event_end_time: Annotated[datetime, Field(description="Event end time")]

    sale_start_at: Annotated[datetime, Field(description="Ticket sale start time")]
    sale_end_at: Annotated[
        datetime | None, Field(None, description="Ticket sale end time")
    ]

    @model_validator(mode="after")
    def validate_date_ordering(self) -> "EventCreate":
        if self.event_start_time >= self.event_end_time:
            raise ValueError("event_start_time must be before event_end_time")

        if self.sale_start_at >= self.sale_end_at:
            raise ValueError("sale_start_at must be before sale_end_at")

        if self.sale_end_at > self.event_start_time:
            raise ValueError("ticket sales must end before the event starts")

        return self


class EventOut(BaseSchema):
    id: uuid.UUID
    organizer_id: uuid.UUID
    title: str
    description: str | None
    venue_name: str
    venue_address: str
    city: str
    status: EventStatus
    event_start_time: datetime
    event_end_time: datetime
    sale_start_at: datetime
    sale_end_at: datetime
    max_tickets_per_user: int
    created_at: datetime
    updated_at: datetime


class EventUpdate(BaseSchema):
    title: str | None = None
    description: str | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    city: str | None = None
    event_start_time: datetime | None = None
    event_end_time: datetime | None = None
    sale_start_at: datetime | None = None
    sale_end_at: datetime | None = None
    max_tickets_per_user: int | None = None
