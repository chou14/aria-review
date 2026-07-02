# Paper 双轨去重存量合并迁移设计

## 背景

当前 `compute_dedup_key` 使用两条轨道：

- 有 DOI：`doi:<normalized_doi>`
- 无 DOI：`title:<sha256(normalized_title)[:32]>`

历史数据中，同一文献可能先以无 DOI 的标题轨入库，随后带 DOI 再导入为 DOI 轨，形成两行 `paper`。本迁移只修复这类“双轨重复”，不尝试解决所有题录质量问题。

## 重复行识别规则

自动合并的同一文献必须同时满足：

1. `owner_id` 相同，含 `NULL` owner 的全局库单独成组。
2. `title` 经过与 `compute_dedup_key` 标题轨一致的规范化后相同：NFC 归一、转小写、移除 `\W+`。
3. 同组内至少存在一行 DOI 为空，且至少存在一行 DOI 非空。
4. 同组内只有一个规范化 DOI 值。若同标题存在多个不同 DOI，视为不同文献或歧义数据，迁移跳过并在报告中列出。

保留行选择：

- 优先保留 DOI 为空的标题轨旧行，因为它通常是最早入库、已被项目/笔记/附件引用的库内身份。
- 若存在多个 DOI 为空行，优先保留 `dedup_key` 等于标题轨 key 的行；再按信息完整度高、`created_at` 早、`id` 小排序。
- 从 DOI 行回填 `doi` 与 DOI 轨 `dedup_key` 到保留行；其他题录字段只在保留行为空时补齐，避免覆盖人工修订。

## 引用表确认

已用 `rg "paper_id|ForeignKey"` 核对 ORM 与迁移，关系型 `paper_id` 引用表为：

- `paper_tag`
- `note`
- `attachment`
- `project_paper`
- `corpus_paper`
- `paper_extraction`
- `paper_external_id`

`rg` 还会命中运行日志、证据包、scratchpad 等 JSON 内的 `paper_id` 文本字段；这些不是外键引用，本迁移不改写历史审计/证据 JSON。

## 各表迁移策略

`paper_tag`

- 唯一约束：复合主键 `(paper_id, tag_id)`。
- 策略：若目标 paper 已有同 tag，删除源关联；否则将源关联 `paper_id` 改为目标 paper。

`note`

- 唯一约束：无。
- 策略：所有源 note 直接重指向目标 paper。`paper_id` 可空不影响本迁移。

`attachment`

- 唯一约束：无。
- 策略：所有源附件直接重指向目标 paper，保留路径、状态、Markdown 路径等附件语义。

`project_paper`

- 唯一约束：`uq_project_paper(project_id, paper_id)`。
- 策略：若同项目中目标 paper 已有关联，先把源关联的筛选信息合并进目标关联，再删除源关联；若无冲突，直接重指向目标 paper。
- 冲突合并规则：目标状态为 `candidate` 且源状态更具体时采用源状态；`exclusion_reason`、`screening_score`、`screening_notes` 仅在目标为空时补齐；`order` 取较小值。

`corpus_paper`

- 唯一约束：`uq_corpus_paper(corpus_id, paper_id)`。
- 策略：语料快照的 `csl_json_snapshot`、`record_hash`、排序等语义保持不动；无冲突时只重指 `paper_id`。若同一 corpus 中源/目标都存在，删除源快照行以满足唯一约束，保留目标快照行。
- 注意：`corpus_paper.paper_id` 不级联，本迁移在删除源 `paper` 前显式处理，避免悬挂引用。

`paper_extraction`

- 唯一约束：`paper_id` 唯一。
- 策略：若目标无抽取结果，源抽取结果重指向目标；若目标已有抽取结果，目标字段为空时从源补齐，然后删除源抽取结果。

`paper_external_id`

- 唯一约束：`uq_paper_external_id_paper(paper_id, provider, id_type, external_id)`。
- 策略：若目标 paper 已有相同外部 ID，删除源外部 ID；否则重指向目标 paper。

`paper`

- 唯一约束：`uq_paper_dedup(dedup_key, owner_id)` 与 `uq_paper_dedup_null_owner(dedup_key WHERE owner_id IS NULL)`。
- 策略：先迁移/去冲突所有引用表，再删除 DOI 源行，最后将保留行更新为 DOI 轨 `dedup_key`。这个顺序避免保留行更新时撞上源行已有的 DOI key。

## Dry-run 模式

迁移脚本支持两种 dry-run 开关：

- Alembic 参数：`alembic -x dry_run=true upgrade head`
- 环境变量：`DEDUP_MERGE_DRY_RUN=1 alembic upgrade head`

dry-run 只输出报告，不写库。报告包含：

- 每组将合并的 `target_id`、`source_ids`、`doi`、`dedup_key`。
- 每个引用表将受影响的源行数量。
- 因多个不同 DOI 同标题而跳过的歧义组。

默认模式执行合并。`downgrade` 为 no-op，因为合并会删除源 `paper.id`，历史引用无法无损拆回。
