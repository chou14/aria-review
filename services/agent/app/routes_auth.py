"""认证与账户路由 (Phase B)：注册 / 登录 / 登出 / 当前用户 / 兑换 / 积分 / BYOK 密钥。

- 会话走 httpOnly cookie（app.auth 签发）；mutating 端点挂 require_csrf（Origin/Referer 校验）。
- register/login 是认证入口，豁免 CSRF；logout/redeem/keys 需 CSRF。
- BYOK key 加密存储，/keys 只回哪些 provider 已配置，绝不回明文。
- 登录爆破限流交由反代层（Caddy，Phase A）/ Phase C 应用层限流处理。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from . import auth
from .config import settings
from .db import get_session
from .errors import ApiError
from .models import User
from .repositories import credit as credit_repo
from .repositories import redeem as redeem_repo
from .repositories import session as session_repo
from .repositories import user as user_repo

router = APIRouter(prefix="/auth", tags=["auth"])

_ALLOWED_PROVIDERS = {"deepseek", "mineru", "image", "sciverse"}


# --------------------------- 请求 / 响应模型 ---------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    invite_code: str | None = None
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RedeemRequest(BaseModel):
    code: str


class SetKeyRequest(BaseModel):
    provider: str
    api_key: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None
    role: str
    credits: int

    @classmethod
    def of(cls, u: User) -> "UserOut":
        return cls(id=u.id, email=u.email, display_name=u.display_name,
                   role=u.role, credits=u.credits)


# --------------------------- 辅助 ---------------------------

def _cookie_secure(request: Request) -> bool:
    """反代终止 TLS 时用 X-Forwarded-Proto 判定，否则看 request scheme。"""
    xfp = request.headers.get("x-forwarded-proto", "")
    return (xfp or request.url.scheme) == "https"


async def _issue_session(s: AsyncSession, response: Response, request: Request, user: User) -> None:
    tok, token_hash = auth.new_session_token()
    await session_repo.create_session(
        s, user.id, token_hash, settings.session_ttl_days, ip_hash=auth.ip_hash(request))
    auth.set_session_cookie(response, tok, secure=_cookie_secure(request))


# --------------------------- 认证入口 ---------------------------

@router.post("/register", response_model=UserOut)
async def register(
    body: RegisterRequest, request: Request, response: Response,
    s: AsyncSession = Depends(get_session),
):
    if not settings.allow_registration:
        raise ApiError(403, "REGISTRATION_CLOSED", "当前未开放自助注册")
    pw_hash = auth.hash_password(body.password)
    user = await user_repo.register_with_invite(
        s, email=body.email, password_hash=pw_hash,
        invite_code=body.invite_code, invite_required=settings.invite_required,
        display_name=body.display_name)
    await _issue_session(s, response, request, user)
    return UserOut.of(user)


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest, request: Request, response: Response,
    s: AsyncSession = Depends(get_session),
):
    email = user_repo.normalize_email(body.email)
    user = await user_repo.get_by_email(s, email)
    if user is None:
        auth.verify_password(body.password, auth._DUMMY_HASH)  # 恒定时间，消除邮箱枚举侧信道
        raise ApiError(401, "INVALID_CREDENTIALS", "邮箱或密码错误")
    if not auth.verify_password(body.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "邮箱或密码错误")
    if user.status != "active":
        raise ApiError(403, "USER_DISABLED", "账号已被禁用")
    await _issue_session(s, response, request, user)
    return UserOut.of(user)


@router.post("/logout")
async def logout(
    request: Request, response: Response,
    s: AsyncSession = Depends(get_session),
    _: None = Depends(auth.require_csrf),
):
    tok = request.cookies.get(auth.COOKIE_NAME)
    if tok:
        await session_repo.revoke(s, auth.hash_token(tok))
    auth.clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(auth.get_current_user)):
    return UserOut.of(user)


# --------------------------- 积分 / 兑换 ---------------------------

@router.post("/redeem")
async def redeem(
    body: RedeemRequest,
    s: AsyncSession = Depends(get_session),
    user: User = Depends(auth.get_current_user),
    _: None = Depends(auth.require_csrf),
):
    credits, balance = await redeem_repo.redeem(s, user.id, body.code.strip())
    return {"credits_added": credits, "balance": balance}


@router.get("/credits")
async def get_credits(
    s: AsyncSession = Depends(get_session),
    user: User = Depends(auth.get_current_user),
):
    bal = await credit_repo.get_balance(s, user.id)
    hist = await credit_repo.history(s, user.id, limit=50)
    return {
        "balance": bal,
        "ledger": [
            {
                "delta": h.delta, "reason": h.reason, "ref": h.ref,
                "balance_after": h.balance_after,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in hist
        ],
    }


# --------------------------- BYOK 密钥 ---------------------------

@router.get("/keys")
async def get_keys(user: User = Depends(auth.get_current_user)):
    """只回哪些 provider 已配置（绝不回明文/密文）。"""
    keys = user.encrypted_keys or {}
    return {"providers": {p: True for p in keys}}


@router.put("/keys")
async def set_key(
    body: SetKeyRequest,
    s: AsyncSession = Depends(get_session),
    user: User = Depends(auth.get_current_user),
    _: None = Depends(auth.require_csrf),
):
    if body.provider not in _ALLOWED_PROVIDERS:
        raise ApiError(400, "INVALID_PROVIDER", "不支持的 provider")
    # 行锁内合并单个 provider，避免并发读-改-写丢更新（codex 二审 P2）；空值=删除该 key。
    cipher = auth.encrypt_secret(body.api_key.strip()) if body.api_key.strip() else None
    keys = await user_repo.upsert_encrypted_key(s, user.id, body.provider, cipher)
    return {"providers": {p: True for p in keys}}
