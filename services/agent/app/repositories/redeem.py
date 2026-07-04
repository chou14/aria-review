"""兑换码仓储：原子兑换（并发下同一码只被兑换一次）。

原子性：UPDATE ... WHERE code=? AND used_by IS NULL AND (未过期) 一步占用，
影响行数=0 即区分「不存在/已用/过期」给友好错误；随后同事务加积分 + 记流水。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ApiError
from ..models import CreditLedger, RedeemCode, User


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


async def redeem(s: AsyncSession, uid: int, code: str) -> tuple[int, int]:
    """兑换积分码。返回 (本次面值, 兑后余额)。无效/已用/过期抛 ApiError。"""
    now = _utcnow()
    # 原子占用：仅当未被使用且未过期，才占为本用户。
    r = await s.execute(
        update(RedeemCode)
        .where(
            RedeemCode.code == code,
            RedeemCode.used_at.is_(None),  # 权威判据（used_by 因 SET NULL 会回退，不能用它判）
            or_(RedeemCode.expires_at.is_(None), RedeemCode.expires_at > now),
        )
        .values(used_by=uid, used_at=now)
        .returning(RedeemCode.credits)
    )
    row = r.first()
    if row is None:
        # 占用失败：查真实原因给友好错误
        rc = (
            await s.execute(select(RedeemCode).where(RedeemCode.code == code))
        ).scalar_one_or_none()
        # 不 rollback：占用 UPDATE 命中 0 行、无脏数据；rollback 会 expire 调用方 ORM 对象
        # 导致后续同步访问触发 IO（MissingGreenlet）。（见 credit.charge 说明）
        if rc is None:
            raise ApiError(400, "INVALID_CODE", "兑换码无效")
        if rc.used_at is not None:
            raise ApiError(409, "CODE_USED", "兑换码已被使用")
        raise ApiError(400, "CODE_EXPIRED", "兑换码已过期")

    credits = row[0]
    # 同事务加积分 + 记流水（与占用一致提交）。
    r2 = await s.execute(
        update(User).where(User.id == uid)
        .values(credits=User.credits + credits).returning(User.credits)
    )
    urow = r2.first()
    if urow is None:
        await s.rollback()
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    new_balance = urow[0]
    s.add(CreditLedger(user_id=uid, delta=credits, reason="redeem", ref=code, balance_after=new_balance))
    await s.commit()
    return credits, new_balance
