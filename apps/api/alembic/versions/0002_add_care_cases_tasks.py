"""Add care cases, agent tasks and isolated conversation storage."""

import sqlalchemy as sa
from alembic import op


revision = "0002_add_care_cases_tasks"
down_revision = "0001_create_doctors_tables"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    definitions = [
        ("agent_owners", [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("care_cases", [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("agent_owners.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("subject_label", sa.String(60), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("agent_tasks", [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("case_id", sa.Uuid(), sa.ForeignKey("care_cases.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("case_messages", [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("case_id", sa.Uuid(), sa.ForeignKey("care_cases.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("operation_id", sa.Uuid(), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("task_id", "operation_id", "role", name="uq_case_message_operation_role"),
        ]),
    ]
    for name, columns in definitions:
        if not sa.inspect(connection).has_table(name):
            op.create_table(name, *columns)


def downgrade():
    for name in ("case_messages", "agent_tasks", "care_cases", "agent_owners"):
        op.drop_table(name)
