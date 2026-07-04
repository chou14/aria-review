"""会话仓储：创建 / 解析 / 吊销服务端会话（主键 = sha256(token)）。

resolve_user 只读（不更新 last_seen），避免每个认证请求一次 DB 写。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuthSession, User


def _utcnow() -> dt.datetime:
    # 与 DB naive DateTime 对齐（models 用 server_default now()，此处比较用 naive UTC）。
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


async def create_session(
    s: AsyncSession,
    user_id: int,
    token_hash: str,
    ttl_days: int,
    ip_hash: str | None = None,
) -> AuthSession:
    """新建会话行（token_hash 作主键，明文 token 由调用方放 cookie）。"""
    now = _utcnow()
    sess = AuthSession(
        id=token_hash,
        user_id=user_id,
        expires_at=now + dt.timedelta(days=ttl_days),
        last_seen_at=now,
        ip_hash=ip_hash,
    )
    s.add(sess)
    await s.commit()
    return sess


async def resolve_user(s: AsyncSession, token_hash: str) -> User | None:
    """token_hash → 未过期会话对应的 User；无效/过期返回 None。"""
    q = (
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.id == token_hash, AuthSession.expires_at > _utcnow())
    )
    return (await s.execute(q)).scalar_one_or_none()


async def revoke(s: AsyncSession, token_hash: str) -> None:
    """吊销单个会话（登出）。"""
    await s.execute(delete(AuthSession).where(AuthSession.id == token_hash))
    await s.commit()


async def revoke_all_for_user(s: AsyncSession, user_id: int) -> int:
    """吊销某用户全部会话（改密码/禁用/踢下线）。返回删除数。"""
    r = await s.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    await s.commit()
    return r.rowcount or 0


async def purge_expired(s: AsyncSession) -> int:
    """清理过期会话（运维脚本可调）。返回删除数。"""
    r = await s.execute(delete(AuthSession).where(AuthSession.expires_at <= _utcnow()))
    await s.commit()
    return r.rowcount or 0
