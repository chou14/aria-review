"""P2 · SubmitFeasibilityPackTool —— 可行性侦察 subagent 回传「可行性证据」。

铁律边界（仿 submit_evidence_pack）：本工具**只规整结构、不做算术、不裁决**。最终
feasibility verdict 由 app/review/feasibility_check.py 的确定性状态机 resolver 出
（decided_by=deterministic）。LLM/subagent 只攒证据，绝不在此层产 verdict。

收集形态（领域无关，见方案 v3 §3 FeasibilityPack）：
  data_availability : {query, provider, datasets:[{name,source,url,access,kind}]}
  method_base       : {query, building_blocks:[{kind,name,doi,has_code}]}  # component-only
  resource_scale    : {scale_flag, typical_sample_size, typical_compute, note}
  negative_evidence : [{kind, note}]   # 供 blocked（data_unavailable/no_measurement/unidentifiable）
  notes / skipped   : [...]

novelty×feasibility 解耦（v3 命门）：method_base.query / data_availability.query **只能用组件/
要素词**（方法名、工具、数据类型），严禁拼入完整 GAP 论断或「A×B 是否被研究」式检索——那是
novelty 的事。本工具对疑似含完整 GAP statement 的 query **留痕告警**（不硬拒；resolver 侧靠
status 语义兜底，SKILL 端 prompt 硬约束是第一防线）。
"""
from __future__ import annotations

from typing import Any

from app.harness.tools import BaseTool, ToolResult


class SubmitFeasibilityPackTool(BaseTool):
    tool_id = "submit_feasibility_pack"
    tool_name = "提交可行性核验证据"
    description = (
        "提交研究方向可行性核验的可核验证据（数据可得性 / 方法组件基座 / 资源规模 / 负证据 / "
        "备注 / 跳过项）。只提交证据，不做算术、不产可行性裁决——裁决由确定性状态机 resolver 完成。"
        "检索 query 只用组件/要素词，严禁拼入完整 GAP 论断（那是 novelty 的事）。"
    )
    actions = ["submit"]
    tags = ["write"]
    action_schemas = {
        "submit": {
            "type": "object",
            "properties": {
                "pack": {
                    "type": "object",
                    "description": (
                        "证据包，建议含 gap_id / data_availability / method_base / "
                        "resource_scale / negative_evidence / notes / skipped"
                    ),
                },
            },
            "required": ["pack"],
        },
    }

    async def _execute(self, action: str, params: dict[str, Any], context: Any = None) -> ToolResult:
        if action != "submit":
            return self._fail(action, f"未知 action: {action}")
        pack = params.get("pack")
        normalized = _normalize_pack(pack)
        if "error" in normalized:
            return self._fail(action, normalized["error"])  # fail-loud：非法证据包显式失败
        n = _count_entries(normalized)
        gid = normalized.get("gap_id") or "?"
        warn = normalized.get("_suspected_gap_statement_queries")
        suffix = f"；⚠ {len(warn)} 条 query 疑含完整 GAP 论断（已留痕）" if warn else ""
        return self._ok(
            "submit", [normalized], source="subagent",
            summary=f"已接收 gap {gid} 可行性证据包（{n} 条线索，不裁决）{suffix}",
        )


# 仅规整结构、不解释、不裁决（铁律：collect-only）。
_LIST_KEYS = ("notes", "skipped", "negative_evidence")
_QUERY_BEARING = ("data_availability", "method_base")
# LLM 若在证据包里夹带"裁决"字段，一律剥离：feasibility verdict 的唯一权威是确定性 resolver。
_FORBIDDEN_VERDICT_KEYS = (
    "verdict", "score", "decided_by", "feasibility_verdict",
    "data_status", "method_status", "resource_status", "rationale",
)


def _deep_strip(obj: Any, keys: set[str]) -> set[str]:
    """递归从 dict/list 里删除 forbidden 裁决键，返回实际剥离过的键集（留痕）。逐字保留其余证据。"""
    stripped: set[str] = set()
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if k in keys:
                obj.pop(k, None)
                stripped.add(k)
            else:
                stripped |= _deep_strip(obj[k], keys)
    elif isinstance(obj, list):
        for item in obj:
            stripped |= _deep_strip(item, keys)
    return stripped


