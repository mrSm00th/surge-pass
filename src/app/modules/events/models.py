from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base

if TYPE_CHECKING:
    from src.app.modules.organizers.models import OrganizerProfile
    from src.app.modules.tickets.models import TicketTier


class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    LIVE = "LIVE"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    organizer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizer_profiles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    venue_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    venue_address: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status"),
        default=EventStatus.DRAFT,
        nullable=False,
        index=True,
    )

    event_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    event_end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    sale_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    sale_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    max_tickets_per_user: Mapped[int] = mapped_column(
        Integer,
        default=4,
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

    organizer: Mapped[OrganizerProfile] = relationship(
        back_populates="events",
    )

    ticket_tiers: Mapped[list["TicketTier"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        CheckConstraint(
            "event_end_time > event_start_time",
            name="ck_event_end_after_start",
        ),
        CheckConstraint(
            "sale_start_at <= event_start_time",
            name="ck_sales_open_before_event_starts",
        ),
        CheckConstraint(
            "sale_end_at IS NULL OR sale_end_at <= event_start_time",
            name="ck_sales_close_by_event_start",
        ),
        CheckConstraint(
            "max_tickets_per_user > 0",
            name="ck_max_tickets_positive",
        ),
    )
