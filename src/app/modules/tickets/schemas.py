import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CreateTicketTier(BaseSchema):
    name: str
    description: str | None = None
    total_capacity: Annotated[int, Field(ge=0)]
    price: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class TicketTierOut(BaseSchema):
    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    description: str | None
    total_capacity: int
    price: Decimal
    created_at: datetime
