from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base

if TYPE_CHECKING:
    from src.app.modules.events.models import Event


class TicketTier(Base):
    __tablename__ = "ticket_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "events.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    total_capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    sold_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    event: Mapped[Event] = relationship(
        back_populates="ticket_tiers",
    )

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "name",
            name="uq_event_ticket_tier_name",
        ),
        CheckConstraint(
            "total_capacity > 0",
            name="ck_ticket_tier_capacity_positive",
        ),
        CheckConstraint(
            "sold_count >= 0 AND sold_count <= total_capacity",
            name="ck_sold_count_within_capacity",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_ticket_tier_price_non_negative",
        ),
    )