def _looks_like_gap_statement(query: str) -> bool:
    """启发式判断 query 是否疑似夹带完整 GAP 论断（novelty 的活）而非纯组件/要素词。

    命中任一即疑似（留痕告警，不硬拒）：过长（组件检索式通常短）；含"是否/未被研究/关系"等
    论断标记；含"A × B / A and B in Z"式概念配对措辞。这是 resolver 侧的 status 兜底 + SKILL 端
    prompt 硬约束之外的**第三道软防线**。
    """
    q = (query or "").strip()
    if not q:
        return False
    if len(q) > 100:
        return True
    markers = ("是否", "未被研究", "尚未", "空白", "关系", "whether", "unexplored",
               "under-studied", "not been studied", "relationship between", " vs ")
    ql = q.lower()
    return any(m.lower() in ql for m in markers)


def _normalize_pack(pack: Any) -> dict[str, Any]:
    if not isinstance(pack, dict) or not pack:
        return {"error": "pack 必须是非空对象"}
    out = dict(pack)
    # gap_id 必填（fail-loud）：证据须能关联回被核验的 GAP。
    gid = out.get("gap_id")
    if not str(gid or "").strip():
        return {"error": "pack 必须含非空 gap_id（证据须关联到被核验的 GAP）"}
    out["gathered_by"] = "subagent"
    # collect-only 边界：**递归**剥离任何 LLM 夹带的裁决字段（codex P2-3：嵌套在 method_base/
    # resource_scale/notes 里的 verdict/*_status 也须剥，否则 API 返回的 pack 仍含裁决暗示）。
    stripped = _deep_strip(out, set(_FORBIDDEN_VERDICT_KEYS))
    if stripped:
        out["_stripped_verdict_fields"] = sorted(stripped)  # 透明留痕：剥离了什么
    # notes/skipped/negative_evidence 容错：单条(字符串或对象) → 单元素数组（逐字保留）。
    # negative_evidence/skipped 元素是对象，notes 是字符串；LLM 可能未包数组，此处规整不丢。
    for key in _LIST_KEYS:
        v = out.get(key)
        if v is None:
            continue
        if isinstance(v, (str, dict)):
            out[key] = [v]
        elif not isinstance(v, list):
            return {"error": f"{key} 必须是字符串/对象或数组"}
    # query-bearing 块形状容错 + query 疑含 GAP statement 留痕告警。
    suspected: list[str] = []
    for key in _QUERY_BEARING:
        blk = out.get(key)
        if blk is None:
            continue
        if not isinstance(blk, dict):
            return {"error": f"{key} 必须是对象"}
        q = blk.get("query")
        if q is not None and _looks_like_gap_statement(str(q)):
            suspected.append(str(q))
    if suspected:
        out["_suspected_gap_statement_queries"] = suspected  # 留痕，不硬拒（resolver 靠 status 兜底）
    rc = out.get("resource_scale")
    if rc is not None and not isinstance(rc, dict):
        return {"error": "resource_scale 必须是对象"}
    # 拒绝空证据包（仅 gap_id、无任何证据）。带 query 的检索块（即便 datasets/blocks 空）本身
    # 就算"已侦察"证据，故不要求命中非空——只要求确有一类证据被收集。
    if not _has_evidence(out):
        return {"error": (
            "空证据包：至少需 data_availability/method_base(带 query)/resource_scale/"
            "negative_evidence/notes/skipped 之一"
        )}
    return out


def _has_evidence(pack: dict[str, Any]) -> bool:
    """是否承载至少一类可行性证据。"""
    for key in _QUERY_BEARING:
        blk = pack.get(key)
        if isinstance(blk, dict) and str(blk.get("query") or "").strip():
            return True  # 执行了带 query 的侦察（空命中也是证据）
    if isinstance(pack.get("resource_scale"), dict) and pack["resource_scale"]:
        return True
    for key in ("negative_evidence", "notes", "skipped"):
        if pack.get(key):
            return True
    return False


def _count_entries(pack: dict[str, Any]) -> int:
    total = 0
    da = pack.get("data_availability")
    if isinstance(da, dict) and isinstance(da.get("datasets"), list):
        total += len(da["datasets"])
    mb = pack.get("method_base")
    if isinstance(mb, dict) and isinstance(mb.get("building_blocks"), list):
        total += len(mb["building_blocks"])
    for key in _LIST_KEYS:
        v = pack.get(key)
        if isinstance(v, list):
            total += len(v)
    if isinstance(pack.get("resource_scale"), dict):
        total += 1
    return total
