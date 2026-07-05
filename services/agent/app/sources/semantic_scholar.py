"""Semantic Scholar 检索源 (net-room)。随缘源：无 key 易被 429 限流。

有 SEMANTIC_SCHOLAR_API_KEY 走 x-api-key；无 key 也尝试 (可能 429，作为 error 回传，
不静默 return [])。openAccessPdf 提供 OA 直链。
"""
from __future__ import annotations

import asyncio
import logging
import time

from ..config import settings
from ..sciverse import normalize_meta_result
from .base import HttpSource, SourceOutcome

logger = logging.getLogger("agent.sources.semantic")

_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

# 进程内请求节流：Semantic Scholar 认证限速约 1 req/s，并发 fan-out (multi_source_search
# 同时打多源) + Agent 多轮检索会突发触发 429。用全局锁 + 上次请求时刻，把 semantic 请求
# 串行化并按 min_interval 间隔，从源头避免 429 (对齐朋友 SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS)。
_throttle_lock = asyncio.Lock()
_last_request_ts = 0.0


async def _throttle() -> None:
    global _last_request_ts
    interval = float(settings.semantic_scholar_min_interval_seconds or 0)
    if interval <= 0:
        return
    async with _throttle_lock:
        wait = _last_request_ts + interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_ts = time.monotonic()
_FIELDS = "title,abstract,year,publicationDate,authors,externalIds,openAccessPdf,venue,citationCount"


def map_paper(row: dict) -> dict:
    authors = [
        a.get("name")
        for a in (row.get("authors") or [])
        if isinstance(a, dict) and a.get("name")
    ]
    external = row.get("externalIds") or {}
    doi = (external.get("DOI") or "").strip() or None
    pdf = (row.get("openAccessPdf") or {}).get("url")
    return {
        "title": row.get("title"),
        "doi": doi,
        "abstract": row.get("abstract"),
        "author": authors,
        "publication_published_year": row.get("year"),
        "publication_published_date": row.get("publicationDate"),
        "publication_venue_name_unified": row.get("venue"),
        "citation_count": row.get("citationCount"),
        "source_id": row.get("paperId"),
        "source_id_type": "s2_paper_id",
        "url": f"https://www.semanticscholar.org/paper/{row.get('paperId')}" if row.get("paperId") else None,
        "pdf_url": pdf,
    }


class SemanticScholarSource(HttpSource):
    source = "semantic"

    def configured(self) -> tuple[bool, str | None]:
        # 无 key 仍可尝试 (免鉴权但强限流)；标注为可用但提示随缘。
        return True, None

    async def search(self, query: str, *, limit: int, since: str | None = None) -> SourceOutcome:
        params = {"query": query, "limit": str(max(1, min(100, limit))), "fields": _FIELDS}
        if since:
            year = str(since)[:4]
            if year.isdigit():
                params["year"] = f"{year}-"
        headers = {}
        key = (settings.semantic_scholar_api_key or "").strip()
        if key:
            headers["x-api-key"] = key
        await _throttle()  # 请求前节流，串行化 + 按 min_interval 间隔，从源头避免 429
        try:
            status, body = await self._get_json(_SEARCH_URL, params=params, headers=headers or None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[semantic] 请求异常: %s", exc)
            return SourceOutcome(self.source, available=True, error=str(exc))
        if status == 429:
            # 有 key 仍 429 = 节流不足/短时高并发；无 key = 未鉴权强限流。文案区分，避免误导。
            hint = "已配 key，短时并发过高，可调大 SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS" if key else "建议配置 SEMANTIC_SCHOLAR_API_KEY"
            return SourceOutcome(self.source, available=True, error=f"Semantic Scholar 限流 (429)，{hint}")
        if status >= 400 or not isinstance(body, dict):
            return SourceOutcome(self.source, available=True, error=f"Semantic Scholar HTTP {status}")
        results = body.get("data") or []
        candidates = [
            normalize_meta_result(map_paper(r), self.source)
            for r in results
            if isinstance(r, dict) and (r.get("title") or "").strip()
        ]
        return SourceOutcome(self.source, available=True, candidates=candidates, total=body.get("total"))
