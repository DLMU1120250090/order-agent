"""User L2 行为事件表：memory_user_event

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_user_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("order_no", sa.String(length=64), nullable=True),
        sa.Column("context", JSON(), nullable=True),
        sa.Column("result", JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_memory_user_event_user_created", "memory_user_event", ["user_id", "created_at"])
    op.create_index("idx_memory_user_event_type", "memory_user_event", ["event_type"])


def downgrade() -> None:
    op.drop_index("idx_memory_user_event_type", table_name="memory_user_event")
    op.drop_index("idx_memory_user_event_user_created", table_name="memory_user_event")
    op.drop_table("memory_user_event")
