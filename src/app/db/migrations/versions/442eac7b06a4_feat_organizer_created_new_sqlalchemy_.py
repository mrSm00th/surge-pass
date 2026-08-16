"""feat(organizer): created new sqlalchemy type and enabled encryption at rest for sensitive organizer fields

Revision ID: 442eac7b06a4
Revises: a2a0a37d3631
Create Date: 2026-08-14 22:30:42.767634

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import src.app.db.db_types

# revision identifiers, used by Alembic.
revision: str = "442eac7b06a4"
down_revision: Union[str, Sequence[str], None] = "a2a0a37d3631"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # drop the regex CHECK constraint on pan_number before it becomes ciphertext
    op.drop_constraint("ck_pan_number_format", "organizer_profiles", type_="check")

    op.alter_column(
        "organizer_profiles",
        "pan_number",
        existing_type=sa.VARCHAR(length=10),
        type_=src.app.db.db_types.EncryptedString(),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "gst_number",
        existing_type=sa.VARCHAR(length=15),
        type_=src.app.db.db_types.EncryptedString(),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "bank_account_number",
        existing_type=sa.VARCHAR(length=35),
        type_=src.app.db.db_types.EncryptedString(),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "bank_ifsc",
        existing_type=sa.VARCHAR(length=11),
        type_=src.app.db.db_types.EncryptedString(),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "bank_beneficiary_name",
        existing_type=sa.VARCHAR(length=255),
        type_=src.app.db.db_types.EncryptedString(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "organizer_profiles",
        "bank_beneficiary_name",
        existing_type=src.app.db.db_types.EncryptedString(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "bank_ifsc",
        existing_type=src.app.db.db_types.EncryptedString(),
        type_=sa.VARCHAR(length=11),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "bank_account_number",
        existing_type=src.app.db.db_types.EncryptedString(),
        type_=sa.VARCHAR(length=35),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "gst_number",
        existing_type=src.app.db.db_types.EncryptedString(),
        type_=sa.VARCHAR(length=15),
        existing_nullable=True,
    )
    op.alter_column(
        "organizer_profiles",
        "pan_number",
        existing_type=src.app.db.db_types.EncryptedString(),
        type_=sa.VARCHAR(length=10),
        existing_nullable=True,
    )

    # re-add the CHECK constraint on downgrade so schema fully reverses
    op.create_check_constraint(
        "CONSTRAINT_NAME_HERE",
        "organizer_profiles",
        "pan_number ~ '^[A-Z]{5}[0-9]{4}[A-Z]$'",  # <-- put your actual regex back here
    )
