"""Phase B 认证与计费测试：密码/会话/邀请码/原子扣费/兑换/BYOK + 并发安全。

用 conftest 的 session / session_factory fixture（每测试 create_all/drop_all 隔离）。
asyncio_mode=auto（见 pyproject），async 测试无需 marker。
"""
from __future__ import annotations

import asyncio

import pytest

from app import auth
from app.errors import ApiError
from app.models import InviteCode, RedeemCode
from app.repositories import credit as credit_repo
from app.repositories import redeem as redeem_repo
from app.repositories import session as session_repo
from app.repositories import user as user_repo


async def _mk_user(s, email: str):
    return await user_repo.register_with_invite(
        s, email=email, password_hash="h", invite_code=None, invite_required=False)


# --------------------------- 密码 / 会话 ---------------------------

async def test_password_hash_roundtrip(session):
    ph = auth.hash_password("secret123")
    assert ph.startswith("scrypt$")
    assert auth.verify_password("secret123", ph)
    assert not auth.verify_password("wrong", ph)
    assert not auth.verify_password("x", None)  # OAuth-only 用户 password_hash=None


async def test_session_lifecycle(session):
    u = await _mk_user(session, "s@x.io")
    tok, th = auth.new_session_token()
    assert auth.hash_token(tok) == th
    await session_repo.create_session(session, u.id, th, 14)
    resolved = await session_repo.resolve_user(session, th)
    assert resolved is not None and resolved.id == u.id
    await session_repo.revoke(session, th)
    assert await session_repo.resolve_user(session, th) is None


# --------------------------- 注册 / 邀请码 ---------------------------

async def test_register_with_invite(session):
    session.add(InviteCode(code="INV-1"))
    await session.commit()
    u = await user_repo.register_with_invite(
        session, email="A@X.io", password_hash="h", invite_code="INV-1")
    assert u.email == "a@x.io"  # 归一化小写

    # 邀请码复用被拒
    with pytest.raises(ApiError) as ei:
        await user_repo.register_with_invite(
            session, email="b@x.io", password_hash="h", invite_code="INV-1")
    assert ei.value.code == "INVITE_USED"

    # 重复邮箱被拒
    session.add(InviteCode(code="INV-2"))
    await session.commit()
    with pytest.raises(ApiError) as ei:
        await user_repo.register_with_invite(
            session, email="a@x.io", password_hash="h", invite_code="INV-2")
    assert ei.value.code == "EMAIL_EXISTS"


async def test_register_invalid_invite(session):
    with pytest.raises(ApiError) as ei:
        await user_repo.register_with_invite(
            session, email="c@x.io", password_hash="h", invite_code="NOPE")
    assert ei.value.code == "INVALID_INVITE"


# --------------------------- 计费 ---------------------------

async def test_charge_refund_and_ledger(session):
    u = await _mk_user(session, "c@x.io")
    await credit_repo.grant(session, u.id, 100)
    assert await credit_repo.charge(session, u.id, 30) == 70
    with pytest.raises(ApiError) as ei:
        await credit_repo.charge(session, u.id, 1000)
    assert ei.value.code == "INSUFFICIENT_CREDITS"
    assert await credit_repo.refund(session, u.id, 10) == 80
    hist = await credit_repo.history(session, u.id)
    assert sum(h.delta for h in hist) == 80  # ledger 总和 = 余额
    assert hist[0].balance_after == 80  # 最新一条 balance_after 与余额一致


async def test_charge_zero_no_ledger(session):
    u = await _mk_user(session, "z@x.io")
    await credit_repo.grant(session, u.id, 50)
    assert await credit_repo.charge(session, u.id, 0) == 50  # 0 费用不扣不记账
    hist = await credit_repo.history(session, u.id)
    assert len([h for h in hist if h.reason == "consume"]) == 0


async def test_redeem(session):
    u = await _mk_user(session, "r@x.io")
    session.add(RedeemCode(code="RC-1", credits=50))
    await session.commit()
    cr, nb = await redeem_repo.redeem(session, u.id, "RC-1")
    assert cr == 50 and nb == 50
    with pytest.raises(ApiError) as ei:
        await redeem_repo.redeem(session, u.id, "RC-1")
    assert ei.value.code == "CODE_USED"
    with pytest.raises(ApiError) as ei:
        await redeem_repo.redeem(session, u.id, "NOPE")
    assert ei.value.code == "INVALID_CODE"


# --------------------------- BYOK ---------------------------

async def test_byok_crypto(session):
    cipher = auth.encrypt_secret("sk-secret-xyz")
    assert cipher != "sk-secret-xyz"
    assert auth.decrypt_secret(cipher) == "sk-secret-xyz"


# --------------------------- 并发安全（核心）---------------------------

async def test_concurrent_charge_no_overspend(session_factory):
    """余额 100，10 个并发各扣 20 → 恰好成功 5 次、余额=0，不超扣。"""
    async with session_factory() as s:
        u = await _mk_user(s, "cc@x.io")
        await credit_repo.grant(s, u.id, 100)
        uid = u.id

    async def try_charge():
        async with session_factory() as s:
            try:
                await credit_repo.charge(s, uid, 20)
                return True
            except ApiError:
                return False

    results = await asyncio.gather(*[try_charge() for _ in range(10)])
    assert sum(results) == 5, f"应恰好成功 5 次，实际 {sum(results)}"
    async with session_factory() as s:
        assert await credit_repo.get_balance(s, uid) == 0


async def test_concurrent_redeem_single_use(session_factory):
    """同一兑换码 8 个并发兑换 → 只成功一次，余额只加一次。"""
    async with session_factory() as s:
        u = await _mk_user(s, "cr@x.io")
        s.add(RedeemCode(code="CRC-1", credits=30))
        await s.commit()
        uid = u.id

    async def try_redeem():
        async with session_factory() as s:
            try:
                await redeem_repo.redeem(s, uid, "CRC-1")
                return True
            except ApiError:
                return False

    results = await asyncio.gather(*[try_redeem() for _ in range(8)])
    assert sum(results) == 1, f"兑换码应只成功一次，实际 {sum(results)}"
    async with session_factory() as s:
        assert await credit_repo.get_balance(s, uid) == 30
