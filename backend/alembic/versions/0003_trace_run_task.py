"""trace 跨请求链路关联：request_trace.run_id / task_id + 索引

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diet_request_trace", sa.Column("run_id", sa.String(length=64), nullable=True))
    op.add_column("diet_request_trace", sa.Column("task_id", sa.String(length=64), nullable=True))
    op.create_index("idx_request_trace_run_id", "diet_request_trace", ["run_id"])
    op.create_index("idx_request_trace_task_id", "diet_request_trace", ["task_id"])


def downgrade() -> None:
    op.drop_index("idx_request_trace_task_id", table_name="diet_request_trace")
    op.drop_index("idx_request_trace_run_id", table_name="diet_request_trace")
    op.drop_column("diet_request_trace", "task_id")
    op.drop_column("diet_request_trace", "run_id")
