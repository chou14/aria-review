"""merge paper dedup title/doi duplicates

Revision ID: f0b2c3d4e5a6
Revises: c4d2e1a07f3b
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union
import os

from alembic import context, op

from app.repositories.dedup_merge import merge_duplicate_papers


# revision identifiers, used by Alembic.
revision: str = "f0b2c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "c4d2e1a07f3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _dry_run_enabled() -> bool:
    x_args = context.get_x_argument(as_dictionary=True)
    return _truthy(os.environ.get("DEDUP_MERGE_DRY_RUN")) or _truthy(x_args.get("dry_run"))


def upgrade() -> None:
    """Upgrade schema."""
    dry_run = _dry_run_enabled()
    merge_duplicate_papers(
        op.get_bind(),
        dry_run=dry_run,
        output=lambda msg: print(f"dedup merge report:\n{msg}"),
    )
    if dry_run:
        # dry-run 只出报告：必须中止迁移，否则 Alembic 会把本 revision 记为已应用，
        # 之后真跑 upgrade head 不会再执行合并，双轨重复数据永久遗留。
        raise RuntimeError(
            "DEDUP_MERGE_DRY_RUN/-x dry_run 为 dry-run 模式：报告已输出，迁移已中止未记录。"
            "确认报告无误后，去掉 dry-run 参数重新执行 alembic upgrade head。"
        )


def downgrade() -> None:
    """Downgrade schema."""
    # data migration 不可逆：合并后源 paper id 已删除，历史引用无法无损拆回。
    pass
