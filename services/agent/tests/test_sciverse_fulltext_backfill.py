from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app import main as app_main
from app.config import settings
from app.db import get_session
from app.errors import ApiError
from app.main import get_r_client
from app.models import Attachment, DocumentStructure, Paper, PaperExternalId, ProjectPaper
from app.repositories.project import create_project


@pytest_asyncio.fixture
async def aclient(session_factory, fake_r):
    async def _test_session():
        async with session_factory() as s:
            yield s

    app_main.app.dependency_overrides[get_r_client] = lambda: fake_r
    app_main.app.dependency_overrides[get_session] = _test_session
    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, session_factory
    app_main.app.dependency_overrides.clear()


class FakeSciverseClient:
    def __init__(self):
        self.calls: list[tuple[str, int | None]] = []

    async def content(self, doc_id: str, offset: int | None = None, limit: int | None = None):
        self.calls.append((doc_id, offset))
        if doc_id == "doc-fail":
            raise ApiError(503, "SCIVERSE_UNAVAILABLE", "mock timeout")
        if doc_id == "doc-page" and offset == 0:
            return {"text": "# Sciverse Paper\n\nPart one", "more": True, "next_offset": 10}
        return {"text": "Part two", "more": False}


async def _new_project(factory) -> int:
    async with factory() as s:
        proj = await create_project(s, {"name": "Sciverse Backfill"})
        return proj.id


async def _seed_paper(factory, project_id: int, title: str, *, doc_id: str | None = None,
                      has_markdown: bool = False) -> int:
    async with factory() as s:
        paper = Paper(title=title, dedup_key=f"title:{title}", source="sciverse")
        s.add(paper)
        await s.flush()
        s.add(ProjectPaper(project_id=project_id, paper_id=paper.id, inclusion_status="candidate"))
        if doc_id:
            s.add(PaperExternalId(
                paper_id=paper.id,
                provider="sciverse",
                id_type="doc_id",
                external_id=doc_id,
            ))
        if has_markdown:
            s.add(Attachment(
                paper_id=paper.id,
                mineru_status="done",
                markdown_path="/tmp/existing.md",
                sha256="a" * 64,
            ))
        await s.commit()
        return paper.id


@pytest.mark.asyncio
async def test_backfill_fetches_eligible_papers_and_isolates_failures(aclient, monkeypatch, tmp_path):
    c, factory = aclient
    pid = await _new_project(factory)
    p_ok = await _seed_paper(factory, pid, "Needs fulltext", doc_id="doc-page")
    p_fail = await _seed_paper(factory, pid, "Will fail", doc_id="doc-fail")
    p_existing = await _seed_paper(factory, pid, "Already has markdown", doc_id="doc-existing", has_markdown=True)
    await _seed_paper(factory, pid, "No doc id")

    fake = FakeSciverseClient()
    monkeypatch.setattr(settings, "corpora_dir", str(tmp_path))
    monkeypatch.setattr(app_main, "_sciverse_client", lambda request, body=None: fake)

    r = await c.post(f"/projects/{pid}/papers/fulltext:backfill", json={"maxPapers": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["fetched"] == 1
    assert body["remaining"] == 0
    assert body["skipped"] == 0
    assert body["failed"] == [{"paperId": p_fail, "reason": "mock timeout"}]

    async with factory() as s:
        ok_atts = list((await s.execute(
            select(Attachment).where(Attachment.paper_id == p_ok)
        )).scalars().all())
        fail_atts = list((await s.execute(
            select(Attachment).where(Attachment.paper_id == p_fail)
        )).scalars().all())
        existing_atts = list((await s.execute(
            select(Attachment).where(Attachment.paper_id == p_existing)
        )).scalars().all())
        ds = (await s.execute(
            select(DocumentStructure).where(DocumentStructure.attachment_id == ok_atts[-1].id)
        )).scalar_one_or_none()

    assert len(ok_atts) == 1
    assert ok_atts[0].content_type == "text/markdown"
    assert "sciverse" in ok_atts[0].markdown_path
    assert ds is not None
    assert fail_atts == []
    assert len(existing_atts) == 1


@pytest.mark.asyncio
async def test_backfill_reports_remaining_when_limited(aclient, monkeypatch, tmp_path):
    c, factory = aclient
    pid = await _new_project(factory)
    await _seed_paper(factory, pid, "A", doc_id="doc-a")
    await _seed_paper(factory, pid, "B", doc_id="doc-b")

    monkeypatch.setattr(settings, "corpora_dir", str(tmp_path))
    monkeypatch.setattr(app_main, "_sciverse_client", lambda request, body=None: FakeSciverseClient())

    r = await c.post(f"/projects/{pid}/papers/fulltext:backfill", json={"maxPapers": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["fetched"] == 1
    assert body["skipped"] == 1
    assert body["remaining"] == 1


@pytest.mark.asyncio
async def test_backfill_returns_clear_400_when_sciverse_unconfigured(aclient, monkeypatch):
    c, factory = aclient
    pid = await _new_project(factory)
    monkeypatch.setattr(settings, "sciverse_api_token", "")

    r = await c.post(f"/projects/{pid}/papers/fulltext:backfill", json={})
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "SCIVERSE_NOT_CONFIGURED"
    assert "Sciverse API Token 未配置" in body["message"]

