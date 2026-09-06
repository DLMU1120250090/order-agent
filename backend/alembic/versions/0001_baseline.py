"""baseline：全量建表 + 种子数据（对齐 2026-09-05 现网 test 库）。

- schema：mysqldump --no-data 从现网库导出的 15 张 SQLModel 表；
- 种子：复用 sql/travel_tables.sql 的槽位字典 / POI / 通勤时间数据；
- 说明：meal_item、diet_messages_backup_20260812 等遗留表不进迁移；
- 全新环境：alembic upgrade head 即可建出全库；旧库：alembic stamp head。
"""
import pathlib

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_BASELINE_SQL = pathlib.Path(__file__).with_name("0001_baseline_schema.sql")

# 反向清理顺序（无外键约束，仅按语义倒序）
_TABLES = [
    "data_cache",
    "transfer_time_cache",
    "poi_station",
    "user_channel_binding",
    "trip_summary",
    "user_profile",
    "travel_task",
    "travel_order",
    "travel_plan",
    "travel_trip",
    "recommend_feedback",
    "diet_slot_option",
    "diet_request_trace",
    "diet_messages",
    "diet_sessions",
]


def _statements() -> list:
    """读取 baseline SQL，去掉注释行后按分号拆成可执行语句。"""
    text = _BASELINE_SQL.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    parts = [p.strip() for p in "\n".join(lines).split(";")]
    return [p for p in parts if p]


def upgrade() -> None:
    for stmt in _statements():
        op.execute(stmt)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS `{table}`")
