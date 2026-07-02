import type { LlmRequestOptions } from "../api/client";
import type { ProjectDetail } from "../api/agentHooks";
import type { RCorpusId } from "../api/corpusIds";
import { REVIEW_TYPES, useReviewJob } from "../hooks/useReviewJob";
import { ReviewWithProvenance } from "./review/ReviewWithProvenance";
import { downloadMarkdown } from "../lib/download";
import {
  AiPanel,
  AiToolbar,
  AiField,
  AiTextInput,
  AiMarkdown,
  AiEmpty,
  AiError,
  AiKeyNotice,
} from "./ai";

export function ReviewPanel({
  projectId,
  corpusId,
  // M5: 可选 LLM 配置 prop，由父组件从 useLlmSettings 读取后注入（不改内部逻辑）
  llm,
  apiKey,
  projectStats,
}: {
  projectId: string;
  corpusId?: RCorpusId;
  llm?: LlmRequestOptions;
  apiKey?: string;
  projectStats?: Pick<ProjectDetail, "includedCount" | "readableFulltextCount">;
}) {
  const {
    type,
    setType,
    topic,
    setTopic,
    running,
    text,
    summary,
    annotated,
    provenanceMap,
    err,
    precheck,
    exportText,
    generate,
  } = useReviewJob({ projectId, corpusId, llm, apiKey, projectStats });

  function exportMarkdown() {
    if (!exportText) return;
    const typeLabel = REVIEW_TYPES.find(([v]) => v === type)?.[1] ?? type;
    // 剥离溯源锚点包裹标记(保留内部 [n] 引用), 否则原始 [[anchor:...]] 串泄漏进导出文本。
    const clean = exportText
      .replace(/\[\[anchor:[A-Za-z0-9_-]+\]\]/g, "")
      .replace(/\[\[\/anchor\]\]/g, "");
    downloadMarkdown(
      `AI综述-${typeLabel}-${projectId}`,
      `# AI综述导出\n\n- 论型：${typeLabel}\n- 主题：${topic || "未填写"}\n\n${clean}\n`,
    );
  }

  return (
    <AiPanel title="AI 综述写作" intro="按论型与主题流式生成综述，并对引用做语料核验。">
      <AiToolbar>
        <AiField label="论型" htmlFor="review-type">
          <select id="review-type" className="input" value={type} onChange={(e) => setType(e.target.value)}>
            {REVIEW_TYPES.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </AiField>
        <AiField label="研究主题" htmlFor="review-topic">
          <AiTextInput
            id="review-topic"
            value={topic}
            placeholder="例：人工智能在教育中的应用"
            onChange={(e) => setTopic(e.target.value)}
          />
        </AiField>
        <button
          type="button"
          className="btn btn-primary"
          onClick={generate}
          disabled={!topic.trim() || running || !!precheck}
          title={precheck ? precheck.message : undefined}
        >
          {running ? "生成中…" : "生成综述"}
        </button>
        <button type="button" className="btn" onClick={exportMarkdown} disabled={!exportText}>
          导出 Markdown
        </button>
      </AiToolbar>

      {precheck && (
        <p className="muted ai-empty" role="status">
          {precheck.message}：{precheck.detail}{" "}
          <a href={precheck.href}>{precheck.action}</a>
        </p>
      )}

      <AiKeyNotice hasKey={!!(llm?.apiKey || apiKey)} />

      <AiError message={err} />

      {/* 引用校验图例: 文字徽标 + 计数, 取代正文里难辨的裸 emoji */}
      {summary && (
        <div className="cite-legend" aria-live="polite">
          <span className="muted">引用校验</span>
          <span className="lg-item">
            <span className="badge badge-ok cite-mark" title="DOI/PMID 精确命中语料">已核验</span>
            <span className="lg-count tnum">{summary.green}</span>
          </span>
          <span className="lg-item">
            <span className="badge badge-warn cite-mark" title="作者+年模糊命中, 或编号待人工复核">待核</span>
            <span className="lg-count tnum">{summary.yellow}</span>
          </span>
          <span className="lg-item">
            <span className="badge badge-danger cite-mark" title="语料中未找到, 疑似虚构">存疑</span>
            <span className="lg-count tnum">{summary.red}</span>
          </span>
        </div>
      )}

      {/* dogfood A2: 轻量可信卡 —— 综述产出处直接呈现零伪造率+溯源覆盖(诚实空态)，
          不再让"可信"只停留在首页营销区。完整 grounding 指标(哈希链等)在历史 run 的 TrustCard。 */}
      {summary && (() => {
        const g = summary.green ?? 0;
        const y = summary.yellow ?? 0;
        const r = summary.red ?? 0;
        const total = g + y + r;
        const zeroFab = total > 0 ? Math.round(((g + y) / total) * 100) : null;
        const provCount = provenanceMap ? Object.keys(provenanceMap).length : 0;
        return (
          <div
            aria-live="polite"
            style={{ display: "flex", alignItems: "center", gap: "0.6rem", margin: "0.1rem 0 0.7rem" }}
          >
            <span
              className={`badge ${zeroFab === null ? "badge-warn" : r > 0 ? "badge-danger" : "badge-ok"}`}
              title="零伪造率 =（已核验+待核）/全部引用；红色为语料中找不到的伪造引用。无引用时不可评分；存在伪造时标红（codex A2-P3）。"
            >
              零伪造率 {zeroFab === null ? "不可评分" : `${zeroFab}%`}
            </span>
            <span className="muted" style={{ fontSize: "0.8rem" }}>
              共 {total} 处引用{provCount > 0 ? ` · ${provCount} 处可点击溯源原文` : ""}
            </span>
          </div>
        );
      })()}

      {/* 有溯源映射 → 可溯源综述(点引用跳原文页/段)优先，reviewMd 取 annotated||text；
          否则 annotated → 带引用徽标 markdown；再否则 text → 流式 markdown */}
      {provenanceMap && Object.keys(provenanceMap).length > 0 ? (
        <div className="ai-review-body">
          <ReviewWithProvenance
            projectId={Number(projectId)}
            reviewMd={annotated || text}
            provenanceMap={provenanceMap}
          />
        </div>
      ) : annotated ? (
        <div className="ai-review-body">
          <AiMarkdown content={annotated} projectId={projectId} />
        </div>
      ) : text ? (
        <div className="ai-review-body">
          <AiMarkdown content={text} streaming live projectId={projectId} />
        </div>
      ) : (
        !running && !err && <AiEmpty>填写研究主题并点击「生成综述」开始。</AiEmpty>
      )}
    </AiPanel>
  );
}
