"""P1 gap 可观测测试。

验收（docs/plans/2026-07-05 v2 · P1）：
  1. build_child_context 上下文隔离（codex P0-3）：剔除 state/messages/pending_round/
     all_tool_results，保留合法执行依赖 + 注入 depth/skill_id。
  2. _GapEmitter（codex P0-2）：单调 seq + 落 AiJob.events_json + 发布到 gap 频道；单写锁串行。
  3. _SubagentPublisher（codex P0-2）：子事件包成 subagent_event(child_type)，child error
     绝不裸发 error（不误关父流）；噪声(run_start/llm_start)不转发。
  4. summarize_papers on_progress：每篇完成回调一次 (done,total)。
  5. gap SSE 端点：补发 events_json 历史（Last-Event-ID 去重）+ 终态关流。
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agent.dispatch import _CHILD_CONTEXT_DENY, build_child_context
from app.repositories import ai_job as ai_job_repo
from app.repositories.project import create_project
from app.routes_research import _GapEmitter, _SubagentPublisher, gap_channel


# ======================================================================
# 1. build_child_context 上下文隔离（codex P0-3）
# ======================================================================

def test_child_context_drops_parent_session_state():
    base = {
        "session_factory": "SF", "project_id": 7, "scratchpad": "PAD",
        "paper_summaries": [1, 2], "topic": "t", "emit": "E", "gap": {"gap_id": "g1"},
        # 危险键：父交互 run 的会话态，绝不能泄漏
        "state": {"messages": ["secret"]}, "messages": ["m"],
        "pending_round": {"x": 1}, "all_tool_results": [{"r": 1}],
    }
    child = build_child_context(base, child_depth=1, skill_id="gap-finder")
    # 危险键全部剔除
    for k in _CHILD_CONTEXT_DENY:
        assert k not in child, f"{k} 泄漏进 child_context"
    # 合法执行依赖保留
    for k in ("session_factory", "project_id", "scratchpad", "paper_summaries",
              "topic", "emit", "gap"):
        assert child[k] == base[k]
    # 注入 depth/skill_id
    assert child["depth"] == 1 and child["skill_id"] == "gap-finder"


def test_child_context_none_base():
    child = build_child_context(None, 1, "value-evidence")
    assert child == {"depth": 1, "skill_id": "value-evidence"}


# ======================================================================
# 辅助
# ======================================================================

class _FakePublisher:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel: str, event: dict) -> None:
        self.published.append((channel, event))


async def _new_project(session_factory, name: str) -> int:
    async with session_factory() as s:
        proj = await create_project(s, {"name": name})
        return proj.id


# ======================================================================
# 2. _GapEmitter（codex P0-2 单写锁 + seq + 落库 + 发布）
# ======================================================================

@pytest.mark.asyncio
async def test_gap_emitter_seq_persist_publish(session_factory):
    pid = await _new_project(session_factory, "gapemit")
    async with session_factory() as s:
        job = await ai_job_repo.create_job(
            s, project_id=pid, kind="gap_discover", corpus_id="c1", request_json={})
        job_id = job.id

    pub = _FakePublisher()
    em = _GapEmitter(pub, session_factory, pid, job_id)
    await em.emit({"type": "started"})
    await em.emit({"type": "summarizing", "done": 1, "total": 3})
    await em.emit({"type": "done", "gaps": 2})

    # 发布到正确频道 + 单调 seq 1,2,3
    assert [c for c, _ in pub.published] == [gap_channel(job_id)] * 3
    assert [e["seq"] for _, e in pub.published] == [1, 2, 3]
    assert pub.published[0][1]["type"] == "started"

    # events_json 落库（权威历史，供 SSE 重连补发），seq 一致
    async with session_factory() as s:
        job2 = await ai_job_repo.get_job(s, pid, job_id)
    evs = job2.events_json or []
    assert [e["seq"] for e in evs] == [1, 2, 3]
    assert evs[1]["type"] == "summarizing" and evs[1]["total"] == 3


@pytest.mark.asyncio
async def test_gap_emitter_concurrent_no_seq_collision(session_factory):
    """并发 emit（模拟并发 subagent 回传）单写锁下 seq 无撞、无丢。"""
    pid = await _new_project(session_factory, "gapemit-conc")
    async with session_factory() as s:
        job = await ai_job_repo.create_job(
            s, project_id=pid, kind="gap_verify", corpus_id=None, request_json={})
        job_id = job.id
    pub = _FakePublisher()
    em = _GapEmitter(pub, session_factory, pid, job_id)
    await asyncio.gather(*[em.emit({"type": "subagent_event", "i": i}) for i in range(20)])
    seqs = sorted(e["seq"] for _, e in pub.published)
    assert seqs == list(range(1, 21))  # 1..20 无撞无丢


# ======================================================================
# 3. _SubagentPublisher（codex P0-2 事件包装，child 终态不误关父流）
# ======================================================================

class _RecEmitter:
    def __init__(self):
        self.events: list[dict] = []

    async def emit(self, ev: dict) -> None:
        self.events.append(ev)


@pytest.mark.asyncio
async def test_subagent_publisher_wraps_and_filters():
    rec = _RecEmitter()
    sp = _SubagentPublisher(rec, "gap-finder")
    # 噪声不转发
    await sp.publish("run:1:events", {"type": "run_start"})
    await sp.publish("run:1:events", {"type": "llm_start"})
    # tools_start 转发并保留 tool_calls
    await sp.publish("run:1:events", {"type": "tools_start", "round": 2,
                                      "tool_calls": [{"name": "scratchpad__add", "args_preview": "{}"}]})
    # child error 包成 subagent_event（child_type=error），绝不裸发 error
    await sp.publish("run:1:events", {"type": "error", "error": "boom"})
    # child run_complete 也包壳（不作父终态）
    await sp.publish("run:1:events", {"type": "run_complete", "status": "done"})

    types = [e["type"] for e in rec.events]
    assert types == ["subagent_event"] * 3  # 只有 tools_start/error/run_complete 转发
    assert all(e["type"] == "subagent_event" for e in rec.events)
    # 绝不出现裸 error/run_complete（否则父 SSE 会误当终态关流）
    assert not any(e["type"] in ("error", "run_complete") for e in rec.events)
    child_types = [e["child_type"] for e in rec.events]
    assert child_types == ["tools_start", "error", "run_complete"]
    err_ev = next(e for e in rec.events if e["child_type"] == "error")
    assert err_ev["child_error"] == "boom"
    ts_ev = next(e for e in rec.events if e["child_type"] == "tools_start")
    assert ts_ev["tool_calls"][0]["name"] == "scratchpad__add"


# ======================================================================
# 4. summarize_papers on_progress
# ======================================================================

@pytest.mark.asyncio
async def test_summarize_papers_on_progress(monkeypatch):
    from app.review import read as read_mod
    from app.review.read import PaperSummary, summarize_papers

    async def _fake_summarize_paper(*, markdown, meta, topic, content_list=None, override=None):
        return PaperSummary(paper_id=str(meta.get("paper_id")), title="t")

    monkeypatch.setattr(read_mod, "summarize_paper", _fake_summarize_paper)
    papers = [{"paper_id": i, "markdown": "x"} for i in range(4)]
    seen: list[tuple[int, int]] = []

    async def _prog(done, total):
        seen.append((done, total))

    out = await summarize_papers(papers, "topic", concurrency=2, on_progress=_prog)
    assert len(out) == 4
    # 每篇完成回调一次；total 恒为 4；done 覆盖 1..4（并发下顺序不定，用集合断言）
    assert len(seen) == 4
    assert {d for d, _ in seen} == {1, 2, 3, 4}
    assert all(t == 4 for _, t in seen)


# ======================================================================
# 5. gap SSE 端点：补发 events_json 历史 + 终态关流
# ======================================================================

@pytest.mark.asyncio
async def test_gap_sse_replays_history_and_closes_on_terminal(session_factory, fake_r):
    import httpx
    import pytest_asyncio  # noqa: F401 — 确保插件已装

    from app.db import get_session
    from app.harness.events import SubscribableEventPublisher
    from app.main import app, get_r_client

    pid = await _new_project(session_factory, "gapsse")
    # 建一条已完成的 gap job，events_json 含 started/summarizing/done_empty（终态）
    async with session_factory() as s:
        job = await ai_job_repo.create_job(
            s, project_id=pid, kind="gap_discover", corpus_id="c1", request_json={})
        await ai_job_repo.update_job(s, job, append_event={"type": "started", "seq": 1})
        await ai_job_repo.update_job(
            s, job, append_event={"type": "summarizing", "done": 2, "total": 2, "seq": 2})
        await ai_job_repo.update_job(
            s, job, append_event={"type": "done_empty", "gaps": 0, "seq": 3})
        job_id = job.id

    # SSE 端点读 app.state.publisher；测试环境未跑 lifespan，手动装一个
    app.state.publisher = SubscribableEventPublisher()

    async def _test_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_r_client] = lambda: fake_r
    app.dependency_overrides[get_session] = _test_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(f"/projects/{pid}/gaps/runs/{job_id}/events")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            body = r.text
        # 补发三条历史事件，且带终态 done_empty（流随即关闭）
        assert "event: started" in body
        assert "event: summarizing" in body
        assert "event: done_empty" in body
        assert "id: 3" in body  # Last-Event-ID 断点续传用
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_gap_sse_synthesizes_terminal_from_status(session_factory, fake_r):
    """codex P1：events_json 无终态但 job.status 已终态（emit 终态落库失败/竞态）→
    端点据 status 合成终态关流，绝不让已结束 run 让客户端永等 heartbeat。"""
    import httpx

    from app.db import get_session
    from app.harness.events import SubscribableEventPublisher
    from app.main import app, get_r_client

    pid = await _new_project(session_factory, "gapsse-synth")
    async with session_factory() as s:
        job = await ai_job_repo.create_job(
            s, project_id=pid, kind="gap_discover", corpus_id="c1", request_json={})
        # 只落了非终态事件（模拟终态 append 失败），但 job 已被置 done
        await ai_job_repo.update_job(s, job, append_event={"type": "started", "seq": 1})
        await ai_job_repo.update_job(
            s, job, append_event={"type": "summarizing", "done": 1, "total": 1, "seq": 2})
        await ai_job_repo.update_job(s, job, status="done", complete=True)
        job_id = job.id

    app.state.publisher = SubscribableEventPublisher()

    async def _test_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_r_client] = lambda: fake_r
    app.dependency_overrides[get_session] = _test_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(f"/projects/{pid}/gaps/runs/{job_id}/events")
            assert r.status_code == 200
            body = r.text
        assert "event: started" in body
        assert "event: summarizing" in body
        assert "event: done" in body  # 合成终态
        assert "synthesized" in body
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_gap_sse_404_unknown_run(session_factory, fake_r):
    import httpx

    from app.db import get_session
    from app.harness.events import SubscribableEventPublisher
    from app.main import app, get_r_client

    pid = await _new_project(session_factory, "gapsse404")
    app.state.publisher = SubscribableEventPublisher()

    async def _test_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_r_client] = lambda: fake_r
    app.dependency_overrides[get_session] = _test_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(f"/projects/{pid}/gaps/runs/999999/events")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
