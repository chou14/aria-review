#!/usr/bin/env python
"""运维脚本：查询用户余额与积分流水。"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 把 services/agent 加入 sys.path（脚本直接运行时需要）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_SERVICE_DIR = _SCRIPT_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.models import User  # noqa: E402
from app.repositories import credit as credit_repo  # noqa: E402
from app.repositories import user as user_repo  # noqa: E402


def _fmt_time(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(sep=" ", timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查询用户余额与积分流水")
    parser.add_argument("--email", default=None, help="用户邮箱；不传则列出所有用户")
    return parser.parse_args()


async def _print_all_users(factory: async_sessionmaker) -> int:
    async with factory() as s:
        users = list((await s.execute(select(User).order_by(User.id))).scalars().all())

    print("id\temail\tcredits\tstatus\tcreated_at")
    for u in users:
        print(f"{u.id}\t{u.email}\t{u.credits}\t{u.status}\t{_fmt_time(u.created_at)}")
    return 0


async def _print_one_user(factory: async_sessionmaker, raw_email: str) -> int:
    async with factory() as s:
        try:
            email = user_repo.normalize_email(raw_email)
            u = await user_repo.get_by_email(s, email)
            if u is None:
                print(f"用户不存在：{email}", file=sys.stderr)
                return 1
            balance = await credit_repo.get_balance(s, u.id)
            rows = await credit_repo.history(s, u.id)
        except ApiError as exc:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            return 1

    print(f"用户：id={u.id} email={u.email} status={u.status} balance={balance}")
    print("id\tdelta\treason\tref\tbalance_after\tcreated_at")
    for row in rows:
        print(
            f"{row.id}\t{row.delta}\t{row.reason}\t{row.ref or ''}\t"
            f"{row.balance_after}\t{_fmt_time(row.created_at)}"
        )
    return 0


async def _amain(args: argparse.Namespace) -> int:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if args.email:
            return await _print_one_user(factory, args.email)
        return await _print_all_users(factory)
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(_amain(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
