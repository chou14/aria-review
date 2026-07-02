"""Paper 双轨去重的存量合并逻辑。

供 Alembic data migration 和单元测试共用。这里使用同步 Connection，
避免迁移脚本里混入 async session 生命周期。
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any, Callable, Mapping

from sqlalchemy import JSON, bindparam, text
from sqlalchemy.engine import Connection


_DOI_URL_PREFIX_RE = re.compile(
    r"^https?://(?:dx\.)?doi\.org/",
    re.IGNORECASE,
)

_PAPER_FILL_FIELDS = (
    "item_type",
    "creators",
    "year",
    "container_title",
    "volume",
    "issue",
    "pages",
    "url",
    "abstract",
    "keywords",
    "language",
    "source",
    "csl_json",
)

_EXTRACTION_FILL_FIELDS = (
    "research_question",
    "method",
    "findings",
    "dataset",
    "contribution",
    "raw",
    "model",
)

_REFERENCE_TABLES = (
    "paper_tag",
    "note",
    "attachment",
    "project_paper",
    "corpus_paper",
    "paper_extraction",
    "paper_external_id",
)


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalize_doi(raw: str) -> str:
    stripped = _DOI_URL_PREFIX_RE.sub("", raw.strip())
    return stripped.strip().lower()


def _normalize_title(raw_title: str) -> str:
    nfc_title = unicodedata.normalize("NFC", raw_title)
    return re.sub(r"\W+", "", nfc_title.lower())


def _title_dedup_key(raw_title: str) -> str:
    norm = _normalize_title(raw_title)
    return "title:" + hashlib.sha256(norm.encode()).hexdigest()[:32]


def _completeness_score(row: Mapping[str, Any]) -> int:
    return sum(0 if _is_missing(row.get(field)) else 1 for field in _PAPER_FILL_FIELDS)


def _created_sort_key(row: Mapping[str, Any]) -> tuple[bool, str, int]:
    created_at = row.get("created_at")
    if hasattr(created_at, "isoformat"):
        created = created_at.isoformat()
    else:
        created = str(created_at or "")
    return (created == "", created, int(row["id"]))


def plan_paper_dedup_merges(
    papers: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """生成双轨重复合并计划；不访问数据库，便于单测。

    规则：同 owner + 同规范化标题，且只有一个非空规范化 DOI 的组，才自动合并。
    多个不同 DOI 同标题视为歧义，跳过，避免误合并不同文献。
    """
    groups: dict[tuple[int | None, str], list[Mapping[str, Any]]] = defaultdict(list)
    # (owner_id, dedup_key) -> paper ids：用于检测组外行已持有目标 doi: key 的冲突
    # （同 DOI 但标题规范化不同会分到别组，直接升级会撞 uq_paper_dedup）
    dedup_key_holders: dict[tuple[int | None, str], set[int]] = defaultdict(set)
    for paper in papers:
        existing_key = str(paper.get("dedup_key") or "")
        if existing_key:
            dedup_key_holders[(paper.get("owner_id"), existing_key)].add(int(paper["id"]))
        norm_title = _normalize_title(str(paper.get("title") or ""))
        if not norm_title:
            continue
        groups[(paper.get("owner_id"), norm_title)].append(paper)

    merges: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for (owner_id, norm_title), rows in groups.items():
        no_doi = [row for row in rows if not _normalize_doi(str(row.get("doi") or ""))]
        doi_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            norm_doi = _normalize_doi(str(row.get("doi") or ""))
            if norm_doi:
                doi_groups[norm_doi].append(row)

        if not no_doi or not doi_groups:
            continue
        if len(doi_groups) > 1:
            skipped.append({
                "reason": "ambiguous_doi",
                "owner_id": owner_id,
                "normalized_title": norm_title,
                "paper_ids": sorted(int(row["id"]) for row in rows),
                "doi_values": sorted(doi_groups.keys()),
            })
            continue

        norm_doi, doi_rows = next(iter(doi_groups.items()))
        group_ids = {int(row["id"]) for row in rows}
        outside_holders = dedup_key_holders.get((owner_id, f"doi:{norm_doi}"), set()) - group_ids
        if outside_holders:
            skipped.append({
                "reason": "dedup_key_conflict",
                "owner_id": owner_id,
                "normalized_title": norm_title,
                "paper_ids": sorted(group_ids),
                "conflicting_paper_ids": sorted(outside_holders),
                "doi_values": [norm_doi],
            })
            continue
        title_key = _title_dedup_key(str(rows[0].get("title") or ""))
        target = sorted(
            no_doi,
            key=lambda row: (
                row.get("dedup_key") != title_key,
                -_completeness_score(row),
                _created_sort_key(row),
            ),
        )[0]
        best_doi_row = sorted(
            doi_rows,
            key=lambda row: (-_completeness_score(row), _created_sort_key(row)),
        )[0]
        source_ids = sorted(int(row["id"]) for row in rows if int(row["id"]) != int(target["id"]))
        if not source_ids:
            continue
        merges.append({
            "target_id": int(target["id"]),
            "source_ids": source_ids,
            "doi_source_id": int(best_doi_row["id"]),
            "doi": best_doi_row.get("doi"),
            "dedup_key": f"doi:{norm_doi}",
            "owner_id": owner_id,
            "normalized_title": norm_title,
        })

    return {"merges": merges, "skipped": skipped}


def _fetch_papers(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(text(
        """
        SELECT id, item_type, title, creators, year, container_title, volume,
               issue, pages, doi, url, abstract, keywords, language, source,
               csl_json, dedup_key, owner_id, created_at, updated_at
        FROM paper
        ORDER BY id
        """
    )).mappings().all()
    return [dict(row) for row in rows]


def _reference_counts(conn: Connection, source_ids: list[int]) -> dict[str, int]:
    counts = dict.fromkeys(_REFERENCE_TABLES, 0)
    for source_id in source_ids:
        for table in _REFERENCE_TABLES:
            counts[table] += int(conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE paper_id = :paper_id"),
                {"paper_id": source_id},
            ).scalar_one())
    return counts


def _paper_by_id(conn: Connection, paper_id: int) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT * FROM paper WHERE id = :id"),
        {"id": paper_id},
    ).mappings().one()
    return dict(row)


def _update_target_paper(
    conn: Connection,
    target_id: int,
    source: Mapping[str, Any],
    doi: str,
    dedup_key: str,
) -> int:
    target = _paper_by_id(conn, target_id)
    values: dict[str, Any] = {
        "id": target_id,
        "doi": doi,
        "dedup_key": dedup_key,
    }
    assignments = ["doi = :doi", "dedup_key = :dedup_key", "updated_at = now()"]
    typed_params = []

    for field in _PAPER_FILL_FIELDS:
        if _is_missing(target.get(field)) and not _is_missing(source.get(field)):
            values[field] = source[field]
            assignments.append(f"{field} = :{field}")
            if field in {"creators", "csl_json"}:
                typed_params.append(bindparam(field, type_=JSON))

    stmt = text(f"UPDATE paper SET {', '.join(assignments)} WHERE id = :id")
    if typed_params:
        stmt = stmt.bindparams(*typed_params)
    return conn.execute(stmt, values).rowcount or 0


def _merge_paper_tag(conn: Connection, target_id: int, source_id: int) -> int:
    deleted = conn.execute(text(
        """
        DELETE FROM paper_tag src
        USING paper_tag dst
        WHERE src.paper_id = :source_id
          AND dst.paper_id = :target_id
          AND dst.tag_id = src.tag_id
        """
    ), {"target_id": target_id, "source_id": source_id}).rowcount or 0
    updated = conn.execute(text(
        "UPDATE paper_tag SET paper_id = :target_id WHERE paper_id = :source_id"
    ), {"target_id": target_id, "source_id": source_id}).rowcount or 0
    return deleted + updated


def _merge_simple_reference(conn: Connection, table: str, target_id: int, source_id: int) -> int:
    return conn.execute(
        text(f"UPDATE {table} SET paper_id = :target_id WHERE paper_id = :source_id"),
        {"target_id": target_id, "source_id": source_id},
    ).rowcount or 0


def _choose_project_status(target: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    target_status = target.get("inclusion_status") or "candidate"
    source_status = source.get("inclusion_status") or "candidate"
    if target_status == "candidate" and source_status != "candidate":
        return str(source_status)
    return str(target_status)


def _merge_project_paper(conn: Connection, target_id: int, source_id: int) -> int:
    affected = 0
    source_rows = conn.execute(text(
        """
        SELECT id, project_id, inclusion_status, exclusion_reason, screening_score,
               screening_notes, added_by, "order"
        FROM project_paper
        WHERE paper_id = :source_id
        ORDER BY id
        """
    ), {"source_id": source_id}).mappings().all()
    for source_row_raw in source_rows:
        source_row = dict(source_row_raw)
        target_row_raw = conn.execute(text(
            """
            SELECT id, project_id, inclusion_status, exclusion_reason, screening_score,
                   screening_notes, added_by, "order"
            FROM project_paper
            WHERE project_id = :project_id AND paper_id = :target_id
            """
        ), {"project_id": source_row["project_id"], "target_id": target_id}).mappings().one_or_none()
        if target_row_raw is None:
            affected += conn.execute(text(
                "UPDATE project_paper SET paper_id = :target_id WHERE id = :id"
            ), {"target_id": target_id, "id": source_row["id"]}).rowcount or 0
            continue

        target_row = dict(target_row_raw)
        order_values = [
            value for value in (target_row.get("order"), source_row.get("order"))
            if value is not None
        ]
        merged = {
            "id": target_row["id"],
            "inclusion_status": _choose_project_status(target_row, source_row),
            "exclusion_reason": (
                target_row.get("exclusion_reason") or source_row.get("exclusion_reason")
            ),
            "screening_score": (
                target_row.get("screening_score")
                if target_row.get("screening_score") is not None
                else source_row.get("screening_score")
            ),
            "screening_notes": (
                target_row.get("screening_notes") or source_row.get("screening_notes")
            ),
            "added_by": target_row.get("added_by") or source_row.get("added_by") or "user",
            "order": min(order_values) if order_values else 0,
        }
        affected += conn.execute(text(
            """
            UPDATE project_paper
            SET inclusion_status = :inclusion_status,
                exclusion_reason = :exclusion_reason,
                screening_score = :screening_score,
                screening_notes = :screening_notes,
                added_by = :added_by,
                "order" = :order
            WHERE id = :id
            """
        ), merged).rowcount or 0
        affected += conn.execute(
            text("DELETE FROM project_paper WHERE id = :id"),
            {"id": source_row["id"]},
        ).rowcount or 0
    return affected


def _merge_corpus_paper(conn: Connection, target_id: int, source_id: int) -> int:
    affected = 0
    source_rows = conn.execute(text(
        "SELECT id, corpus_id FROM corpus_paper WHERE paper_id = :source_id ORDER BY id"
    ), {"source_id": source_id}).mappings().all()
    for source_row in source_rows:
        exists = conn.execute(text(
            """
            SELECT 1 FROM corpus_paper
            WHERE corpus_id = :corpus_id AND paper_id = :target_id
            """
        ), {"corpus_id": source_row["corpus_id"], "target_id": target_id}).first()
        if exists:
            affected += conn.execute(
                text("DELETE FROM corpus_paper WHERE id = :id"),
                {"id": source_row["id"]},
            ).rowcount or 0
        else:
            affected += conn.execute(text(
                "UPDATE corpus_paper SET paper_id = :target_id WHERE id = :id"
            ), {"target_id": target_id, "id": source_row["id"]}).rowcount or 0
    return affected


def _merge_paper_extraction(conn: Connection, target_id: int, source_id: int) -> int:
    source = conn.execute(
        text("SELECT * FROM paper_extraction WHERE paper_id = :source_id"),
        {"source_id": source_id},
    ).mappings().one_or_none()
    if source is None:
        return 0

    target = conn.execute(
        text("SELECT * FROM paper_extraction WHERE paper_id = :target_id"),
        {"target_id": target_id},
    ).mappings().one_or_none()
    if target is None:
        return conn.execute(text(
            "UPDATE paper_extraction SET paper_id = :target_id WHERE paper_id = :source_id"
        ), {"target_id": target_id, "source_id": source_id}).rowcount or 0

    source_row = dict(source)
    target_row = dict(target)
    assignments = []
    values = {"id": target_row["id"], "source_id": source_id}
    typed_params = []
    for field in _EXTRACTION_FILL_FIELDS:
        if _is_missing(target_row.get(field)) and not _is_missing(source_row.get(field)):
            assignments.append(f"{field} = :{field}")
            values[field] = source_row[field]
            if field == "raw":
                typed_params.append(bindparam("raw", type_=JSON))
    affected = 0
    if assignments:
        stmt = text(
            f"UPDATE paper_extraction SET {', '.join(assignments)} WHERE id = :id"
        )
        if typed_params:
            stmt = stmt.bindparams(*typed_params)
        affected += conn.execute(stmt, values).rowcount or 0
    affected += conn.execute(
        text("DELETE FROM paper_extraction WHERE paper_id = :source_id"),
        {"source_id": source_id},
    ).rowcount or 0
    return affected


def _merge_paper_external_id(conn: Connection, target_id: int, source_id: int) -> int:
    affected = 0
    source_rows = conn.execute(text(
        """
        SELECT id, provider, id_type, external_id
        FROM paper_external_id
        WHERE paper_id = :source_id
        ORDER BY id
        """
    ), {"source_id": source_id}).mappings().all()
    for source_row in source_rows:
        exists = conn.execute(text(
            """
            SELECT 1 FROM paper_external_id
            WHERE paper_id = :target_id
              AND provider = :provider
              AND id_type = :id_type
              AND external_id = :external_id
            """
        ), {
            "target_id": target_id,
            "provider": source_row["provider"],
            "id_type": source_row["id_type"],
            "external_id": source_row["external_id"],
        }).first()
        if exists:
            affected += conn.execute(
                text("DELETE FROM paper_external_id WHERE id = :id"),
                {"id": source_row["id"]},
            ).rowcount or 0
        else:
            affected += conn.execute(text(
                "UPDATE paper_external_id SET paper_id = :target_id WHERE id = :id"
            ), {"target_id": target_id, "id": source_row["id"]}).rowcount or 0
    return affected


def _merge_one(conn: Connection, merge: Mapping[str, Any]) -> dict[str, int]:
    target_id = int(merge["target_id"])
    doi_source_id = int(merge["doi_source_id"])
    # 删除前取回全部源行：元数据按「DOI 源优先，其余按完整度降序」逐字段补空，
    # 否则 3+ 行的组里非 DOI 源行独有的 abstract/keywords 等会随删除丢失
    source_rows = [_paper_by_id(conn, int(sid)) for sid in merge["source_ids"]]
    ordered_sources = sorted(
        source_rows,
        key=lambda row: (int(row["id"]) != doi_source_id, -_completeness_score(row)),
    )
    merged_fill: dict[str, Any] = {}
    for row in ordered_sources:
        for field in _PAPER_FILL_FIELDS:
            if _is_missing(merged_fill.get(field)) and not _is_missing(row.get(field)):
                merged_fill[field] = row[field]
    affected = dict.fromkeys((*_REFERENCE_TABLES, "paper", "paper_metadata"), 0)

    for source_id in merge["source_ids"]:
        source_id = int(source_id)
        affected["paper_tag"] += _merge_paper_tag(conn, target_id, source_id)
        affected["note"] += _merge_simple_reference(conn, "note", target_id, source_id)
        affected["attachment"] += _merge_simple_reference(conn, "attachment", target_id, source_id)
        affected["project_paper"] += _merge_project_paper(conn, target_id, source_id)
        affected["corpus_paper"] += _merge_corpus_paper(conn, target_id, source_id)
        affected["paper_extraction"] += _merge_paper_extraction(conn, target_id, source_id)
        affected["paper_external_id"] += _merge_paper_external_id(conn, target_id, source_id)

    # 先迁移引用并删除 DOI 源行，再把目标行升级到 DOI dedup_key，避免唯一键冲突。
    for source_id in merge["source_ids"]:
        affected["paper"] += conn.execute(
            text("DELETE FROM paper WHERE id = :source_id"),
            {"source_id": int(source_id)},
        ).rowcount or 0

    affected["paper_metadata"] += _update_target_paper(
        conn,
        target_id=target_id,
        source=merged_fill,
        doi=str(merge["doi"] or ""),
        dedup_key=str(merge["dedup_key"]),
    )
    return affected


def merge_duplicate_papers(
    conn: Connection,
    *,
    dry_run: bool = False,
    output: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """执行或报告双轨重复合并。

    dry_run=True 时只生成报告，不写库。
    """
    plan = plan_paper_dedup_merges(_fetch_papers(conn))
    report: dict[str, Any] = {
        "dry_run": dry_run,
        "merge_count": len(plan["merges"]),
        "merges": [],
        "skipped": plan["skipped"],
        "totals": dict.fromkeys((*_REFERENCE_TABLES, "paper", "paper_metadata"), 0),
    }

    for merge in plan["merges"]:
        item = dict(merge)
        item["reference_counts"] = _reference_counts(conn, list(merge["source_ids"]))
        if dry_run:
            item["affected"] = dict.fromkeys((*_REFERENCE_TABLES, "paper", "paper_metadata"), 0)
        else:
            item["affected"] = _merge_one(conn, merge)
            for table, count in item["affected"].items():
                report["totals"][table] += count
        report["merges"].append(item)

    if output is not None:
        output(json.dumps(report, ensure_ascii=False, default=str, indent=2))
    return report
