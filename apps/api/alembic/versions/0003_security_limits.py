"""Durable admission counters, leases and paginated history index."""
from alembic import op
from app.services.security import SecurityCounter, SecurityLease
from app.agent_models import CaseMessage

revision = "0003_security_limits"
down_revision = "0002_add_care_cases_tasks"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    SecurityCounter.__table__.create(bind, checkfirst=True)
    SecurityLease.__table__.create(bind, checkfirst=True)
    for index in CaseMessage.__table__.indexes:
        index.create(bind, checkfirst=True)


def downgrade():
    op.drop_index("ix_case_messages_page", table_name="case_messages")
    op.drop_table("security_leases")
    op.drop_table("security_counters")
