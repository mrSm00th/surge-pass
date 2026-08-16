"""feat(organizer): add new columns to support organizer kyc verification

Revision ID: ef6cfdcf1ade
Revises: 618486e2583b
Create Date: 2026-08-10 23:40:45.822563

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ef6cfdcf1ade"
down_revision: Union[str, Sequence[str], None] = "618486e2583b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.alter_column(
        "organizer_profiles",
        "payout_account_id",
        new_column_name="razorpay_account_id",
    )

    op.add_column(
        "organizer_profiles",
        sa.Column(
            "kyc_provider_status",
            sa.Enum(
                "created",
                "under_review",
                "needs_clarification",
                "activated",
                "suspended",
                "rejected",
                name="kyc_provider_status",
                native_enum=False,
                length=50,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "organizer_profiles",
        sa.Column(
            "kyc_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "organizer_profiles",
        sa.Column("kyc_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organizer_profiles",
        sa.Column("kyc_activated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("organizer_profiles", "kyc_activated_at")
    op.drop_column("organizer_profiles", "kyc_submitted_at")
    op.drop_column("organizer_profiles", "kyc_requirements")
    op.drop_column("organizer_profiles", "kyc_provider_status")

    op.alter_column(
        "organizer_profiles",
        "razorpay_account_id",
        new_column_name="payout_account_id",
    )
