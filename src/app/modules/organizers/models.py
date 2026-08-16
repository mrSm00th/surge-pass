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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.db_types import EncryptedString

if TYPE_CHECKING:
    from src.app.modules.events.models import Event
    from src.app.modules.users.models import User


class KYCStatus(str, enum.Enum):
    PENDING = "PENDING"  # kyc not submitted yet by the organizer
    IN_REVIEW = "IN_REVIEW"
    ACTION_REQUIRED = "ACTION_REQUIRED"  # Razorpay needs more info/docs
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


#  these are the enums returned by razorpay linked_account creation
class RazorpayAccountStatus(str, enum.Enum):
    CREATED = "created"
    SUSPENDED = "suspended"


#  response status for product configuration request
class KYCProviderStatus(str, enum.Enum):
    REQUESTED = "requested"
    UNDER_REVIEW = "under_review"
    NEEDS_CLARIFICATION = "needs_clarification"
    ACTIVATED = "activated"
    SUSPENDED = "suspended"


class OrganizerBusinessType(str, enum.Enum):
    INDIVIDUAL = "individual"
    PROPRIETORSHIP = "proprietorship"
    PARTNERSHIP = "partnership"
    PRIVATE_LIMITED = "private_limited"
    PUBLIC_LIMITED = "public_limited"
    LLP = "llp"
    TRUST = "trust"
    SOCIETY = "society"
    NGO = "ngo"
    NOT_YET_REGISTERED = "not_yet_registered"


class OrganizerProfile(Base):
    __tablename__ = "organizer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    kyc_status: Mapped[KYCStatus] = mapped_column(
        Enum(
            KYCStatus, name="kyc_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=KYCStatus.PENDING,
        nullable=False,
        index=True,
    )

    razorpay_account_status: Mapped[RazorpayAccountStatus | None] = mapped_column(
        Enum(
            RazorpayAccountStatus,
            name="razorpay_account_status",
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )

    kyc_provider_status: Mapped[KYCProviderStatus | None] = mapped_column(
        Enum(
            KYCProviderStatus,
            name="kyc_provider_status",
            native_enum=False,
            length=30,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )

    # using a different reference id for rzorpay
    kyc_requirements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    razorpay_reference_code: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )

    razorpay_account_id: Mapped[str | None] = mapped_column(
        String(30), unique=True, index=True, nullable=True
    )

    razorpay_stakeholder_id: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    razorpay_product_id: Mapped[str | None] = mapped_column(
        String(30),
        unique=True,
        nullable=True,
    )

    legal_business_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    business_type: Mapped[OrganizerBusinessType | None] = mapped_column(
        Enum(
            OrganizerBusinessType,
            name="organizer_business_type",
            native_enum=False,
            length=30,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )

    # storing encrypted
    pan_number: Mapped[str | None] = mapped_column(
        EncryptedString,
        nullable=True,
    )

    # storing encrypted
    gst_number: Mapped[str | None] = mapped_column(
        EncryptedString,
        nullable=True,
    )

    contact_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    contact_phone: Mapped[str | None] = mapped_column(
        String(15),
        nullable=True,
    )

    # storing encrypted
    bank_account_number: Mapped[str | None] = mapped_column(
        EncryptedString,
        nullable=True,
    )

    # storing encrypted
    bank_ifsc: Mapped[str | None] = mapped_column(
        EncryptedString,
        nullable=True,
    )

    # storing encrypted
    bank_beneficiary_name: Mapped[str | None] = mapped_column(
        EncryptedString,
        nullable=True,
    )

    kyc_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    kyc_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    kyc_provider_status_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    razorpay_account_status_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    business_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    total_events_hosted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    hold_period_days: Mapped[int] = mapped_column(
        Integer,
        default=7,
        nullable=False,
    )

    risk_flags: Mapped[list[str] | None] = mapped_column(
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

    # relationships

    user: Mapped["User"] = relationship(back_populates="organizer_profile")

    events: Mapped[list["Event"]] = relationship(back_populates="organizer")

    __table_args__ = (
        CheckConstraint(
            "kyc_status != 'VERIFIED' OR ("
            "razorpay_account_id IS NOT NULL AND "
            "razorpay_stakeholder_id IS NOT NULL AND "
            "razorpay_product_id IS NOT NULL AND "
            "legal_business_name IS NOT NULL AND "
            "bank_account_number IS NOT NULL AND "
            "kyc_provider_status = 'activated'"
            ")",
            name="ck_verified_organizer_has_payout_details",
        ),
        CheckConstraint(
            "(kyc_provider_status IS NOT NULL) OR (kyc_status = 'PENDING')",
            name="ck_no_provider_status_before_pending",
        ),
        CheckConstraint(
            "(kyc_provider_status != 'activated') OR (kyc_status = 'VERIFIED')",
            name="ck_activated_provider_status_implies_verified",
        ),
    )
