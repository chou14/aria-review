"""add agent_run.entry (三入口隔离)

Revision ID: a1b2c3d4e5f7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-05 18:00:00.000000

P0 三入口隔离：agent_run 加 entry 列（search/review/gap）；NULL = legacy 全工具入口。
既有行保持 NULL（向后兼容），列 nullable，加索引供 list_recent_dialog 按 entry 过滤。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("agent_run", sa.Column("entry", sa.String(length=16), nullable=True))
    op.create_index("ix_agent_run_entry", "agent_run", ["entry"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_agent_run_entry", table_name="agent_run")
    op.drop_column("agent_run", "entry")
