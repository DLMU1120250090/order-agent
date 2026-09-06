"""feedback trace 归因：recommend_feedback.trace_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommend_feedback", sa.Column("trace_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("recommend_feedback", "trace_id")
