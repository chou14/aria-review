# services/r-analysis

bibliometrix 分析内核, 以 plumber HTTP 服务暴露 (D4)。**仅供 agent 后端内部调用**, 不直接面向前端。

## 结构
- `R/analysis.R` — 纯分析函数 (移植自 legacy `R/fct_analysis.R`), 返回与 `packages/contracts` 对齐的 JSON-able list (Codex step1-P1: 契约 ≠ R 对象)。
- `R/store.R` — 语料存取 + 状态机 (parsing/ready/failed), 原子写 (Codex #5), RDS 仅系统产物 (Codex #18)。
- `plumber.R` — 薄 HTTP 层: `/healthz` `/parse` `/corpus/<id>` `/corpus/<id>/overview`。
- `entrypoint.R` — 启动。

## 端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | /healthz | 存活 |
| POST | /parse (multipart: file + dbsource) | 解析→存储, 返回 corpus meta |
| GET  | /corpus/{id} | 语料状态 |
| GET  | /corpus/{id}/overview | 概览 (仅 ready) |

## 本地运行
```bash
docker compose --profile analysis up -d --build r-analysis
```

R 分析服务为 Docker-only 支持路径。依赖由 `renv.lock` 锁定并在镜像构建时通过 `renv::restore()` 还原；关键顶层包版本为 bibliometrix 5.4.0、plumber 1.2.1、httr2 1.0.0、jsonlite 2.0.0、digest 0.6.34、Matrix 1.6-5。

## 测试 (不需要 plumber)
```bash
# 从仓库根。维护者可在已还原 renv.lock 的 R 环境或 CI 镜像内执行。
Rscript -e 'testthat::test_dir("services/r-analysis/tests/testthat")'
```
纯函数 (analysis/store) 全部可测; plumber HTTP 层薄, 靠集成测试覆盖。

## 待办 (设计 §12)
- RDS → parquet + 明确 schema (RDS 绑 R 版本)。
- 内存态 plumber + LRU (Codex #3); 现为每请求磁盘载入。
- 其余 7 个分析端点 (sources/authors/.../prisma)。
