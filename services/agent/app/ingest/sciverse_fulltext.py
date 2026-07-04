"""Sciverse 全文拉取与落库辅助。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..errors import ApiError
from ..models import Attachment, PaperExternalId, ProjectPaper
from ..repositories import library as lib_repo
from ..repositories import project as project_repo
from ..sciverse import SciverseClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SciverseStoredContent:
    paper_id: int
    doc_id: str
    attachment_id: int
    chars: int
    sha256: str


@dataclass(frozen=True)
class SciverseBackfillCandidate:
    paper_id: int
    doc_id: str


_RETRY_429_DELAYS = (2.0, 4.0, 8.0)  # /content 429 限流退避；生产实测连拉多篇必撞限流


async def _content_with_retry(
    client: SciverseClient,
    doc_id: str,
    offset: int | None,
) -> dict:
    """调 /content，429 限流时指数退避重试（其余错误原样抛出）。"""
    last_exc: ApiError | None = None
    for attempt, delay in enumerate((0.0, *_RETRY_429_DELAYS)):
        if delay:
            await asyncio.sleep(delay)
        try:
            if offset is None:
                # 首次不传 offset：Sciverse 未传时直接返回全文（一次拿全，避免分页连发触发 429）
                return await client.content(doc_id)
            return await client.content(
                doc_id, offset=offset, limit=settings.sciverse_content_chunk_chars)
        except ApiError as exc:
            if exc.status_code != 429:
                raise
            last_exc = exc
            logger.info("[sciverse_fulltext] /content 429 限流，第 %d 次退避重试", attempt + 1)
    assert last_exc is not None
    raise last_exc


async def fetch_sciverse_markdown(
    client: SciverseClient,
    doc_id: str,
    *,
    max_chars: int | None = None,
) -> str:
    """按 doc_id 拉取 Sciverse /content 全文（首次整取，超长再分页续传）。"""
    doc_id = (doc_id or "").strip()
    if not doc_id:
        raise ApiError(422, "SCIVERSE_DOC_ID_MISSING", "该文献没有可用的 Sciverse doc_id")

    chunks: list[str] = []
    offset: int | None = None
    limit_chars = max_chars or settings.sciverse_content_max_chars
    while True:
        part = await _content_with_retry(client, doc_id, offset)
        text = str(part.get("text") or "")
        if text:
            chunks.append(text)
        if not part.get("more"):
            break
        next_offset = part.get("next_offset")
        # next_offset 不前进时必须终止：上游异常返回 more=true 且 offset 停滞会造成死循环
        if next_offset is None or int(next_offset) <= (offset or 0):
            break
        offset = int(next_offset)
        if sum(len(c) for c in chunks) >= limit_chars:
            break

    markdown = "\n\n".join(chunks).strip()
    if not markdown:
        raise ApiError(404, "SCIVERSE_CONTENT_EMPTY", "Sciverse 未返回可保存的全文文本")
    return markdown


async def _doc_id_for_paper(s: AsyncSession, paper_id: int, explicit_doc_id: str | None) -> str:
    doc_id = (explicit_doc_id or "").strip()
    if doc_id:
        return doc_id
    ids = await lib_repo.list_external_ids(
        s,
        paper_id,
        provider="sciverse",
        id_type="doc_id",
    )
    if ids:
        return ids[0].external_id
    raise ApiError(422, "SCIVERSE_DOC_ID_MISSING", "该文献没有可用的 Sciverse doc_id")


def _sciverse_markdown_path(paper_id: int, sha256: str, markdown: str) -> Path:
    out_dir = Path(settings.corpora_dir) / "sciverse" / str(paper_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{sha256}.md"
    md_path.write_text(markdown, encoding="utf-8")
    return md_path


async def store_sciverse_markdown(
    s: AsyncSession,
    *,
    paper_id: int,
    doc_id: str,
    markdown: str,
) -> SciverseStoredContent:
    """把 Sciverse markdown 存盘、写 Attachment，并补 DocumentStructure。"""
    content = markdown.encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    md_path = _sciverse_markdown_path(paper_id, sha, markdown)

    att = Attachment(
        paper_id=paper_id,
        path=str(md_path),
        url=f"sciverse://content/{doc_id}",
        content_type="text/markdown",
        sha256=sha,
        mineru_status="done",
        markdown_path=str(md_path),
    )
    s.add(att)
    await s.flush()
    attachment_id = att.id
    await s.commit()

    await lib_repo.upsert_external_ids(
        s,
        paper_id,
        [{
            "provider": "sciverse",
            "id_type": "doc_id",
            "external_id": doc_id,
            "url": f"sciverse://content/{doc_id}",
        }],
    )

    # Sciverse /content 是纯文本来源；据 markdown 合成 content_list，保证证据可定位到段落。
    try:
        from ..ingest.fulltext import _upsert_document_structure
        from ..structure.blocks import markdown_to_content_list

        content_list = markdown_to_content_list(markdown)
        if content_list:
            await _upsert_document_structure(s, attachment_id, sha, markdown, content_list)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sciverse 结构合成落库失败(不阻断): attachment_id=%s: %r", attachment_id, exc)
        await s.rollback()

    saved = (await s.execute(select(Attachment).where(Attachment.id == attachment_id))).scalar_one()
    return SciverseStoredContent(
        paper_id=paper_id,
        doc_id=doc_id,
        attachment_id=saved.id,
        chars=len(markdown),
        sha256=sha,
    )


async def fetch_and_store_sciverse_content(
    s: AsyncSession,
    *,
    project_id: int,
    paper_id: int,
    client: SciverseClient,
    doc_id: str | None = None,
    max_chars: int | None = None,
) -> SciverseStoredContent:
    """校验项目关联 → 拉取 Sciverse 全文 → 落库。"""
    pp = await project_repo.find_project_paper(s, project_id, paper_id)
    if pp is None:
        raise ApiError(404, "PROJECT_PAPER_NOT_FOUND", f"文献 {paper_id} 未关联到项目 {project_id}")

    resolved_doc_id = await _doc_id_for_paper(s, paper_id, doc_id)
    markdown = await fetch_sciverse_markdown(client, resolved_doc_id, max_chars=max_chars)
    return await store_sciverse_markdown(
        s,
        paper_id=paper_id,
        doc_id=resolved_doc_id,
        markdown=markdown,
    )


async def select_sciverse_backfill_candidates(
    s: AsyncSession,
    *,
    project_id: int,
    paper_ids: list[int] | None = None,
    exclude_paper_ids: list[int] | None = None,
) -> list[SciverseBackfillCandidate]:
    """选出项目内有 Sciverse doc_id 且尚无 markdown 附件的论文。"""
    has_markdown = exists().where(
        Attachment.paper_id == ProjectPaper.paper_id,
        Attachment.markdown_path.isnot(None),
        Attachment.markdown_path != "",
    )
    q = (
        select(ProjectPaper.paper_id, PaperExternalId.external_id)
        .join(PaperExternalId, PaperExternalId.paper_id == ProjectPaper.paper_id)
        .where(
            ProjectPaper.project_id == project_id,
            PaperExternalId.provider == "sciverse",
            PaperExternalId.id_type == "doc_id",
            ~has_markdown,
        )
        .order_by(ProjectPaper.order.asc(), ProjectPaper.id.asc(), PaperExternalId.id.asc())
    )
    if paper_ids:
        q = q.where(ProjectPaper.paper_id.in_([int(pid) for pid in paper_ids]))
    if exclude_paper_ids:
        q = q.where(ProjectPaper.paper_id.notin_([int(pid) for pid in exclude_paper_ids]))

    rows = (await s.execute(q)).all()
    candidates: list[SciverseBackfillCandidate] = []
    seen: set[int] = set()
    for paper_id, doc_id in rows:
        if paper_id in seen:
            continue
        doc_id_text = str(doc_id or "").strip()
        if not doc_id_text:
            continue
        candidates.append(SciverseBackfillCandidate(paper_id=int(paper_id), doc_id=doc_id_text))
        seen.add(int(paper_id))
    return candidates
