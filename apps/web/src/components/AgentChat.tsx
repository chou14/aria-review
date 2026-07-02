// AgentChat — 对话输入框 + SSE 流接收 + RunTimeline 渲染 (P1-10)
// P2-3: 增加写操作确认开关 + ConfirmCard 批准/拒绝 + RunLog 下载。
// P2-4: 接入 onSearchResults → 渲染候选卡 SearchCandidateCards。
import { useEffect, useMemo } from "react";
import { useAgentRunStream } from "../hooks/useAgentRunStream";
import { RunTimeline } from "./RunTimeline";
import { ConfirmCard } from "./ConfirmCard";
import { SearchCandidateCards } from "./SearchCandidateCards";
import { ErrorBoundary } from "./ErrorBoundary";
import { ErrMsg } from "../lib/ui";
import { useLlmSettings } from "../api/useLlmSettings";
import { useSciverseSettings } from "../api/useSciverseSettings";

interface Props {
  projectId: number;
  /**
   * M4 (codex P2): run 完成时回调真实 runId + finalOutput + eventSeq,
   * 供上层(ChatWorkbench)据此创建工件。替代不可靠的 DOM MutationObserver 监听。
   */
  onRunComplete?: (info: { runId: string; finalOutput: string; eventSeq: number }) => void;
  /**
   * I-2: run 开始时（handleSubmit 启动）通知父级，父级可据此隐藏空状态引导。
   * 出错/取消后不重置，避免引导闪回。
   */
  onRunStart?: () => void;
  /**
   * W4 (Task 7-8): 填入预设/建议追问文本（受控注入，不自动发送）。
   * I-1 修复：使用 {text, seq} 对象；seq 每次点击都递增，确保同一文本二次点击
   * 也能触发 useEffect（引用每次变化）。
   */
  fillPrompt?: { text: string; seq: number } | null;
}

// 建议追问 chips（run 完成后显示）
const SUGGEST_FOLLOW_UPS = [
  "为综述补充文献计量佐证（发文趋势、高被引、关键词聚类）",
  "把综述导出为 DOCX 格式下载",
  "检索补充更多相关文献，扩充语料库",
];

export function AgentChat({ projectId, onRunComplete, onRunStart, fillPrompt }: Props) {
  const { settings: llm } = useLlmSettings();
  const { settings: sciverse } = useSciverseSettings();
  const llmOptions = useMemo(() => ({
    apiKey: llm.apiKey || undefined,
    baseUrl: llm.baseUrl || undefined,
    model: llm.model || undefined,
  }), [llm.apiKey, llm.baseUrl, llm.model]);
  const sciverseOptions = useMemo(() => ({
    apiToken: sciverse.apiToken || undefined,
    baseUrl: sciverse.baseUrl || undefined,
  }), [sciverse.apiToken, sciverse.baseUrl]);
  const {
    prompt,
    setPrompt,
    events,
    running,
    showFollowUps,
    submitError,
    autoConfirm,
    setAutoConfirm,
    rid,
    pendingConfirm,
    confirming,
    runCount,
    searchResult,
    submit,
    decide,
    stop,
    handleKeyDown,
  } = useAgentRunStream({ projectId, llmOptions, sciverseOptions, onRunComplete, onRunStart });

  // W4: 外部注入 fillPrompt（预设/能力卡/建议追问点击），写入输入框（可编辑，不自动发送）
  // I-1 修复：依赖整个对象（引用每次都变），text 相同但 seq 递增时仍会重跑
  useEffect(() => {
    if (fillPrompt && fillPrompt.text) {
      setPrompt(fillPrompt.text);
    }
  }, [fillPrompt]);

  // P2-3 → Phase 2: RunLog 下载已迁入 TrustCard（可信凭证卡含下载入口），此处不再重复。

  return (
    <div className="agent-chat">
      <div className="agent-input-row">
        <textarea
          className="input"
          placeholder="输入研究指令，按 Ctrl+Enter 或点击发送…"
          value={prompt}
          disabled={running}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          aria-label="Agent 指令输入"
        />
        <button
          className="btn btn-primary"
          disabled={running || !prompt.trim()}
          onClick={() => void submit()}
        >
          {running ? (
            <>
              <span className="spinner" />
              运行中
            </>
          ) : (
            "发送"
          )}
        </button>
        {/* Phase 5: 运行中显示「停止运行」——取消后端 run + 断本地流，避免孤儿 run 烧 token */}
        {running && rid && (
          <button
            className="btn btn-ghost"
            onClick={() => void stop()}
            aria-label="停止运行"
          >
            停止运行
          </button>
        )}
      </div>

      <div className="agent-options-row">
        <label className="agent-autoconfirm">
          <input
            type="checkbox"
            checked={autoConfirm}
            disabled={running}
            onChange={(e) => setAutoConfirm(e.target.checked)}
          />
          自动确认写操作
        </label>
        {/* Phase 2: 「下载 RunLog」已迁入可信凭证卡 TrustCard（含哈希链/grounding 指标）。 */}
      </div>

      {submitError && <ErrMsg error={submitError} />}

      <ErrorBoundary key={runCount}>
        <RunTimeline events={events} />
      </ErrorBoundary>

      {pendingConfirm && (
        <ConfirmCard
          toolId={pendingConfirm.toolId}
          action={pendingConfirm.action}
          argsPreview={pendingConfirm.argsPreview}
          pending={confirming}
          onApprove={() => void decide("approve")}
          onReject={() => void decide("reject")}
        />
      )}

      {/* P2-4: 检索候选卡 — 出现在时间线/确认卡之后、追问 chips 之前 */}
      {searchResult && (searchResult.candidates.length > 0 || searchResult.partial) && (
        <SearchCandidateCards
          projectId={projectId}
          candidates={searchResult.candidates}
          query={searchResult.query}
          searchCount={searchResult.searchCount}
          latestCount={searchResult.latestCount}
          partial={searchResult.partial}
          partialReason={searchResult.partialReason}
        />
      )}

      {/* W4 Task 8: run 完成后建议追问 chips */}
      {showFollowUps && !running && (
        <div className="follow-up-chips" role="group" aria-label="建议追问">
          <span className="follow-up-label">建议继续：</span>
          {SUGGEST_FOLLOW_UPS.map((text) => (
            <button
              key={text}
              className="follow-up-chip"
              onClick={() => setPrompt(text)}
              aria-label={text}
            >
              {text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
