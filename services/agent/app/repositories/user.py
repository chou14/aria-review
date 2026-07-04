"""用户仓储：创建 / 查询 / 邀请码注册 / BYOK 密钥 / 状态。

register_with_invite 用 SELECT ... FOR UPDATE 锁邀请码行，保证并发下同一码只被消费一次。
BYOK 密钥以 Fernet 密文形式存 User.encrypted_keys（加解密在 app.auth，本层只存取密文）。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ApiError
from ..models import InviteCode, User


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def normalize_email(email: str | None) -> str:
    e = (email or "").strip().lower()
    if not e or "@" not in e or e.startswith("@") or e.endswith("@"):
        raise ApiError(400, "INVALID_EMAIL", "邮箱格式不正确")
    return e


async def get_by_email(s: AsyncSession, email: str) -> User | None:
    return (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def get_by_id(s: AsyncSession, uid: int) -> User | None:
    return (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()


async def register_with_invite(
    s: AsyncSession,
    *,
    email: str,
    password_hash: str,
    invite_code: str | None,
    invite_required: bool = True,
    display_name: str | None = None,
) -> User:
    """邀请码注册。邮箱唯一 + 邀请码单次消费（行锁）；冲突抛对应 ApiError。"""
    email = normalize_email(email)

    # 先校验邀请码，再查邮箱：否则未持有效邀请码者也能凭 EMAIL_EXISTS / INVALID_INVITE
    # 的差异枚举邮箱是否已注册（codex 二审 P2）。
    code_row: InviteCode | None = None
    if invite_required:
        if not invite_code:
            raise ApiError(400, "INVALID_INVITE", "需要邀请码")
        code_row = (
            await s.execute(
                select(InviteCode).where(InviteCode.code == invite_code).with_for_update()
            )
        ).scalar_one_or_none()
        if code_row is None:
            raise ApiError(400, "INVALID_INVITE", "邀请码无效")
        # used_at 为权威判据（used_by 因 ondelete=SET NULL 会回退，删用户后邀请码会复活）。
        if code_row.used_at is not None:
            raise ApiError(409, "INVITE_USED", "邀请码已被使用")
        if code_row.expires_at is not None and code_row.expires_at < _utcnow():
            raise ApiError(400, "INVITE_EXPIRED", "邀请码已过期")

    if await get_by_email(s, email) is not None:
        raise ApiError(409, "EMAIL_EXISTS", "该邮箱已注册")

    user = User(email=email, password_hash=password_hash, display_name=display_name)
    s.add(user)
    try:
        await s.flush()  # 拿 user.id；email 唯一撞车在此抛 IntegrityError
    except IntegrityError:
        await s.rollback()
        raise ApiError(409, "EMAIL_EXISTS", "该邮箱已注册")

    if code_row is not None:
        code_row.used_by = user.id
        code_row.used_at = _utcnow()

    await s.commit()
    await s.refresh(user)
    return user


async def set_encrypted_keys(s: AsyncSession, uid: int, keys: dict) -> User:
    """覆盖写 BYOK 密文（keys 已是 {provider: fernet_cipher}）。"""
    u = await get_by_id(s, uid)
    if u is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    u.encrypted_keys = keys
    await s.commit()
    await s.refresh(u)
    return u


async def upsert_encrypted_key(
    s: AsyncSession, uid: int, provider: str, cipher: str | None
) -> dict:
    """行锁内合并单个 provider 的 BYOK 密钥，避免并发读-改-写丢更新（codex 二审 P2）。

    cipher 为 None/空表示删除该 provider。返回合并后的 {provider: cipher} 全量映射。
    """
    u = (
        await s.execute(select(User).where(User.id == uid).with_for_update())
    ).scalar_one_or_none()
    if u is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    keys = dict(u.encrypted_keys or {})
    if cipher:
        keys[provider] = cipher
    else:
        keys.pop(provider, None)
    u.encrypted_keys = keys
    await s.commit()
    return keys


async def set_status(s: AsyncSession, uid: int, status: str) -> User:
    """启用/禁用用户（运维）。"""
    if status not in ("active", "disabled"):
        raise ApiError(400, "INVALID_STATUS", "状态非法")
    u = await get_by_id(s, uid)
    if u is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    u.status = status
    await s.commit()
    await s.refresh(u)
    return u
