"""积分计费仓储：原子扣费 / 记账 / 预扣退款 / 余额查询。

核心不变量：User.credits 与 credit_ledger 流水在同一事务内一致更新。
防超扣（并发安全）：扣费用 UPDATE ... WHERE credits >= cost，影响行数=0 即余额不足，
不做「先读余额再写」（那样并发下会超扣）。
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ApiError
from ..models import CreditLedger, User


async def get_balance(s: AsyncSession, uid: int) -> int:
    r = (await s.execute(select(User.credits).where(User.id == uid))).scalar_one_or_none()
    if r is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    return r


async def charge(
    s: AsyncSession, uid: int, cost: int, *, reason: str = "consume", ref: str | None = None
) -> int:
    """原子扣费。成功返回扣后余额；余额不足抛 402。cost<=0 不扣、不记账。"""
    if cost <= 0:
        return await get_balance(s, uid)
    r = await s.execute(
        update(User)
        .where(User.id == uid, User.credits >= cost)
        .values(credits=User.credits - cost)
        .returning(User.credits)
    )
    row = r.first()
    if row is None:
        # 用户不存在 或 余额不足 —— 区分给友好错误
        exists = (await s.execute(select(User.id).where(User.id == uid))).scalar_one_or_none()
        # 不 rollback：上面 UPDATE 命中 0 行、无脏数据；rollback 会 expire 调用方持有的
        # ORM 对象，其后同步访问其属性会触发意外 IO（MissingGreenlet）。事务由上层收尾。
        if exists is None:
            raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
        raise ApiError(402, "INSUFFICIENT_CREDITS", "积分不足，请充值或改用自带 API Key")
    new_balance = row[0]
    s.add(CreditLedger(user_id=uid, delta=-cost, reason=reason, ref=ref, balance_after=new_balance))
    await s.commit()
    return new_balance


async def refund(s: AsyncSession, uid: int, amount: int, *, ref: str | None = None) -> int:
    """退款（预扣任务失败时把积分加回）。返回新余额。"""
    if amount <= 0:
        return await get_balance(s, uid)
    r = await s.execute(
        update(User).where(User.id == uid)
        .values(credits=User.credits + amount).returning(User.credits)
    )
    row = r.first()
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")  # UPDATE 0 行无脏数据，不 rollback（见 charge）
    new_balance = row[0]
    s.add(CreditLedger(user_id=uid, delta=amount, reason="refund", ref=ref, balance_after=new_balance))
    await s.commit()
    return new_balance


async def grant(
    s: AsyncSession, uid: int, amount: int, *, reason: str = "adjust", ref: str | None = None
) -> int:
    """人工调账（正=加/负=扣，不校验余额，供运维纠错）。返回新余额。"""
    r = await s.execute(
        update(User).where(User.id == uid)
        .values(credits=User.credits + amount).returning(User.credits)
    )
    row = r.first()
    if row is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")  # UPDATE 0 行无脏数据，不 rollback（见 charge）
    new_balance = row[0]
    s.add(CreditLedger(user_id=uid, delta=amount, reason=reason, ref=ref, balance_after=new_balance))
    await s.commit()
    return new_balance


async def history(s: AsyncSession, uid: int, limit: int = 50) -> list[CreditLedger]:
    q = (
        select(CreditLedger)
        .where(CreditLedger.user_id == uid)
        .order_by(CreditLedger.id.desc())
        .limit(limit)
    )
    return list((await s.execute(q)).scalars().all())
