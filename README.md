<div align="center">

# 🔭 Aria Review

### 可信文献综述 Agent 工作台

**让 AI 写的每一句综述，都能追回真实的原文证据。**

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![R](https://img.shields.io/badge/R-4.3+-276DC3?logo=r&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-779%20passing-brightgreen)
![Demo](https://img.shields.io/badge/demo-zero--key-success)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-ff69b4)

[English](./README.en.md) · **简体中文** · [60 秒上手](#-60-秒上手) · [架构](#%EF%B8%8F-架构) · [路线图](#%EF%B8%8F-路线图)

</div>

---

> ### 别的 Agent 给你一个答案，Aria 给你一条可验证的研究路径。

<p align="center">
  <img src="assets/review-provenance.png" width="90%" alt="可溯源综述：点击综述里的引用，右栏定位并高亮原文 Markdown 块，标注页码与表号">
</p>

<div align="center"><sub>综述里的引用 <code>[1]</code> 点一下 → 右栏定位到原文那一块，连第几页第几张表都标着。把「相信我」做成「你来验」。</sub></div>

**Aria Review**（工程代号 BiblioCN）面向研究者，把 **文献检索 → 全文解析 → 文献计量 → AI 综述 → 引用核验 → 原文溯源 → 报告导出** 收进同一个可复现系统。它的设计目标只有一个：

**综述里的每一个论断，都能追回真实文献、被你亲手核验。** 而且零外部 API key 也能把整条 demo 跑通。

---

## 💡 为什么需要 Aria

今天的 AI 综述，大多死在三件事上：

| 症状 | 后果 |
|---|---|
| **编造引用** —— 引用一篇语料里根本不存在的文献 | 一条假引用，整篇综述不可信 |
| **结果数据当装饰** —— 把数字抄进正文，却不绑定来源 | 数据无法复核，等于没有 |
| **罗列多于论证** —— 堆叠"谁做了什么"，不回答"还差什么" | 读者得不到研究判断 |

三者共用一个病根：**不可验证**。

而研究最贵的那一步判断——「这个方向**真有价值、又还没人做过**吗」——恰恰建立在综述之上。综述一旦不可信，下游的找空白、判价值，全都立不住。

**Aria 的回答不是"看起来更对"，而是把结论做成可被你亲手验证的**：读取方案不是朴素 RAG，引用经确定性反查，运行全程留痕、可离线重算。

---

## 🔁 核心理念：一条可验证的研究加速闭环

```
        ┌────────────────────── ④ 的判断回流到 ① ──────────────────────┐
        │                                                              │
        ▼                                                              │
   ① 多源检索  ───▶   ② 可信综述   ───▶   ③ 找研究空白   ───▶   ④ 验研究价值
   OpenAlex          ★ 核心环 ★          从可信证据矩阵        新颖性 · 可行性
   Sciverse        句句可溯源·零伪造        派生 · 可回溯           · 可核验
```

整条链的可信，**全压在 ② 这一环**：只有综述本身可验证，下游的「研究空白」与「研究价值」判断才立得住。所以 Aria 把绝大部分工程，都投在了「让 ② 真正可信」上。

这就是我们理解的 **AI for Science**：让 AI 参与科研的全过程，而**每一步都可被验证**。

---

## 🛡️ 凭什么可信：把「相信我」做成「你来验」

### 1. 结构化解析 ≠ RAG

写一篇能被核对的综述，光靠 top-k 相似片段不够。Aria 对每篇纳入文献做**全文结构化解析**，而不是切块嵌入：

| 维度 | 朴素 RAG | Aria 的读取方案 |
|---|---|---|
| 处理单位 | 文本切块 + 向量嵌入 | MinerU 把全文拆成 段 / 表 / 图 / 公式 结构块 |
| 结果表格 | 可能被切碎 | **整张表格保留** |
| 证据锚点 | 近似 top-k 相似片段 | 每个抽取值带**页 / 块锚点**，点得回原文 |
| 擅长 | 快速定位片段 | 综述的**事实底座** |
| 在 Aria 中的角色 | 仍用于快速证据发现 | 综述事实底座建立在结构化解析之上 |

Agent 顺着结构**逐块精读**——读摘要抽「发现」、读方法抽「方法」、读结果表抽「数据」，每一条都标着第几页第几张表。整篇读完，就是可溯源证据矩阵里的一行。

### 2. 三件确定性工程

可信不是靠模型「自觉」，而是靠纯代码做的确定性校验：

| 工程 | 做什么 | 你能验证什么 |
|---|---|---|
| **`cite_check`** | 纯代码逐条反查综述里的每条引用 | 注入一条假引用 → **确定性标红、校验 FAIL** |
| **证据哈希** | 把每个抽取的数绑死到源文献 | 数据可溯回原文，不能被悄悄篡改 |
| **RunLog 哈希链** | 记录事件链、工具调用、证据引用与最终输出 | **离线把整条执行重算一遍** |

> 读和抽交给 AI，反查和溯源交给代码 —— **写验分离**。

### 3. 句句可溯源

综述里的引用 `[4]`，点一下，右栏定位到那篇文献的原文 Markdown 并高亮，连第几页第几张表都标着。读者点一下就能自己核对。

---

## ✨ 核心能力

| 能力 | 说明 |
|---|---|
| 🔑 **零 key 一键 demo** | `docker compose run --rm demo` 用内置样例语料 + 确定性 LLM，产出可校验 RunLog，全程不需任何外部 API key |
| 🔗 **可溯源综述** | 综述里的引用 / 数据可点击回到原文 Markdown 段落、表格或结构块 |
| 🚫 **零伪造约束** | GuardedStream + 引用校验把伪造引用标红，不把不可验证内容伪装成可信结果 |
| 📜 **可验证运行日志** | `runlog/v1` 哈希链记录事件、工具调用、证据引用与最终输出，可独立离线校验 |
| 📈 **文献计量分析** | R plumber + bibliometrix：来源、作者、关键词、合作网络、PRISMA 流程图 |
| 🧭 **研究副驾** | GAP 发现、价值核验、证据包与人工确认闭环，裁决由确定性 resolver 汇总 |
| 🔍 **多源检索** | OpenAlex + Sciverse 路由，按主题检索、候选自筛、归一化键去重入库 |
| 🐳 **三服务部署** | React 前端 + FastAPI Agent + R 分析 + Postgres，Docker Compose 一键编排 |

---

## 📊 实测家底

> 以下数据在一个真实的系统综述案例上跑出，分母按真实文档对象计——每个数都立得住。

- ✅ **779** 项离线测试全绿（排除真实 LLM 实时调用的口径）
- ✅ **130** 篇候选一次去重入库、零跳过
- ✅ **23** 条带页 / 块锚点的原文溯源，一次运行产出
- ✅ **0** 条伪造引用放行

---

## 📸 产品一览

<table>
<tr>
<td width="50%" valign="top">
<img src="assets/bibliometric-overview.png" alt="文献计量分析"><br>
<sub><b>📈 文献计量分析</b><br>领域概览、年度产出趋势，以及「作者 → 关键词 → 来源」三字段流向图，由 bibliometrix 驱动。</sub>
</td>
<td width="50%" valign="top">
<img src="assets/ai-review.png" alt="AI 可信综述"><br>
<sub><b>🧠 AI 可信综述</b><br>结构化生成的综述正文，论点有据、引用经核验、可逐条溯源回原文。</sub>
</td>
</tr>
</table>

---

## ⚡ 60 秒上手

前置条件：Docker + Docker Compose v2。

```bash
git clone https://github.com/niuniu-869/aria-review.git
cd aria-review

# 零 key 一键 demo：离线样例语料 + 确定性 LLM，产出可校验 RunLog
docker compose run --rm --build demo
```

零 key、全新容器的**预期结果**：RunLog 7 项校验通过、最终裁决 `PASS`，并产出 grounding / zero-fabrication 指标。

启动工作台：

```bash
docker compose up -d --build
curl http://localhost:8000/healthz        # Agent 健康检查
# 打开 http://localhost:8080               # 前端工作台
```

默认启动 `web + agent + postgres`，足够体验项目创建、文献库、设置页、AI 工具的无 key 回退等流程。需要**上传解析、文献计量图谱**等完整分析能力时，再启动较重的 R 服务（首次从源码构建可能 20 分钟以上）：

```bash
docker compose --profile analysis up -d --build
```

> Postgres 默认只暴露到宿主 `127.0.0.1:55432`，避免和本机 `5432` 冲突。改端口在根目录 `.env` 写 `POSTGRES_PORT=55433`。

工作台冒烟验证、可选环境变量与完整命令见 [本地开发](#-本地开发) 与 [验证](#-验证)。

---

## 🏗️ 架构

```
                       浏览器  ·  apps/web (React + Vite + TypeScript)
                                      │  REST / SSE
                                      ▼
        ┌──────────────────────────────────────────────────────────┐
        │  services/agent  ·  FastAPI                                │
        │  Agent 循环 · RunLog 哈希链 · 引用核验 · 多源检索 · 综述   │
        └───────────────┬────────────────────────────┬──────────────┘
                        │                            │ projects · papers
          结构化解析 /  │                            │ attachments · runs · gaps
          bibliometrix  ▼                            ▼
                ┌───────────────────┐        ┌──────────────────┐
                │ services/         │        │   PostgreSQL     │
                │ r-analysis        │        └──────────────────┘
                │ R + plumber +     │
                │ bibliometrix      │
                └───────────────────┘
```

| 路径 | 内容 |
|---|---|
| `apps/web` | 前端工作台、Playwright E2E、Vitest 单测 |
| `services/agent` | FastAPI 后端、Agent 工具、综述与安全校验、迁移、pytest |
| `services/r-analysis` | R 分析服务、OpenAlex 接入、bibliometrix 分析 |
| `packages/contracts` | OpenAPI 契约——前后端类型的单一真源 |
| `legacy-shiny` | 历史 Shiny 版本快照 |

> 仓库**不提交**本地演示材料、验证截图、运行输出、benchmark 结果、demo 语料或测试数据——这些统一由 `.gitignore` 保留在本地。离线 demo 使用脚本内置样例语料，不依赖任何提交进仓库的数据文件。

---

## 🧑‍💻 本地开发

| 工具 | 建议版本 |
|---|---|
| Docker Compose | v2+ |
| Node.js / pnpm | Node 20+ / pnpm 9.15.9 |
| Python | 3.12 |
| R | 4.3+（仅 R 分析服务测试需要）|

**前端：**

```bash
pnpm -C apps/web install
pnpm -C apps/web dev          # http://localhost:5173
```

**Agent（需先启动 Postgres）：**

```bash
docker compose up -d postgres
cd services/agent
python3 -m pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://bibliocn:bibliocn@localhost:55432/bibliocn
export R_ANALYSIS_URL=http://localhost:8001
python scripts/wait_for_db.py --timeout 60
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**R 分析服务：**

```bash
docker compose --profile analysis up -d --build r-analysis
```

> R 分析服务为 **Docker-only 支持路径**。镜像基于 `services/r-analysis/renv.lock` 通过 `renv::restore()` 还原依赖，锁定 R 4.3.3、bibliometrix 5.4.0、plumber 1.2.1、httr2 1.0.0、jsonlite 2.0.0、digest 0.6.34、Matrix 1.6-5 及其递归依赖；不再支持未锁定的本机 R 包安装路径。

> 本地若让 Agent 读取服务内 `.env`，放在 `services/agent/.env`（Docker Compose 用仓库根 `.env`）。排查复现问题时先确认是否存在 `services/agent/.env`，它会覆盖本地命令的默认 key 与数据库地址。
>
> `services/agent/requirements.txt` 是人工维护的顶层依赖声明；`services/agent/requirements.lock` 是由当前 Python 3.12 虚拟环境 `pip freeze` 生成的复现基线，排查环境差异时优先对照 lock。

### 环境变量

```bash
cp .env.example .env
```

用户必填项：无。根目录 `.env` 供 Docker Compose 使用；本地直接运行 Agent 时，可复制 `services/agent/.env.example` 为 `services/agent/.env`。不配置 key 时系统走离线或确定性回退路径，仍能跑通 demo。用户的 LLM / Sciverse / Image key 可通过请求头或环境变量提供，**不写入数据库、不回显**。

`services/agent/app/config.py` 实际读取的变量如下：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `R_ANALYSIS_URL` | `http://localhost:8001` | Agent 调用 R 分析服务的地址；Compose 默认覆盖为 `http://r-analysis:8001` |
| `R_REQUEST_TIMEOUT` | `120` | 常规 R 分析请求超时秒数 |
| `R_INGEST_TIMEOUT` | `300` | OpenAlex / 参考文献摄取等长请求超时秒数 |
| `R_HEALTH_TIMEOUT` | `5` | R 分析服务健康检查超时秒数 |
| `MAX_UPLOAD_BYTES` | `52428800` | 上传文件大小上限，默认 50 MiB |
| `CORS_ORIGINS` | `http://localhost:8080,http://localhost:5173` | 逗号分隔的 Agent CORS 允许来源；Compose 默认 `http://localhost:8080` |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 兼容 LLM key；为空时使用 FakeLLM / 确定性回退 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek 兼容 LLM API 地址 |
| `BIBLIOCN_ALLOW_PRIVATE_API_BASE_URLS` | 空 | 默认拒绝 LLM / Sciverse / Image 等用户可配 Base URL 指向 localhost、内网 IP 或 `.local`；确需连接内网兼容 LLM 时设为 `1` / `true` / `yes` / `on` |
| `REVIEW_RECORDS_LIMIT` | `40` | 综述生成读取的记录数量上限 |
| `DATABASE_URL` | `postgresql+asyncpg://bibliocn@localhost/bibliocn` | Agent 主数据库连接；Compose 默认指向容器内 Postgres |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://bibliocn@localhost/bibliocn_test` | Agent 测试数据库连接 |
| `OCR_AUTHORIZATION_TOKEN` | 空 | MinerU OCR 授权 token；为空时真实全文解析能力不可用 |
| `MINERU_BASE_URL` | `https://mineru.net/api/v4` | MinerU OCR API 地址 |
| `SCIVERSE_BASE_URL` | `https://api.sciverse.space` | Sciverse 检索 / 全文 API 地址 |
| `SCIVERSE_API_TOKEN` | 空 | Sciverse API token；为空时 Sciverse 路径不可用，OpenAlex 仍可用 |
| `SCIVERSE_TIMEOUT` | `60` | Sciverse 请求超时秒数 |
| `SCIVERSE_CONTENT_CHUNK_CHARS` | `7000` | Sciverse 全文分块字符数 |
| `SCIVERSE_CONTENT_MAX_CHARS` | `500000` | Sciverse 单篇全文最大保留字符数 |
| `IMAGE_API_KEY` | 空 | OpenAI 兼容生图 key；为空时使用 SVG fallback 或仅保存提示词 |
| `IMAGE_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容生图 API 地址 |
| `IMAGE_MODEL` | `gpt-image-1` | 生图模型名 |
| `IMAGE_SIZE` | `1024x1024` | 生图尺寸 |
| `BIBLIOCN_CORPORA_DIR` | `/tmp/bibliocn_corpora` | 全文 Markdown、RunLog 与指标等语料缓存目录；Compose 默认 `/data/corpora` |

R 分析服务另读一个 OpenAlex 礼貌池变量：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `OPENALEX_EMAIL` | `aria-review@users.noreply.github.com` | R 分析服务请求 OpenAlex 时使用的 `mailto` 联系邮箱；根目录 `.env` 会透传给 `r-analysis` |

---

## 🔬 验证

提交前推荐至少跑：

```bash
docker compose config -q
pnpm -C apps/web test
pnpm -C apps/web build
cd services/agent && \
  DATABASE_URL=postgresql+asyncpg://bibliocn:bibliocn@localhost:55432/bibliocn \
  TEST_DATABASE_URL=postgresql+asyncpg://bibliocn:bibliocn@localhost:55432/bibliocn_test \
  python3 -m pytest -q
```

> Agent 测试需可连接的 Postgres。Compose 会自动创建 `bibliocn` 与 `bibliocn_test` 两个库；先 `docker compose up -d postgres` 再跑 pytest。旧卷缺 `bibliocn_test` 时执行 `docker compose exec postgres createdb -U bibliocn bibliocn_test` 补建。

R 侧测试：

```bash
Rscript -e 'testthat::test_dir("services/r-analysis/tests/testthat")'
```

独立校验 demo RunLog（这正是「你来验」的入口）：

```bash
docker compose run --rm agent python scripts/verify_runlog.py \
  /data/corpora/demo_runlog.json \
  --corpus-hashes /data/corpora/demo_corpus_hashes.json
```

---

## 🔒 安全与隐私

- 用户的 LLM / Sciverse / Image key 通过请求头透传，**不写入数据库、不回显**。
- `.env` 与备份环境文件默认被忽略，示例文件只含占位符。**请勿提交** `.env`、API key、含密码的数据库 URL、私钥或复制的请求头。
- 综述输出不直接信任 LLM，引用会经过 citation / grounding 校验。
- RunLog 哈希链只证明事件**自洽**。若需防篡改，请把 `chain_head` 写入外部不可变存储或签名系统。

安全问题请按 [SECURITY.md](SECURITY.md) **私下报告**，不要开公开 issue。

---

## 🗺️ 路线图

| 阶段 | 状态 |
|---|---|
| ② 可信综述内核（可溯源 / 零伪造 / RunLog 哈希链） | ✅ 已落地 · 本项目核心 |
| ① 多源检索（OpenAlex + Sciverse 归一化去重入库） | ✅ 已落地 |
| ③ 找研究空白（综述内建「研究分歧与空白」「未来方向」，每条从证据矩阵派生、可回溯） | ✅ 已内建 |
| ④ 验研究价值（综述内建「研究空白与本研究价值」论证章节） | ✅ 已内建 |
| 更深的**自动新颖性检验**（把 ④ 的反查做成独立可核验模块） | 🚧 下一站 |
| 内核迁移（情报研判 / 规范解析 / 语料质检等领域无关场景） | 🔭 探索中 |

> 我们坦诚标注边界：③④ 已以综述章节形式内建并可回溯到原文；更深的**自动新颖性检验**是正在推进的下一站，不夸大。「可验证」精确指三件——引用存在、证据可溯、日志可离线重算；语义正确性由人在环上复核兜底，从不声称「证明结论一定对」。

---

## 🤝 贡献

欢迎改进 Aria。请先读 [CONTRIBUTING.md](CONTRIBUTING.md)：保持改动聚焦、沿用既有模式、API 形状变更时同步更新 `packages/contracts/openapi.yaml` 与生成类型、**绝不提交 `.env` 或 API key**。

## 📚 文档

- [Monorepo 说明](MONOREPO.md) · [贡献指南](CONTRIBUTING.md) · [安全策略](SECURITY.md) · [许可证](LICENSE)

## 📄 许可证

[MIT License](LICENSE)。

---

<div align="center">

**让 AI 参与科研的全过程，而每一步都可被验证。**

<sub>Built for researchers who need to trust what the AI wrote.</sub>

</div>
