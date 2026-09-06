"""memory v2 model：user_profile.preferences_v2 + trip_summary.episode_json

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("preferences_v2", JSON(), nullable=True))
    op.add_column("trip_summary", sa.Column("episode_json", JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trip_summary", "episode_json")
    op.drop_column("user_profile", "preferences_v2")
