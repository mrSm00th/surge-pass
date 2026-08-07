from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base

if TYPE_CHECKING:
    from src.app.modules.events.models import Event
    from src.app.modules.users.models import User


class KYCStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class OrganizerProfile(Base):
    __tablename__ = "organizer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        unique=True,
        nullable=False,
        # index=True, unique=True auto indexes this
    )

    kyc_status: Mapped[KYCStatus] = mapped_column(
        Enum(KYCStatus, name="kyc_status"),
        default=KYCStatus.PENDING,
    )

    payout_account_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
    )

    business_name: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
    )

    total_events_hosted: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    hold_period_days: Mapped[int] = mapped_column(
        Integer,
        default=7,
    )

    risk_flags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=True,
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

    user: Mapped[User] = relationship(
        back_populates="organizer_profile",
    )

    events: Mapped[list["Event"]] = relationship(
        back_populates="organizer",
    )

    __table_args__ = (
        CheckConstraint(
            "kyc_status != 'VERIFIED' OR "
            "(payout_account_id IS NOT NULL AND business_name IS NOT NULL)",
            name="ck_verified_organizer_has_payout_details",
        ),
    )
