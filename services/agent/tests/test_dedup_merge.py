"""Paper 双轨去重存量合并测试。"""

from sqlalchemy import func, select

from app.models import (
    Attachment,
    Corpus,
    CorpusPaper,
    Note,
    Paper,
    PaperExternalId,
    PaperExtraction,
    PaperTag,
    Project,
    ProjectPaper,
    Tag,
)
from app.repositories.dedup_merge import merge_duplicate_papers, plan_paper_dedup_merges
from app.repositories.library import compute_dedup_key


async def test_merge_duplicate_papers_repoints_references_and_conflicts(session):
    """存量双轨重复：合并成一行，引用表重指向，唯一约束冲突不报错。"""
    target = Paper(
        title="Dual Track Stored Paper",
        dedup_key=compute_dedup_key({"title": "Dual Track Stored Paper"}),
        doi=None,
        year=None,
        abstract=None,
    )
    source = Paper(
        title="dual track stored paper",
        dedup_key=compute_dedup_key({"title": "dual track stored paper", "doi": "10.1/stored"}),
        doi="10.1/stored",
        year=2024,
        abstract="source abstract",
    )
    session.add_all([target, source])
    await session.flush()
    target_id = target.id
    source_id = source.id

    dup_tag = Tag(name="dedup-conflict")
    move_tag = Tag(name="dedup-move")
    project = Project(name="Dedup Project")
    session.add_all([dup_tag, move_tag, project])
    await session.flush()
    project_id = project.id

    corpus_conflict = Corpus(project_id=project_id, content_hash="corpus-conflict")
    corpus_move = Corpus(project_id=project_id, content_hash="corpus-move")
    session.add_all([corpus_conflict, corpus_move])
    await session.flush()
    session.add_all([
        PaperTag(paper_id=target_id, tag_id=dup_tag.id),
        PaperTag(paper_id=source_id, tag_id=dup_tag.id),
        PaperTag(paper_id=source_id, tag_id=move_tag.id),
        Note(paper_id=source_id, body="source note"),
        Attachment(paper_id=source_id, path="/tmp/source.pdf"),
        ProjectPaper(project_id=project_id, paper_id=target_id, inclusion_status="candidate", order=9),
        ProjectPaper(
            project_id=project_id,
            paper_id=source_id,
            inclusion_status="included",
            screening_score=8,
            screening_notes="source screening",
            order=3,
        ),
        CorpusPaper(
            corpus_id=corpus_conflict.id,
            paper_id=target_id,
            inclusion_status_snapshot="included",
            record_hash="target-hash",
        ),
        CorpusPaper(
            corpus_id=corpus_conflict.id,
            paper_id=source_id,
            inclusion_status_snapshot="included",
            record_hash="source-hash",
        ),
        CorpusPaper(
            corpus_id=corpus_move.id,
            paper_id=source_id,
            inclusion_status_snapshot="included",
            record_hash="move-hash",
        ),
        PaperExtraction(paper_id=target_id, research_question="target rq"),
        PaperExtraction(paper_id=source_id, method="source method", raw={"from": "source"}),
        PaperExternalId(
            paper_id=target_id,
            provider="openalex",
            id_type="work",
            external_id="W1",
        ),
        PaperExternalId(
            paper_id=source_id,
            provider="openalex",
            id_type="work",
            external_id="W1",
        ),
        PaperExternalId(
            paper_id=source_id,
            provider="doi",
            id_type="doi",
            external_id="10.1/stored",
        ),
    ])
    await session.commit()

    dry_report = await session.run_sync(
        lambda sync_session: merge_duplicate_papers(sync_session.connection(), dry_run=True)
    )
    paper_count = (await session.execute(select(func.count()).select_from(Paper))).scalar_one()
    assert dry_report["merge_count"] == 1
    assert paper_count == 2

    report = await session.run_sync(
        lambda sync_session: merge_duplicate_papers(sync_session.connection())
    )
    await session.commit()
    session.expire_all()

    assert report["merge_count"] == 1
    assert (await session.execute(select(func.count()).select_from(Paper))).scalar_one() == 1

    merged = await session.get(Paper, target_id)
    assert merged is not None
    assert merged.doi == "10.1/stored"
    assert merged.dedup_key == "doi:10.1/stored"
    assert merged.year == 2024
    assert merged.abstract == "source abstract"
    assert await session.get(Paper, source_id) is None

    assert (await session.execute(
        select(func.count()).select_from(PaperTag).where(PaperTag.paper_id == target_id)
    )).scalar_one() == 2
    assert (await session.execute(
        select(func.count()).select_from(Note).where(Note.paper_id == target_id)
    )).scalar_one() == 1
    assert (await session.execute(
        select(func.count()).select_from(Attachment).where(Attachment.paper_id == target_id)
    )).scalar_one() == 1

    pp = (await session.execute(
        select(ProjectPaper).where(ProjectPaper.project_id == project_id)
    )).scalar_one()
    assert pp.paper_id == target_id
    assert pp.inclusion_status == "included"
    assert pp.screening_score == 8
    assert pp.screening_notes == "source screening"
    assert pp.order == 3

    corpus_rows = (await session.execute(
        select(CorpusPaper).order_by(CorpusPaper.corpus_id)
    )).scalars().all()
    assert len(corpus_rows) == 2
    assert {row.paper_id for row in corpus_rows} == {target_id}

    extraction = (await session.execute(
        select(PaperExtraction).where(PaperExtraction.paper_id == target_id)
    )).scalar_one()
    assert extraction.research_question == "target rq"
    assert extraction.method == "source method"

    external_ids = (await session.execute(
        select(PaperExternalId.external_id).where(PaperExternalId.paper_id == target_id)
    )).scalars().all()
    assert sorted(external_ids) == ["10.1/stored", "W1"]


def test_plan_paper_dedup_merges_skips_ambiguous_doi():
    """同标题多个不同 DOI 时跳过，避免把不同文献误合并。"""
    papers = [
        {"id": 1, "owner_id": None, "title": "Ambiguous", "doi": None, "dedup_key": "title:x"},
        {"id": 2, "owner_id": None, "title": "Ambiguous", "doi": "10.1/a", "dedup_key": "doi:10.1/a"},
        {"id": 3, "owner_id": None, "title": "Ambiguous", "doi": "10.1/b", "dedup_key": "doi:10.1/b"},
    ]

    plan = plan_paper_dedup_merges(papers)

    assert plan["merges"] == []
    assert plan["skipped"][0]["reason"] == "ambiguous_doi"


def test_plan_paper_dedup_merges_skips_outside_dedup_key_conflict():
    """组外行已持有目标 doi: dedup_key 时跳过，避免升级撞 uq_paper_dedup。"""
    papers = [
        # 待合并组：无 DOI 标题轨 + DOI 轨
        {"id": 1, "owner_id": None, "title": "Conflict Case", "doi": None, "dedup_key": "title:c"},
        {"id": 2, "owner_id": None, "title": "Conflict Case", "doi": "10.1/c", "dedup_key": "doi:x-old"},
        # 组外行：标题规范化不同，但已持有目标 doi:10.1/c key
        {"id": 3, "owner_id": None, "title": "Conflict Case (Extended)", "doi": "10.1/c", "dedup_key": "doi:10.1/c"},
    ]

    plan = plan_paper_dedup_merges(papers)

    assert plan["merges"] == []
    conflict = [s for s in plan["skipped"] if s["reason"] == "dedup_key_conflict"]
    assert conflict and conflict[0]["conflicting_paper_ids"] == [3]
