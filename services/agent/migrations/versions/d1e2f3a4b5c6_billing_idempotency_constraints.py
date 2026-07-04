"""billing idempotency + positive-credits constraints (codex 二审 P1)

Revision ID: d1e2f3a4b5c6
Revises: cb2f807c1d12
Create Date: 2026-07-03

- redeem_code: CHECK(credits > 0) —— 防负面值码扣余额 / 零面值消耗码不给分。
- credit_ledger: 部分唯一索引 (user_id, reason, ref) WHERE ref IS NOT NULL ——
  幂等护栏，防重复扣费/退款静默送钱或双扣；ref 为空的运维调账(adjust)不受约束。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "cb2f807c1d12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_redeem_code_credits_positive", "redeem_code", "credits > 0")
    op.create_index(
        "uq_credit_ledger_idempotent", "credit_ledger",
        ["user_id", "reason", "ref"], unique=True,
        postgresql_where=sa.text("ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_credit_ledger_idempotent", table_name="credit_ledger")
    op.drop_constraint(
        "ck_redeem_code_credits_positive", "redeem_code", type_="check")
