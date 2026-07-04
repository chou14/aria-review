#!/usr/bin/env python
"""回填存量 project/paper 的 owner_id 到指定账户（Round 5 不可逆迁移前置）。

用途：多租户上线前，把 owner_id 为空的存量 project/paper 归属到一个账户
（通常是管理员/迁移账户），使后续 owner_id NOT NULL + per-owner 唯一约束迁移可行。

默认 dry-run（只统计不写入）；加 --apply 才真正回填。生产执行前请先备份主库。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from sqlalchemy import text, update  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import Paper, Project  # noqa: E402
from app.repositories import user as user_repo  # noqa: E402


async def _amain(email: str, apply: bool) -> int:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as s:
            u = await user_repo.get_by_email(s, email)
            if u is None:
                print(f"账户不存在: {email}。请先用 issue_invites.py 发码 + 注册创建该账户。",
                      file=sys.stderr)
                return 1
            proj_null = (await s.execute(
                text("select count(*) from project where owner_id is null"))).scalar()
            paper_null = (await s.execute(
                text("select count(*) from paper where owner_id is null"))).scalar()
            print(f"待回填 → owner_id={u.id} ({email}): project={proj_null}, paper={paper_null}")
            if not apply:
                print("dry-run（未写入）。确认无误后加 --apply 执行；生产请先备份主库。")
                return 0
            await s.execute(
                update(Project).where(Project.owner_id.is_(None)).values(owner_id=u.id))
            await s.execute(
                update(Paper).where(Paper.owner_id.is_(None)).values(owner_id=u.id))
            await s.commit()
            print(f"回填完成：project +{proj_null}, paper +{paper_null} → owner_id={u.id}")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    p = argparse.ArgumentParser(description="回填存量 project/paper 的 owner_id")
    p.add_argument("--owner-email", required=True, help="归属账户的邮箱（须已注册）")
    p.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    args = p.parse_args()
    return asyncio.run(_amain(args.owner_email, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
