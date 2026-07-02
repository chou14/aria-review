"""Task 1.5: Library 仓储测试 (TDD: 先失败 → 实现 → PASS)。

测试关注点:
  - add_paper 正常写入, 返回带 id 的 Paper
  - add_paper 对相同 DOI 幂等 (dedup)，返回同一行 id
  - add_paper 无 DOI 时用标题 hash 去重
  - find_by_dedup 按 dedup_key 查询
  - DOI 大小写幂等（锁 I1 + 大小写归一）
  - DOI URL 前缀 vs 裸 DOI 幂等（锁 I1）

session fixture 由 conftest.py 提供。
"""

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

async def test_add_paper_creates_record(session):
    """add_paper 写入新 Paper，返回带 id 的 ORM 对象。"""
    from app.repositories.library import add_paper

    p = await add_paper(session, {"title": "Deep Learning", "doi": "10.1/dl"})
    assert p.id is not None
    assert p.dedup_key == "doi:10.1/dl"
    assert p.title == "Deep Learning"


async def test_add_paper_dedup_by_doi(session):
    """相同 DOI 重复调用 add_paper 应幂等，返回同一行 id。"""
    from app.repositories.library import add_paper

    p1 = await add_paper(session, {"title": "Deep X", "doi": "10.1/x"})
    p2 = await add_paper(session, {"title": "Deep X", "doi": "10.1/x"})
    assert p1.id is not None
    assert p2.id == p1.id  # 命中 dedup，不新建


async def test_add_paper_dedup_by_title_hash(session):
    """无 DOI 时用标题 hash 去重，重复标题不新建行。"""
    from app.repositories.library import add_paper

    p1 = await add_paper(session, {"title": "Novel Approach"})
    p2 = await add_paper(session, {"title": "Novel Approach"})
    assert p2.id == p1.id


async def test_find_by_dedup(session):
    """find_by_dedup 能按 dedup_key 检索到已存在的 Paper。"""
    from app.repositories.library import add_paper, find_by_dedup

    p = await add_paper(session, {"title": "Test Paper", "doi": "10.1/tp"})
    found = await find_by_dedup(session, p.dedup_key)
    assert found is not None
    assert found.id == p.id


async def test_find_by_dedup_missing_returns_none(session):
    """find_by_dedup 对不存在的 key 返回 None。"""
    from app.repositories.library import find_by_dedup

    result = await find_by_dedup(session, "doi:10.999/nonexistent")
    assert result is None


async def test_add_paper_doi_case_idempotent(session):
    """DOI 大小写不同应视为同一篇（锁 I1 大小写归一）。"""
    from app.repositories.library import add_paper

    p1 = await add_paper(session, {"title": "Case Study", "doi": "10.1/ABC"})
    p2 = await add_paper(session, {"title": "Case Study", "doi": "10.1/abc"})
    assert p1.id == p2.id, "DOI 大小写不同应命中同一行"


async def test_add_paper_doi_url_prefix_idempotent(session):
    """DOI URL 前缀与裸 DOI 应视为同一篇（锁 I1 URL 前缀剥离）。"""
    from app.repositories.library import add_paper

    p1 = await add_paper(session, {"title": "URL Prefix Test", "doi": "10.1/url"})
    p2 = await add_paper(session, {"title": "URL Prefix Test", "doi": "https://doi.org/10.1/url"})
    p3 = await add_paper(session, {"title": "URL Prefix Test", "doi": "http://dx.doi.org/10.1/url"})
    assert p1.id == p2.id, "https://doi.org/ 前缀应被剥离"
    assert p1.id == p3.id, "http://dx.doi.org/ 前缀应被剥离"


async def test_add_paper_backfills_doi_for_existing_title_track(session):
    """同一文献先无 DOI 后有 DOI：回填旧行，不新建第二行。"""
    from sqlalchemy import func, select

    from app.models import Paper
    from app.repositories.library import add_paper

    p1 = await add_paper(session, {"title": "Dual Track Paper", "year": 2023})
    old_key = p1.dedup_key

    p2 = await add_paper(
        session,
        {"title": "Dual Track Paper", "doi": "https://doi.org/10.1/dual", "abstract": "abs"},
    )
    count = (await session.execute(select(func.count()).select_from(Paper))).scalar_one()

    assert p2.id == p1.id
    assert count == 1
    assert p2.doi == "https://doi.org/10.1/dual"
    assert p2.dedup_key == "doi:10.1/dual"
    assert p2.dedup_key != old_key
    assert p2.abstract == "abs"


async def test_add_paper_same_title_different_doi_creates_two_rows(session):
    """旧记录已有不同 DOI 时，同标题不同 DOI 仍按不同文献入库。"""
    from sqlalchemy import func, select

    from app.models import Paper
    from app.repositories.library import add_paper

    p1 = await add_paper(session, {"title": "Same Title", "doi": "10.1/one"})
    p2 = await add_paper(session, {"title": "Same Title", "doi": "10.1/two"})
    count = (await session.execute(select(func.count()).select_from(Paper))).scalar_one()

    assert p2.id != p1.id
    assert count == 2
