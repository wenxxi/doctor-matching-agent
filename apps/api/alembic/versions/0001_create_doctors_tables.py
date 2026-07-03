"""create doctors tables

Revision ID: 0001_create_doctors_tables
Revises:
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_create_doctors_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hospital", sa.Text(), nullable=False),
        sa.Column("campus", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("subspecialty", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("registration_url", sa.Text(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("raw_expertise", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "hospital", "department", "profile_url", name="uq_doctors_identity"),
    )
    op.create_index("ix_doctors_hospital", "doctors", ["hospital"])
    op.create_index("ix_doctors_campus", "doctors", ["campus"])
    op.create_index("ix_doctors_department", "doctors", ["department"])

    op.create_table(
        "doctor_expertise",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("canonical_keyword", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "keyword", name="uq_doctor_expertise_keyword"),
    )
    op.create_index("ix_doctor_expertise_keyword", "doctor_expertise", ["keyword"])
    op.create_index("ix_doctor_expertise_canonical_keyword", "doctor_expertise", ["canonical_keyword"])


def downgrade() -> None:
    op.drop_index("ix_doctor_expertise_canonical_keyword", table_name="doctor_expertise")
    op.drop_index("ix_doctor_expertise_keyword", table_name="doctor_expertise")
    op.drop_table("doctor_expertise")
    op.drop_index("ix_doctors_department", table_name="doctors")
    op.drop_index("ix_doctors_campus", table_name="doctors")
    op.drop_index("ix_doctors_hospital", table_name="doctors")
    op.drop_table("doctors")
