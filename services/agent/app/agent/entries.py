"""三入口隔离配置 —— entry → (tool_ids 子集, system persona)。

设计（docs/plans/2026-07-05 多源检索Agent引擎设计 v2 · P0）：
  - 无顶层 AI 统筹，路由 = 用户点 UI 按钮（entry），不做 AI 分诊。
  - 上下文隔离 = 每入口独立 system persona + tool_ids 子集：LLM 只拿到本域工具的
    function 定义，拿不到就无法调用（暴露级硬拦越权）。
  - 群间只共享文献库（project/corpus DB）；对话上下文按 entry 隔离
    （见 run_controller._history_messages / agent_run.list_recent_dialog 的 entry 过滤）。
  - 灰度铁律：entry=None / 未知值 → legacy 全工具 + AGENT_SYSTEM；老 workbench 不传
    entry 时绝不被收窄（无回归）。

tool_ids 粒度是 tool_id（非 action）——见 harness/tools.py ToolRegistry.get_function_definitions。
现有 tool_id：library / project / corpus / analysis / review / search / ingest / extract /
read_paper / scratchpad / submit_evidence_pack。
"""
from __future__ import annotations

from .prompts import AGENT_SYSTEM, GAP_SYSTEM, REVIEW_SYSTEM, SEARCH_SYSTEM

# entry 常量（与前端 / 契约约定一致）
ENTRY_SEARCH = "search"
ENTRY_REVIEW = "review"
ENTRY_GAP = "gap"
ENTRY_LEGACY = "legacy"  # entry=None 归一化为此，语义 = 旧全工具入口（无收窄）

# 三个可路由入口（前端会用到）；legacy 不对外暴露为可选项，仅作兜底。
ROUTABLE_ENTRIES = (ENTRY_SEARCH, ENTRY_REVIEW, ENTRY_GAP)

# entry → 授权 tool_ids 子集（None = 全部工具，仅 legacy）。
_ENTRY_TOOL_IDS: dict[str, set[str] | None] = {
    # 检索建库：多源/单源检索 + 导入(project__import_search_results) + 库操作 +
    # 全文摄取(ingest) + 结构化抽取(extract) + 建库(corpus) + 按需精读取证(read_paper 只读)。
    ENTRY_SEARCH: {
        "search", "project", "library", "ingest", "extract", "corpus", "read_paper",
    },
    # 综述撰写：综述工具（内部 map-reduce）+ 按需核查原文(read_paper 只读)。
    ENTRY_REVIEW: {"review", "read_paper"},
    # 研究空白对话：按需精读(read_paper) + gap 工作记忆(scratchpad) + 旁证检索(search)。
    ENTRY_GAP: {"read_paper", "scratchpad", "search"},
    # legacy：全工具（tool_ids=None），保持旧对话工作台行为。
    ENTRY_LEGACY: None,
}

_ENTRY_SYSTEM: dict[str, str] = {
    ENTRY_SEARCH: SEARCH_SYSTEM,
    ENTRY_REVIEW: REVIEW_SYSTEM,
    ENTRY_GAP: GAP_SYSTEM,
    ENTRY_LEGACY: AGENT_SYSTEM,
}


def normalize_entry(entry: str | None) -> str:
    """归一化 entry：None / 未知值 → legacy（灰度铁律：绝不把未知入口收窄）。"""
    if entry is None:
        return ENTRY_LEGACY
    e = entry.strip().lower()
    return e if e in _ENTRY_TOOL_IDS else ENTRY_LEGACY


def entry_to_db(entry: str | None) -> str | None:
    """落库值：legacy 存 NULL（与既有历史行一致、向后兼容），其余存归一化字符串。"""
    norm = normalize_entry(entry)
    return None if norm == ENTRY_LEGACY else norm


def entry_tool_ids(entry: str | None) -> set[str] | None:
    """本 entry 授权的 tool_ids 子集；legacy → None（全工具）。返回副本防调用方篡改。"""
    ids = _ENTRY_TOOL_IDS[normalize_entry(entry)]
    return set(ids) if ids is not None else None


def entry_system_prompt(entry: str | None) -> str:
    """本 entry 的 system persona；legacy → AGENT_SYSTEM。"""
    return _ENTRY_SYSTEM[normalize_entry(entry)]
