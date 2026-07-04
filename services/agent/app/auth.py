"""认证与安全 (Phase B)：密码哈希、服务端会话、当前用户依赖、CSRF、BYOK 加密。

安全约定（对齐 docs/plans/2026-07-03 §8.1/§8.7）：
- 密码用 scrypt (stdlib, memory-hard) 加盐哈希；永不明文/日志。
- 会话 token 随机生成，DB 只存 sha256(token)；cookie 只放明文 token (httpOnly+Secure+SameSite=Lax)。
- 非 GET 请求校验 Origin/Referer 属可信来源 (CSRF 防护，SameSite 之外的第二道)。
- BYOK key 用 Fernet(APP_SECRET_KEY 派生) 加密后存 DB；明文只在调用瞬间存在，永不落库/日志。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .errors import ApiError
from .logging_setup import get_logger
from .models import User
from .repositories import session as session_repo

log = get_logger(__name__)

COOKIE_NAME = "aria_session"

if not settings.app_secret_key:
    if settings.env == "production":
        # 生产强制：缺失会导致 BYOK 密文被公共默认密钥保护，DB 泄露即可解（codex 二审 P2）。
        raise RuntimeError(
            "生产环境（BIBLIOCN_ENV=production）必须设置 APP_SECRET_KEY："
            "用于会话签名与 BYOK 密钥 Fernet 加密。"
        )
    log.warning(
        "APP_SECRET_KEY 未设置：使用不安全的开发默认密钥。"
        "生产环境必须设置 APP_SECRET_KEY（否则 session 可伪造、BYOK 密文可解）。"
    )

_DEV_SECRET = "dev-insecure-default-change-me"


# ---------------------------------------------------------------------------
# 密码哈希 (scrypt, stdlib)
# ---------------------------------------------------------------------------

_SCRYPT_N = 2 ** 14  # ~16MB 内存代价
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(pw: str) -> str:
    """scrypt 加盐哈希，返回 'scrypt$N$r$p$salt_hex$hash_hex' 自描述字符串。"""
    if not pw:
        raise ApiError(400, "INVALID_PASSWORD", "密码不能为空")
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                        p=_SCRYPT_P, dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    """常量时间校验密码。stored 为 None（OAuth-only 用户）或格式非法时返回 False。"""
    if not stored:
        return False
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p),
                            dklen=len(hash_hex) // 2, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# 登录时对不存在的用户也跑一次校验，消除「邮箱是否存在」的时序侧信道（codex 二审 P2）。
_DUMMY_HASH = hash_password("aria-constant-time-dummy")


# ---------------------------------------------------------------------------
# 会话 token
# ---------------------------------------------------------------------------

def new_session_token() -> tuple[str, str]:
    """生成 (明文 token 放 cookie, sha256 hash 存 DB)。"""
    tok = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    return tok, hash_token(tok)


def hash_token(tok: str) -> str:
    """cookie token → DB 主键 (sha256 十六进制)。"""
    return hashlib.sha256(tok.encode()).hexdigest()


def ip_hash(request: Request) -> str | None:
    """客户端 IP 的加盐哈希（排查异常用，不存明文 IP）。"""
    ip = request.client.host if request.client else None
    if not ip:
        return None
    salt = settings.app_secret_key or _DEV_SECRET
    return hashlib.sha256((ip + salt).encode()).hexdigest()


# ---------------------------------------------------------------------------
# BYOK 密钥加密 (Fernet)
# ---------------------------------------------------------------------------

def _fernet() -> Fernet:
    secret = settings.app_secret_key or _DEV_SECRET
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """加密 BYOK key 明文 → 密文串（存 User.encrypted_keys）。"""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(cipher: str) -> str:
    """解密 BYOK 密文 → 明文（仅调用瞬间使用，永不落库/日志）。"""
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except InvalidToken as exc:
        # 通常是 APP_SECRET_KEY 轮换后旧密文无法解（需 key_version 迁移，Phase C）。
        raise ApiError(500, "BYOK_DECRYPT_FAILED", "无法解密已保存的 API Key，请重新填写") from exc


# ---------------------------------------------------------------------------
# 依赖注入：当前用户 + CSRF
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    s: AsyncSession = Depends(get_session),
) -> User:
    """从 httpOnly cookie 解析会话到 User；未登录/过期→401，禁用→403。"""
    tok = request.cookies.get(COOKIE_NAME)
    if not tok:
        raise ApiError(401, "UNAUTHENTICATED", "未登录")
    user = await session_repo.resolve_user(s, hash_token(tok))
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED", "会话无效或已过期")
    if user.status != "active":
        raise ApiError(403, "USER_DISABLED", "账号已被禁用")
    return user


async def get_current_user_optional(
    request: Request,
    s: AsyncSession = Depends(get_session),
) -> User | None:
    """可选当前用户（用于既支持登录也支持匿名 demo 的端点）。"""
    tok = request.cookies.get(COOKIE_NAME)
    if not tok:
        return None
    user = await session_repo.resolve_user(s, hash_token(tok))
    if user is None or user.status != "active":
        return None
    return user


def _trusted_origins() -> set[str]:
    return set(settings.trusted_origins) or set(settings.cors_origins)


def _origin_of(url: str) -> str | None:
    try:
        p = urlsplit(url)
        if not p.scheme or not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}"
    except ValueError:
        return None


async def require_csrf(request: Request) -> None:
    """非安全方法校验 Origin/Referer 属可信来源（CSRF 第二道防线）。

    未配置可信来源时（本地开发）跳过。GET/HEAD/OPTIONS 天然安全，放行。
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    allowed = _trusted_origins()
    if not allowed:
        return
    origin = request.headers.get("origin")
    src = origin or _origin_of(request.headers.get("referer") or "")
    # 无 Origin/Referer：依赖 SameSite=Lax cookie 防护（跨站请求不携带会话 cookie），放行，
    # 避免误伤同源部署下浏览器可能不带 Origin 的 POST。仅当来源存在且不在白名单才拒。
    if src is not None and src not in allowed:
        raise ApiError(403, "CSRF_FORBIDDEN", "跨源请求被拒绝")


# ---------------------------------------------------------------------------
# Cookie 读写
# ---------------------------------------------------------------------------

def set_session_cookie(response, token: str, *, secure: bool = True) -> None:
    """写会话 cookie（httpOnly + Secure + SameSite=Lax）。

    secure 默认由调用方按请求 scheme 推断；SESSION_COOKIE_SECURE 显式配置时覆盖，
    避免反代头缺失导致签发非 Secure cookie（codex 二审 P2）。
    """
    cfg = settings.cookie_secure
    if cfg == "1":
        secure = True
    elif cfg == "0":
        secure = False
    response.set_cookie(
        COOKIE_NAME, token,
        httponly=True, secure=secure, samesite="lax",
        max_age=settings.session_ttl_days * 86400, path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
