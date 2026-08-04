"""feat(user): added otp reason enum

Revision ID: 9dff4578abab
Revises: 4f21e4535a10
Create Date: 2026-07-31 13:52:50.355237

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9dff4578abab"
down_revision: Union[str, Sequence[str], None] = "4f21e4535a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    otp_purpose_enum = sa.Enum(
        "EMAIL_VERIFICATION", "PASSWORD_RESET", name="otppurpose"
    )
    otp_purpose_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "otp_verifications",
        sa.Column("purpose", otp_purpose_enum, nullable=False),
    )
    op.drop_index(
        "idx_one_valid_otp_per_user",
        table_name="otp_verifications",
        postgresql_where=sa.text("is_used = false"),
    )
    op.create_index(
        "idx_one_valid_otp_per_user",
        "otp_verifications",
        ["user_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("is_used = false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_one_valid_otp_per_user",
        table_name="otp_verifications",
        postgresql_where=sa.text("is_used = false"),
    )
    op.create_index(
        "idx_one_valid_otp_per_user",
        "otp_verifications",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_used = false"),
    )
    op.drop_column("otp_verifications", "purpose")

    sa.Enum(name="otppurpose").drop(op.get_bind(), checkfirst=True)
