#!/usr/bin/env python
"""运维脚本：批量发放注册邀请码。"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import secrets
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 把 services/agent 加入 sys.path（脚本直接运行时需要）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_SERVICE_DIR = _SCRIPT_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import InviteCode  # noqa: E402


def _parse_date(value: str | None) -> dt.datetime | None:
    """解析 YYYY-MM-DD 为 naive UTC datetime，与数据库 DateTime 对齐。"""
    if value is None:
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--expires 必须是 YYYY-MM-DD") from exc


def _new_code(existing: set[str]) -> str:
    while True:
        code = secrets.token_urlsafe(16)[:12]
        if code not in existing:
            existing.add(code)
            return code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量生成注册邀请码")
    parser.add_argument("--n", type=int, required=True, help="生成数量")
    parser.add_argument("--note", default=None, help="批次/备注")
    parser.add_argument("--expires", type=_parse_date, default=None, help="过期日期 YYYY-MM-DD")
    args = parser.parse_args()
    if args.n <= 0:
        parser.error("--n 必须为正整数")
    return args


async def _amain(args: argparse.Namespace) -> int:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    codes: list[str] = []
    seen: set[str] = set()

    try:
        async with factory() as s:
            for _ in range(args.n):
                code = _new_code(seen)
                codes.append(code)
                s.add(InviteCode(code=code, expires_at=args.expires, note=args.note))
            try:
                await s.commit()
            except IntegrityError:
                await s.rollback()
                print("生成失败：邀请码与已有记录冲突，请重新执行。", file=sys.stderr)
                return 1
    finally:
        await engine.dispose()

    for code in codes:
        print(code)
    return 0


def main() -> int:
    return asyncio.run(_amain(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
