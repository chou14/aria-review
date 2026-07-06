"""add gap_candidate.feasibility_verdict/feasibility_pack (P2 feasibility-scout)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-05 19:30:00.000000

P2 feasibility-scout：gap_candidate 加 feasibility_verdict / feasibility_pack 两 JSON 列
（与 novelty/value 解耦的可行性裁决 + 攒证包）。均 nullable，既有行保持 NULL（向后兼容）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("gap_candidate", sa.Column("feasibility_verdict", sa.JSON(), nullable=True))
    op.add_column("gap_candidate", sa.Column("feasibility_pack", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("gap_candidate", "feasibility_pack")
    op.drop_column("gap_candidate", "feasibility_verdict")
