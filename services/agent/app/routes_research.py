"""A5 · 研究副驾路由 — GAP 发现 / 价值二次验证 / HITL（契约 §2.1 + §2.4）。

5 endpoint（均 HITL：裁决浮现给人，不自动定稿）：
  POST  /projects/{pid}/corpus/{cid}/gaps:discover   → 202 {run_id}   异步 gap 发现
  GET   /projects/{pid}/agent/runs/{rid}/scratchpad   → ScratchpadState（实时 HITL 视图）
  POST  /projects/{pid}/gaps/{gap_id}:verify          → 202 {verify_run_id} 异步价值核验
  GET   /projects/{pid}/gaps/{gap_id}/verdict         → GapVerdictResult（裁决 + 证据包）
  PATCH /projects/{pid}/gaps/{gap_id}                 → GapCandidate（accept/reject/revise）

异步走 AiJob + BackgroundTasks（run_id = str(ai_job.id)，与 gap_candidate.run_id 对齐）。
分层铁律：LLM 攒证 / 确定性 resolver 裁决（decided_by=deterministic）。领域无关（§0.3）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent.dispatch import OUTCOME_OK
from .agent.registry_factory import build_registry
from .agent.scratchpad import DbScratchpadStore
from .harness.llm import LLMRouter
from .db import SessionLocal, get_session
from .errors import ApiError
from .repositories import ai_job as ai_job_repo
from .repositories import gaps as gaps_repo
from .run_status import normalize_run_status
from .repositories import project as project_repo
from .review.feasibility_check import FeasibilityCheckError, verify_gap_feasibility
from .review.gap_discover import discover_gaps
from .review.load import has_readable_fulltext, load_project_corpus, project_fulltext_diagnostics
from .review.read import summarize_papers
from .review.value_check import ValueCheckError, verify_gap_value

logger = logging.getLogger("agent.routes_research")

router = APIRouter(tags=["research"])

# 路径段白名单（§2.4-4）：禁 `:` `/` 等，避免与 AIP 自定义方法 :discover/:verify 路由歧义。
_SEG = r"^[A-Za-z0-9._-]+$"


# ======================================================================
# 请求模型
# ======================================================================

class GapDiscoverRequest(BaseModel):
    # 契约 §2.1 `gaps:discover` 无请求体（openapi requestBody?: never）；topic 可选，
    # 缺省时由 handler 从项目 research_question/name 派生，使前端「无 body」请求不再 422。
    topic: Optional[str] = None
    lens: Optional[str] = None          # 可选过滤；缺省三 lens 全开
    # codex P2: body 可缺省后, max_candidates 须收口边界 —— 否则 0/负数/过大值被接受,
    # 静默跑出无候选或异常成本。ge=1 le=50 兜住合理区间。
    max_candidates: int = Field(default=12, ge=1, le=50)


class ValueThresholdsIn(BaseModel):
    reverse_hit_high: int = 25
    reverse_hit_low: int = 3


class GapVerifyRequest(BaseModel):
    methods: Optional[list[str]] = None                 # ["reverse_search","biblio_structure"]
    thresholds: Optional[ValueThresholdsIn] = None      # 按领域可调（§0.3）


class GapFeasibilityRequest(BaseModel):
    # P2：可行性核验无必填参数；预留 config（当前状态机无阈值）。body 可缺省。
    config: Optional[dict] = None


class GapPatchRequest(BaseModel):
    """HITL 决策（§2.4-3 oneOf）：revise 强制带非空 statement；accept/reject 不带。

    oneOf 一致性在 patch_gap handler 前置校验（先于 gap 存在性），返回可预测的 422。
    """
    action: Literal["accept", "reject", "revise"]
    note: Optional[str] = None
    statement: Optional[str] = None


def _validate_patch_oneof(body: "GapPatchRequest") -> None:
    """§2.4-3 oneOf：revise 必带非空 statement；accept/reject 不应带 statement。fail-loud 422。"""
    if body.action == "revise" and not (body.statement or "").strip():
        raise ApiError(422, "VALIDATION_ERROR", "revise 必须提供非空 statement")
    if body.action != "revise" and body.statement:
        raise ApiError(422, "VALIDATION_ERROR", "accept/reject 不应带 statement")


# ======================================================================
# 序列化 / 状态映射
# ======================================================================

def _run_status(job: Any | None) -> str:
    """AiJob.status → 契约 run_status（前端停轮询信号，§2.4-2）。"""
    raw = getattr(job, "status", None)
    if raw == "error":
        return "failed"
    st = normalize_run_status(raw)
    if st == "done":
        return "done"
    if st == "failed":
        return "failed"
    return "running"


def _gap_dict(g: Any) -> dict:
    """GapCandidate 域对象 / ORM 行 → 契约 GapCandidate dict。"""
    if hasattr(g, "to_dict"):
        d = g.to_dict()
        # 域对象 to_dict 已含 feasibility 两字段（P2）；ORM 行走下面分支补齐。
        return d
    return {
        "gap_id": g.gap_id, "theme": g.theme, "statement": g.statement, "lens": g.lens,
        "supporting_papers": g.supporting_papers or [], "counter_evidence": g.counter_evidence or [],
        "confidence": g.confidence, "status": g.status, "value_verdict": g.value_verdict,
        # P2 feasibility（codex P1-3：ORM 行分支也须输出，否则 verdict/HITL 端点丢字段）。
        "feasibility_verdict": getattr(g, "feasibility_verdict", None),
        "feasibility_pack": getattr(g, "feasibility_pack", None),
    }


def _discover_job_update(result: dict) -> dict:
    """从 discover_gaps 返回值决定 job 终态（纯函数，可单测）。返回 {status, error, summary_json, event}。

    铁律（问题3 修复）：discover_gaps 对 subagent 非 ok 是「透出 outcome 不抛异常」
    （gap_discover.py 注释明示「调用方据此置 job 状态」），故必须在此显式检查 outcome——
    非 "ok" 一律置 failed，绝不静默 done。此前调用方无条件 status="done"，把 gap-finder 的
    error（如 read_paper 越界失败耗尽轮次）吞成 run_status=done + 0 条（静默吞错）。

    done-empty（codex 二审）：outcome=ok 但 0 条 = 正常跑完未发现，置 done 但标
    summary_json.empty=true + event done_empty，与「系统失败」区分（不改前端状态枚举）。
    """
    outcome = result.get("outcome")
    gaps_n = len(result.get("gaps") or [])
    if outcome != OUTCOME_OK:
        reasons = result.get("tool_failure_reasons") or []
        return {
            "status": "failed",
            "error": (f"gap-finder 未正常完成（outcome={outcome}, "
                      f"tool_failures={result.get('tool_failures')}）：{reasons[:3]}"),
            "summary_json": {"gaps": gaps_n, "outcome": outcome,
                             "tool_failures": result.get("tool_failures")},
            "event": {"type": "error", "outcome": outcome,
                      "tool_failures": result.get("tool_failures")},
        }
    empty = gaps_n == 0
    # codex review P2：done 分支也保留 tool_failures，避免 outcome=ok 但有部分工具失败时
    # 信息被丢弃（不复现主 bug，但保可观测）。
    return {
        "status": "done",
        "error": None,
        "summary_json": {"gaps": gaps_n, "outcome": outcome, "empty": empty,
                         "tool_failures": result.get("tool_failures")},
        "event": {"type": "done_empty" if empty else "done", "gaps": gaps_n,
                  "tool_failures": result.get("tool_failures")},
    }


# ======================================================================
# P1 gap 可观测：单写锁 emit（落 events_json + seq）→ 发布到 gap SSE 频道
# ======================================================================

def gap_channel(job_id: int) -> str:
    """gap job 的 SSE 频道名（与 SSE 端点约定一致）。"""
    return f"gap:{job_id}:events"


def _sse_frame(event_type: str, data: dict, seq: int | None = None) -> str:
    """格式化 SSE 帧；seq 非空时带 id 行（供 Last-Event-ID 断点续传）。"""
    id_line = f"id: {seq}\n" if seq is not None else ""
    return f"{id_line}event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# gap SSE 终态事件类型：SSE 收到即关流（与 discover/verify 终态一致）。
_GAP_TERMINAL_TYPES = {"done", "done_empty", "error"}


class _GapEmitter:
    """gap job 的单写锁 emit（codex P0-2）。

    职责：给事件分配单调 seq → 落 AiJob.events_json（重连补发的权威历史）→ 发布到
    gap:{job_id}:events 频道（实时）。用 asyncio.Lock 串行化——防并发 subagent emit
    同时 append events_json + 撞 seq（value-evidence 反向检索可能并发多路检索经子事件回传）。
    落库/发布任一失败都被隔离，绝不打断 gap 主流程（可观测是增益，不是承重）。
    """

    def __init__(self, publisher: Any, session_factory: Any, pid: int, job_id: int) -> None:
        self._publisher = publisher
        self._session_factory = session_factory
        self._pid = pid
        self._job_id = job_id
        self._channel = gap_channel(job_id)
        self._lock = asyncio.Lock()
        self._seq = 0

    async def emit(self, ev: dict) -> None:
        async with self._lock:
            self._seq += 1
            payload = {**ev, "seq": self._seq}
            try:
                async with self._session_factory() as s:
                    job = await ai_job_repo.get_job(s, self._pid, self._job_id)
                    if job is not None:
                        await ai_job_repo.update_job(s, job, append_event=payload)
            except Exception:  # noqa: BLE001 — 可观测落库失败不打断 gap 主流程
                logger.warning("[gap_emit] events_json 落库失败 job=%s（不阻断）", self._job_id)
            if self._publisher is not None:
                try:
                    await self._publisher.publish(self._channel, payload)
                except Exception:  # noqa: BLE001
                    logger.warning("[gap_emit] 发布失败 job=%s（不阻断）", self._job_id)


class _SubagentPublisher:
    """把 subagent(gap-finder / value-evidence) 子 loop 事件包成 subagent_event 转发到父 gap
    频道（codex P0-2）。

    命门：子 loop 的 autonomous_loop 会发 run_complete / error 等**终态**事件；若原样进父 SSE
    频道，父流会把 child 终态误当父终态而关流。此处一律包成 subagent_event（child_type 保留原
    类型），父 SSE 只认父自己发的 done/done_empty/error 为终态。只透传有信息量的子事件
    （tools_start / round_complete / run_complete / error），过滤 run_start/llm_start 噪声。
    实现 EventPublisher.publish 协议（autonomous_loop 经 publish_run_event 调用）。
    """

    _FORWARD = {"tools_start", "round_complete", "run_complete", "error"}

    def __init__(self, emitter: "_GapEmitter", skill_id: str) -> None:
        self._emitter = emitter
        self._skill_id = skill_id

    async def publish(self, channel: str, event: dict) -> None:  # noqa: ARG002 — 频道由子决定，父统一改道
        et = event.get("type", "")
        if et not in self._FORWARD:
            return
        wrapped = {
            "type": "subagent_event",
            "skill": self._skill_id,
            "child_type": et,
            "round": event.get("round"),
        }
        if et in ("round_complete", "tools_start"):
            think = event.get("thinking")
            if think:
                wrapped["thinking"] = str(think)[:200]
            if event.get("tool_calls"):
                wrapped["tool_calls"] = [
                    {"name": tc.get("name", ""), "args_preview": tc.get("args_preview", "")}
                    for tc in (event.get("tool_calls") or [])
                ]
            if event.get("tool_results"):
                wrapped["tool_results"] = [
                    {"tool_id": tr.get("tool_id"), "action": tr.get("action"),
                     "success": tr.get("success"), "summary": (tr.get("summary") or "")[:120]}
                    for tr in (event.get("tool_results") or [])
                ]
        if et == "error":
            wrapped["child_error"] = str(event.get("error") or "")[:200]
        await self._emitter.emit(wrapped)


# ======================================================================
# 背景 worker（自建 session；fail-loud 置 job 状态）
# ======================================================================

async def _run_gap_discover(job_id: int, pid: int, cid: str, topic: str,
                            max_candidates: int, llm: Any, override: Any, r: Any,
                            publisher: Any = None) -> None:
    # P1 可观测：单写锁 emit（落 events_json + 发 gap SSE 频道）。事件统一走 emitter 带 seq。
    emitter = _GapEmitter(publisher, SessionLocal, pid, job_id)
    async with SessionLocal() as s:
        job = await ai_job_repo.get_job(s, pid, job_id)
        if job is None:
            return
        await ai_job_repo.update_job(s, job, status="running")
    await emitter.emit({"type": "started", "topic": topic})
    try:
        async with SessionLocal() as s:
            markdowns, records, _skipped = await load_project_corpus(s, pid)
        if not markdowns:
            raise ApiError(400, "NO_CORPUS", "项目无可读全文语料（先入库+解析）")
        await emitter.emit({"type": "summarizing", "done": 0, "total": len(markdowns)})
        summaries = await summarize_papers(
            markdowns, topic, concurrency=4, override=override,
            on_progress=lambda d, t: emitter.emit({"type": "summarizing", "done": d, "total": t}),
        )
        await emitter.emit({"type": "discovering", "papers": len(summaries)})
        store = DbScratchpadStore(SessionLocal, project_id=pid)
        registry = build_registry(SessionLocal, r)
        result = await discover_gaps(
            topic=topic,
            paper_summaries=[ps.to_dict() for ps in summaries],
            registry=registry, llm_router=llm,
            # codex P1：不把父 raw emit 塞进 base_context —— 否则 child tool 直调
            # ctx["emit"]({"type":"error"}) 会绕过 _SubagentPublisher 包壳、被父 SSE 误当终态
            # 关流。子 agent 可见性统一走 _SubagentPublisher（包成 subagent_event）。
            base_context={"session_factory": SessionLocal, "project_id": pid},
            run_id=str(job_id), store=store, project_id=pid,
            max_candidates=max_candidates, llm_override=override,
            publisher=_SubagentPublisher(emitter, "gap-finder"),
        )
        # 问题3 修复：按 outcome 决定终态——非 ok 显式 failed，绝不静默 done。
        upd = _discover_job_update(result)
        async with SessionLocal() as s:
            job = await ai_job_repo.get_job(s, pid, job_id)
            if job is not None:
                await ai_job_repo.update_job(
                    s, job, status=upd["status"], complete=(upd["status"] == "done"),
                    error=upd["error"], summary_json=upd["summary_json"],
                )
        await emitter.emit(upd["event"])
    except Exception as e:  # noqa: BLE001 — fail-loud：置 failed，绝不静默
        logger.exception("[gap_discover] run=%s failed", job_id)
        async with SessionLocal() as s:
            job = await ai_job_repo.get_job(s, pid, job_id)
            if job is not None:
                await ai_job_repo.update_job(s, job, status="failed", error=str(e))
        await emitter.emit({"type": "error", "error": str(e)})


async def _run_gap_verify(job_id: int, pid: int, gap_id: str, thresholds: dict | None,
                          llm: Any, override: Any, r: Any, publisher: Any = None) -> None:
    emitter = _GapEmitter(publisher, SessionLocal, pid, job_id)
    async with SessionLocal() as s:
        job = await ai_job_repo.get_job(s, pid, job_id)
        if job is None:
            return
        await ai_job_repo.update_job(s, job, status="running")
    await emitter.emit({"type": "started", "gap_id": gap_id})
    try:
        async with SessionLocal() as s:
            rec = await gaps_repo.get_record(s, gap_id)
            if rec is None:
                raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
            gap = _gap_dict(rec)
            # 计量结构佐证：取 discover run 所属 corpus 的已算共现网络（不重算）。
            graph = None
            disc_job = await ai_job_repo.get_job(s, pid, int(rec.run_id)) if str(rec.run_id).isdigit() else None
            corpus_id = getattr(disc_job, "corpus_id", None)
        if corpus_id:
            st, body = await r.get_conceptual(corpus_id)
            if st == 200 and isinstance(body, dict):
                graph = body.get("graph")
        await emitter.emit({"type": "verifying", "gap_id": gap_id})
        registry = build_registry(SessionLocal, r)
        out = await verify_gap_value(
            gap, registry=registry, llm_router=llm,
            # codex P1：同上，不塞父 raw emit；子可见性走 _SubagentPublisher。
            base_context={"session_factory": SessionLocal, "project_id": pid},
            graph=graph, thresholds=thresholds, llm_override=override,
            publisher=_SubagentPublisher(emitter, "value-evidence"),
        )
        # 回写裁决 + 证据包 + status=verified
        async with SessionLocal() as s2:
            rec2 = await gaps_repo.get_record(s2, gap_id)
            if rec2 is not None:
                rec2.value_verdict = out["verdict"]
                rec2.evidence_pack = out["evidence"]
                if rec2.status == "draft":
                    rec2.status = "verified"
                await s2.commit()
        verdict_label = out["verdict"]["verdict"]
        async with SessionLocal() as s:
            job = await ai_job_repo.get_job(s, pid, job_id)
            if job is not None:
                await ai_job_repo.update_job(
                    s, job, status="done", complete=True,
                    summary_json={"verdict": verdict_label},
                )
        await emitter.emit({"type": "done", "verdict": verdict_label})
    except (ValueCheckError, ApiError, Exception) as e:  # noqa: BLE001 — fail-loud
        logger.exception("[gap_verify] run=%s gap=%s failed", job_id, gap_id)
        async with SessionLocal() as s:
            job = await ai_job_repo.get_job(s, pid, job_id)
            if job is not None:
                await ai_job_repo.update_job(s, job, status="failed", error=str(e))
        await emitter.emit({"type": "error", "error": str(e)})


async def _run_gap_feasibility(job_id: int, pid: int, gap_id: str, config: dict | None,
                               llm: Any, override: Any, r: Any, publisher: Any = None) -> None:
    """P2：可行性核验后台 worker。派 feasibility-scout 攒证 → 状态机裁决 → 写回
    feasibility_verdict/feasibility_pack。**与 value 链路独立**：只写 feasibility 字段，
    feasibility 失败绝不动既有 value_verdict（fail-loud 置 job failed）。"""
    emitter = _GapEmitter(publisher, SessionLocal, pid, job_id)
    async with SessionLocal() as s:
        job = await ai_job_repo.get_job(s, pid, job_id)
        if job is None:
            return
        await ai_job_repo.update_job(s, job, status="running")
    await emitter.emit({"type": "started", "gap_id": gap_id})
    try:
        async with SessionLocal() as s:
            rec = await gaps_repo.get_record(s, gap_id)
            if rec is None:
                raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
            full = _gap_dict(rec)
        # codex P2-4：可行性与 novelty 独立 —— 传给 feasibility-scout 的 gap 做白名单裁剪，
        # 不带 value_verdict / 旧 feasibility 字段，scout 取证阶段绝不看到 value 结论。
        gap = {k: full.get(k) for k in
               ("gap_id", "theme", "statement", "lens", "supporting_papers", "counter_evidence")}
        await emitter.emit({"type": "scouting", "gap_id": gap_id})
        registry = build_registry(SessionLocal, r)
        out = await verify_gap_feasibility(
            gap, registry=registry, llm_router=llm,
            base_context={"session_factory": SessionLocal, "project_id": pid},
            config=config, llm_override=override,
            publisher=_SubagentPublisher(emitter, "feasibility-scout"),
        )
        # 只写 feasibility 两字段（绝不碰 value_verdict/status，独立于 value 链路）。
        async with SessionLocal() as s2:
            rec2 = await gaps_repo.get_record(s2, gap_id)
            if rec2 is not None:
                rec2.feasibility_verdict = out["verdict"]
                rec2.feasibility_pack = out["pack"]
                await s2.commit()
        verdict_label = out["verdict"]["verdict"]
        async with SessionLocal() as s:
            job = await ai_job_repo.get_job(s, pid, job_id)
            if job is not None:
                await ai_job_repo.update_job(
                    s, job, status="done", complete=True,
                    summary_json={"feasibility": verdict_label},
                )
        await emitter.emit({"type": "done", "feasibility": verdict_label})
    except (FeasibilityCheckError, ApiError, Exception) as e:  # noqa: BLE001 — fail-loud
        logger.exception("[gap_feasibility] run=%s gap=%s failed", job_id, gap_id)
        async with SessionLocal() as s:
            job = await ai_job_repo.get_job(s, pid, job_id)
            if job is not None:
                await ai_job_repo.update_job(s, job, status="failed", error=str(e))
        await emitter.emit({"type": "error", "error": str(e)})


# ======================================================================
# Endpoints
# ======================================================================

async def _require_project(s: Any, pid: int) -> None:
    if await project_repo.get_project(s, pid) is None:
        raise ApiError(404, "PROJECT_NOT_FOUND", f"项目 {pid} 不存在")


def _no_corpus_message(diag: dict[str, int]) -> str:
    included = diag.get("includedCount", 0)
    included_fulltext = diag.get("includedWithFulltext", 0)
    sciverse_eligible = diag.get("fulltextEligibleCount", 0)
    candidate_fulltext = diag.get("candidatesWithFulltextCount", 0)
    stats = (
        f"当前统计：已纳入 {included} 篇，已纳入且有全文 {included_fulltext} 篇，"
        f"可自动补 Sciverse 全文 {sciverse_eligible} 篇，已有全文但未纳入 {candidate_fulltext} 篇。"
    )
    if candidate_fulltext > 0:
        return (
            "项目暂无可用于 GAP 发现的已纳入全文语料。"
            f"{stats}"
            "你已经上传并解析了全文，但这些文献尚未纳入；请到【文献库】-【筛选】"
            "把该文献标记为【已纳入】，再回到【研究】重新发现研究空白。"
        )
    if sciverse_eligible > 0:
        return (
            "项目暂无可用于 GAP 发现的已纳入全文语料。"
            f"{stats}"
            "当前有 Sciverse 题录可自动补全文；请先在文献库点击【补全文】"
            "或调用 fulltext:backfill，完成后把要精读的文献标记为【已纳入】。"
        )
    if included > 0:
        return (
            "项目已纳入文献，但这些文献没有可读全文附件。"
            f"{stats}"
            "GAP 发现需要精读全文并产生逐字溯源；请先到【文献库】上传 PDF 并完成解析，"
            "或为 Sciverse 文献补全文。"
        )
    return (
        "项目还没有已纳入的可读全文语料。"
        f"{stats}"
        "请先到【文献库】导入/上传文献；如已有待筛选文献，请在【筛选】中标记为【已纳入】。"
    )


@router.post("/projects/{pid}/corpus/{cid}/gaps:discover", status_code=202)
async def discover(pid: int, request: Request,
                   background_tasks: BackgroundTasks,
                   body: GapDiscoverRequest | None = None,
                   cid: str = Path(pattern=_SEG),
                   s=Depends(get_session)):
    """启动 GAP 发现 run（用 scratchpad 编排）。返回 run_id 供轮询 scratchpad。

    契约 §2.1 该 endpoint 无请求体；body 可选。topic 缺省时从项目派生
    （research_question > name），避免前端「无 body」请求 422（A/B seam 对齐）。
    """
    from .main import _llm_override  # lazy：避免与 main 循环导入
    proj = await project_repo.get_project(s, pid)
    if proj is None:
        raise ApiError(404, "PROJECT_NOT_FOUND", f"项目 {pid} 不存在")
    # 问题1 修复：同步预检该项目有无可读全文语料——无则快速失败 400，不浪费一次异步 run + LLM
    # 调用（此前 OpenAlex 元数据项目会异步跑到 load 空才 failed，用户等半天看到模糊失败）。
    if not await has_readable_fulltext(s, pid):
        diag = await project_fulltext_diagnostics(s, pid)
        raise ApiError(400, "NO_CORPUS", _no_corpus_message(diag), details=diag)
    max_candidates = body.max_candidates if body else 12
    # codex P2: body.topic 需 strip —— 否则 "   " 这类纯空白 truthy 会绕过派生链, 把空白
    # topic 写进 job/喂给 gap-finder。先归一化, 空白则落到 research_question/name 派生。
    topic = ((body.topic or "").strip() if body else "") \
        or (proj.research_question or "").strip() \
        or (proj.name or "").strip() \
        or "研究主题"
    job = await ai_job_repo.create_job(
        s, project_id=pid, kind="gap_discover", corpus_id=cid,
        request_json={"topic": topic, "max_candidates": max_candidates},
    )
    # dispatch 需 LLMRouter（非 get_llm_client）；from_config 读 env deepseek。
    # P1 可观测：传 app.state.publisher，进度/子事件经 gap SSE 频道实时冒。
    background_tasks.add_task(
        _run_gap_discover, job.id, pid, cid, topic, max_candidates,
        LLMRouter.from_config(), _llm_override(request), request.app.state.r_client,
        request.app.state.publisher,
    )
    return {"run_id": str(job.id)}


@router.get("/projects/{pid}/agent/runs/{rid}/scratchpad")
async def get_scratchpad(pid: int, rid: str = Path(pattern=_SEG), s=Depends(get_session)):
    """拉取本 run 的实时 scratchpad（GapCandidate 列表 + run_status 停轮询信号）。"""
    await _require_project(s, pid)
    gaps = await gaps_repo.list_gaps_by_run(s, rid)
    job = await ai_job_repo.get_job(s, pid, int(rid)) if rid.isdigit() else None
    entries = [_gap_dict(g) for g in gaps]
    return {
        "run_id": rid,
        "entries": entries,
        "updated_at": getattr(job, "updated_at", None).isoformat() if getattr(job, "updated_at", None) else "",
        "run_status": _run_status(job),
    }


@router.get("/projects/{pid}/gaps/runs/{rid}/events")
async def gap_run_events(pid: int, request: Request,
                        rid: str = Path(pattern=_SEG), s=Depends(get_session)):
    """gap discover/verify 的实时进度 SSE —— 消除长精读/核验阶段黑箱（P1）。

    先订阅频道（缓冲实时事件）→ 补发 events_json 历史（落库权威，Last-Event-ID 断点续传）
    → 按 seq 去重转发实时，直到父终态（done/done_empty/error）关流。事件类型：
    started / summarizing(done,total) / discovering / subagent_event(child_type) /
    verifying / done|done_empty|error。前端 Timeline 消费。
    """
    await _require_project(s, pid)
    if not rid.isdigit():
        raise ApiError(404, "GAP_RUN_NOT_FOUND", f"gap run {rid} 不存在")
    job = await ai_job_repo.get_job(s, pid, int(rid))
    if job is None:
        raise ApiError(404, "GAP_RUN_NOT_FOUND", f"gap run {rid} 不存在")

    publisher = request.app.state.publisher
    channel = gap_channel(int(rid))
    raw_lei = request.headers.get("last-event-id", "0")
    try:
        last_id = int(raw_lei)
    except (ValueError, TypeError):
        last_id = 0

    # 先订阅（订阅后频道即开始缓冲，覆盖「读历史—进实时」窗口）——codex P1：必须**订阅后再重
    # 读** events_json，否则订阅前查出的 job 快照会漏掉「get_job→subscribe 之间」emit 的终态
    # （published 早于 subscribe → 队列收不到；快照又无它 → 客户端永挂 heartbeat）。
    # 用**请求同一会话** s.refresh（不是硬编码 SessionLocal，那会绕过 get_session 依赖覆盖、
    # 在测试/多租户下读错库）拉取 worker 已提交的最新 events_json/status。
    q = publisher.subscribe(channel)
    try:
        await s.refresh(job)
    except Exception:  # noqa: BLE001 — refresh 失败退回订阅前快照，不阻断
        logger.warning("[gap_sse] refresh job 失败 rid=%s（退回订阅前快照）", rid)
    history = list(job.events_json or [])
    # 终态兜底（codex P1/P2）：若 emit 落库失败或 Last-Event-ID 跳过了已持久化终态，仍据
    # job.status 合成终态关流，绝不让已结束的 run 让客户端永等。

    def _terminal_from_job(next_seq: int) -> dict | None:
        # 读**实时** job（s.refresh 原地更新该对象）——心跳分支 refresh 后 job 变终态时也能
        # 合成正确终态（codex：不能读进 gen() 前缓存的旧 status，否则情形(c)只 EOF 不发终态）。
        st = _run_status(job)
        if st == "failed":
            return {"type": "error", "error": getattr(job, "error", None) or "运行失败",
                    "seq": next_seq, "synthesized": True}
        if st == "done":
            return {"type": "done", "seq": next_seq, "synthesized": True}
        return None

    async def gen():
        try:
            max_seq = last_id
            history_has_terminal = False
            for ev in history:
                seq = ev.get("seq", 0)
                is_terminal = ev.get("type") in _GAP_TERMINAL_TYPES
                if is_terminal:
                    history_has_terminal = True  # 记账即便被 Last-Event-ID 跳过（P2）
                if seq <= last_id:
                    continue
                yield _sse_frame(ev.get("type", "message"), ev, seq=seq)
                if seq > max_seq:
                    max_seq = seq
            # 历史已含终态（含被 Last-Event-ID 跳过的）→ run 已结束，直接关流。
            if history_has_terminal:
                return
            # 历史无终态但 job 已终态（emit 终态落库失败 / 竞态）→ 合成终态关流。
            if _run_status(job) in ("done", "failed"):
                term = _terminal_from_job(max_seq + 1)
                if term is not None:
                    yield _sse_frame(term["type"], term, seq=term["seq"])
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # 心跳 + 兜底轮询（codex P1）：终态事件可能已落库但 publish 失败（emit 吞掉
                    # 发布异常），活跃连接光等队列会永挂。每次心跳 refresh job → 补发 events_json
                    # 中 seq>max_seq 的新事件；含终态即关流；仍无终态但 job 已终态 → 合成终态关流。
                    try:
                        await s.refresh(job)
                    except Exception:  # noqa: BLE001
                        pass
                    drained_terminal = False
                    for pev in (job.events_json or []):
                        pseq = pev.get("seq", 0)
                        if pseq <= max_seq:
                            continue
                        yield _sse_frame(pev.get("type", "message"), pev, seq=pseq)
                        max_seq = pseq
                        if pev.get("type") in _GAP_TERMINAL_TYPES:
                            drained_terminal = True
                    if drained_terminal:
                        break
                    if _run_status(job) in ("done", "failed"):
                        term = _terminal_from_job(max_seq + 1)
                        if term is not None:
                            yield _sse_frame(term["type"], term, seq=term["seq"])
                        break
                    yield ": hb\n\n"
                    continue
                seq = ev.get("seq", 0)
                if seq <= max_seq:  # 去重：实时事件 seq 若已在历史发过，跳过
                    continue
                yield _sse_frame(ev.get("type", "message"), ev, seq=seq)
                if seq > max_seq:
                    max_seq = seq
                if ev.get("type") in _GAP_TERMINAL_TYPES:
                    break
        finally:
            publisher.unsubscribe(channel, q)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{pid}/gaps/{gap_id}:verify", status_code=202)
async def verify(pid: int, request: Request, background_tasks: BackgroundTasks,
                 gap_id: str = Path(pattern=_SEG),
                 body: GapVerifyRequest | None = None,
                 s=Depends(get_session)):
    """启动该 GAP 的价值二次验证（反向检索证伪 + 计量结构佐证 → 确定性裁决）。"""
    from .main import _llm_override
    await _require_project(s, pid)
    rec = await gaps_repo.get_record(s, gap_id)
    if rec is None:
        raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
    thresholds = None
    if body and body.thresholds:
        thresholds = {"reverse_hit_high": body.thresholds.reverse_hit_high,
                      "reverse_hit_low": body.thresholds.reverse_hit_low}
    job = await ai_job_repo.create_job(
        s, project_id=pid, kind="gap_verify", corpus_id=getattr(rec, "corpus_id", None),
        request_json={"gap_id": gap_id, "thresholds": thresholds},
    )
    background_tasks.add_task(
        _run_gap_verify, job.id, pid, gap_id, thresholds,
        LLMRouter.from_config(), _llm_override(request), request.app.state.r_client,
        request.app.state.publisher,
    )
    return {"verify_run_id": str(job.id)}


@router.get("/projects/{pid}/gaps/{gap_id}/verdict")
async def get_verdict(pid: int, gap_id: str = Path(pattern=_SEG), s=Depends(get_session)):
    """取价值裁决 + 攒证的证据包（§2.4-1：裁决 + 证据包复合体）。"""
    await _require_project(s, pid)
    rec = await gaps_repo.get_record(s, gap_id)
    if rec is None:
        raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
    if not rec.value_verdict:
        raise ApiError(409, "GAP_NOT_VERIFIED", f"GAP {gap_id} 尚未核验（先 POST :verify）")
    return {"gap_id": gap_id, "verdict": rec.value_verdict, "evidence": rec.evidence_pack}


@router.post("/projects/{pid}/gaps/{gap_id}:feasibility", status_code=202)
async def feasibility(pid: int, request: Request, background_tasks: BackgroundTasks,
                      gap_id: str = Path(pattern=_SEG),
                      body: GapFeasibilityRequest | None = None,
                      s=Depends(get_session)):
    """P2：启动该 GAP 的可行性核验（组件级侦察 → 状态机裁决 buildable/hard/blocked）。

    与 novelty(value) 独立：另建 job、写 feasibility_verdict/feasibility_pack，不碰 value_verdict。
    """
    from .main import _llm_override
    await _require_project(s, pid)
    rec = await gaps_repo.get_record(s, gap_id)
    if rec is None:
        raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
    config = body.config if body else None
    job = await ai_job_repo.create_job(
        s, project_id=pid, kind="gap_feasibility", corpus_id=getattr(rec, "corpus_id", None),
        request_json={"gap_id": gap_id, "config": config},
    )
    background_tasks.add_task(
        _run_gap_feasibility, job.id, pid, gap_id, config,
        LLMRouter.from_config(), _llm_override(request), request.app.state.r_client,
        request.app.state.publisher,
    )
    return {"feasibility_run_id": str(job.id)}


@router.get("/projects/{pid}/gaps/{gap_id}/feasibility-verdict")
async def get_feasibility_verdict(pid: int, gap_id: str = Path(pattern=_SEG),
                                  s=Depends(get_session)):
    """P2：取可行性裁决 + 攒证包（未核验 → 409，与 value verdict 同款诚实策略）。"""
    await _require_project(s, pid)
    rec = await gaps_repo.get_record(s, gap_id)
    if rec is None:
        raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
    if not rec.feasibility_verdict:
        raise ApiError(409, "GAP_NOT_FEASIBILITY_CHECKED",
                       f"GAP {gap_id} 尚未做可行性核验（先 POST :feasibility）")
    return {"gap_id": gap_id, "verdict": rec.feasibility_verdict, "pack": rec.feasibility_pack}


@router.patch("/projects/{pid}/gaps/{gap_id}")
async def patch_gap(pid: int, body: GapPatchRequest,
                    gap_id: str = Path(pattern=_SEG), s=Depends(get_session)):
    """HITL：人工 accept / reject / revise，留痕进 run events。"""
    await _require_project(s, pid)
    _validate_patch_oneof(body)   # 前置 422（先于 gap 存在性，可预测）
    rec = await gaps_repo.get_record(s, gap_id)
    if rec is None:
        raise ApiError(404, "GAP_NOT_FOUND", f"GAP {gap_id} 不存在")
    if body.action == "accept":
        rec.status = "accepted"
    elif body.action == "reject":
        rec.status = "rejected"
    else:  # revise
        rec.statement = body.statement
    await s.commit()
    await s.refresh(rec)
    # 留痕：写入 discover run 的事件流（best-effort，不阻断主流程）
    try:
        if str(rec.run_id).isdigit():
            job = await ai_job_repo.get_job(s, pid, int(rec.run_id))
            if job is not None:
                await ai_job_repo.update_job(s, job, append_event={
                    "type": "hitl_decision", "gap_id": gap_id,
                    "decision": body.action, "note": body.note or "",
                })
    except Exception:  # noqa: BLE001
        logger.warning("[patch_gap] 留痕失败 gap=%s（不阻断）", gap_id)
    return _gap_dict(rec)
