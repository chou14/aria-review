#!/usr/bin/env python
"""运维脚本：按邮箱禁用或启用用户。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 把 services/agent 加入 sys.path（脚本直接运行时需要）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_SERVICE_DIR = _SCRIPT_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.repositories import session as session_repo  # noqa: E402
from app.repositories import user as user_repo  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按邮箱禁用或启用用户")
    parser.add_argument("--email", required=True, help="用户邮箱")
    parser.add_argument("--enable", action="store_true", help="启用用户；默认禁用")
    return parser.parse_args()


async def _amain(args: argparse.Namespace) -> int:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    target_status = "active" if args.enable else "disabled"
    revoked = 0

    try:
        async with factory() as s:
            try:
                email = user_repo.normalize_email(args.email)
                u = await user_repo.get_by_email(s, email)
                if u is None:
                    print(f"用户不存在：{email}", file=sys.stderr)
                    return 1
                u = await user_repo.set_status(s, u.id, target_status)
                if not args.enable:
                    revoked = await session_repo.revoke_all_for_user(s, u.id)
            except ApiError as exc:
                print(f"{exc.code}: {exc.message}", file=sys.stderr)
                return 1
    finally:
        await engine.dispose()

    if args.enable:
        print(f"{email} 已启用：status={u.status}")
    else:
        print(f"{email} 已禁用：status={u.status} revoked_sessions={revoked}")
    return 0


def main() -> int:
    return asyncio.run(_amain(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
