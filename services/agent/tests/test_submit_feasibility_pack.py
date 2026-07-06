"""P2 · submit_feasibility_pack collect-only 契约测试。

验收(v3 S2)：合法 ok + 剥离裁决字段留痕；缺 gap_id fail；空包 fail；status 字段透传；
query 疑含完整 GAP statement → 留痕告警(不硬拒)。
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools.submit_feasibility_pack import SubmitFeasibilityPackTool


async def _submit(pack):
    tool = SubmitFeasibilityPackTool()
    return await tool.execute("submit", {"pack": pack}, context=None)


@pytest.mark.asyncio
async def test_ok_strips_verdict_and_keeps_evidence():
    r = await _submit({
        "gap_id": "g1",
        "method_base": {"query": "federated learning", "building_blocks": [{"kind": "method", "name": "FedAvg"}]},
        "data_availability": {"query": "chest x-ray", "datasets": [{"name": "CheXpert", "access": "open", "url": "http://x"}]},
        # LLM 夹带裁决字段 → 必须被剥离
        "verdict": "buildable", "decided_by": "llm", "method_status": "supported",
    })
    assert r.success
    pack = r.data[0]
    # 证据保留
    assert pack["method_base"]["building_blocks"][0]["name"] == "FedAvg"
    assert pack["data_availability"]["datasets"][0]["name"] == "CheXpert"
    # 裁决字段被剥离 + 留痕
    for k in ("verdict", "decided_by", "method_status"):
        assert k not in pack
    assert set(pack["_stripped_verdict_fields"]) >= {"verdict", "decided_by", "method_status"}


@pytest.mark.asyncio
async def test_missing_gap_id_fails():
    r = await _submit({"method_base": {"query": "x", "building_blocks": [{"name": "a"}]}})
    assert not r.success and "gap_id" in (r.error or "")


@pytest.mark.asyncio
async def test_empty_pack_fails():
    r = await _submit({"gap_id": "g1"})  # 只有 gap_id，无任何证据
    assert not r.success and "空证据包" in (r.error or "")


@pytest.mark.asyncio
async def test_query_bearing_block_counts_as_evidence_even_empty_hits():
    # 带 query 的侦察（datasets 空）本身算证据（"已侦察，未命中"）
    r = await _submit({"gap_id": "g1", "data_availability": {"query": "rare dataset", "datasets": []}})
    assert r.success


@pytest.mark.asyncio
async def test_suspected_gap_statement_query_flagged_not_rejected():
    # method query 疑含完整 GAP 论断 → 留痕告警，但不硬拒（resolver 侧靠 status 兜底）
    r = await _submit({
        "gap_id": "g1",
        "method_base": {
            "query": "联邦学习与可解释性在医疗影像诊断中的关系是否已被研究",
            "building_blocks": [{"name": "FedAvg"}, {"name": "SHAP"}],
        },
    })
    assert r.success
    assert r.data[0]["_suspected_gap_statement_queries"]  # 留痕
    assert "疑含完整 GAP" in (r.summary or "")


@pytest.mark.asyncio
async def test_component_only_query_not_flagged():
    r = await _submit({
        "gap_id": "g1",
        "method_base": {"query": "federated learning SHAP", "building_blocks": [{"name": "FedAvg"}]},
    })
    assert r.success
    assert "_suspected_gap_statement_queries" not in r.data[0]


@pytest.mark.asyncio
async def test_deep_strip_nested_verdict_fields():
    # 嵌套在 method_base 里的裁决字段也须被递归剥离（codex P2-3）
    r = await _submit({
        "gap_id": "g1",
        "method_base": {
            "query": "fedavg", "building_blocks": [{"name": "FedAvg"}],
            "method_status": "supported",  # 嵌套裁决暗示 → 必须剥
        },
    })
    assert r.success
    pack = r.data[0]
    assert "method_status" not in pack["method_base"]  # 嵌套裁决被剥
    assert "method_status" in pack["_stripped_verdict_fields"]
    # 证据本身保留
    assert pack["method_base"]["building_blocks"][0]["name"] == "FedAvg"


@pytest.mark.asyncio
async def test_negative_evidence_passthrough_as_list():
    r = await _submit({
        "gap_id": "g1",
        "negative_evidence": {"kind": "data_unavailable", "note": "proprietary"},  # 单条 → 数组
    })
    assert r.success
    assert isinstance(r.data[0]["negative_evidence"], list)
    assert r.data[0]["negative_evidence"][0]["kind"] == "data_unavailable"
