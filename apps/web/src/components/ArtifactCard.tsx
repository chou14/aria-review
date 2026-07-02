/**
 * ArtifactCard — 工件卡片组件（M4）
 *
 * 在 AgentChat 运行完成后，run_complete 事件产出的 final_output 以工件卡形式呈现。
 * 提供：
 *   - 类型徽章（综述/分析/抽取/文献集）
 *   - 标题 + 操作（展开 Canvas / pin / 重跑）
 *   - pin 状态持久化（调后端 artifacts 端点）
 *
 * 注意：内容本身派生自 final_output（不可变审计源），工件 id 是后端持久化的身份标识。
 */
import { useState, useCallback } from "react";
import type { ArtifactItem } from "../api/client";
import { usePatchArtifact } from "../api/agentHooks";

// 类型 → 中文标签映射
const TYPE_LABELS: Record<string, string> = {
  review: "综述",
  analysis: "分析",
  extraction: "抽取",
  paperset: "文献集",
};

// 类型 → CSS class 映射（学术宣纸风格）
const TYPE_BADGE_CLASS: Record<string, string> = {
  review: "badge badge-ok",
  analysis: "badge badge-warn",
  extraction: "badge",
  paperset: "badge",
};

interface Props {
  artifact: ArtifactItem;
  projectId: number;
  /** 点击「展开」回调 → 唤起 ArtifactCanvas */
  onExpand: (artifact: ArtifactItem) => void;
  /** 点击「重跑」回调（可选，传入时才显示按钮） */
  onRerun?: (artifact: ArtifactItem) => void;
  /** 点击「重试持久化」回调（负 id 本地回退工件专用） */
  onRetryPersist?: (artifact: ArtifactItem) => Promise<void> | void;
}

export function ArtifactCard({ artifact, projectId, onExpand, onRerun, onRetryPersist }: Props) {
  const [pinning, setPinning] = useState(false);
  const [retryingPersist, setRetryingPersist] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);
  const [persistError, setPersistError] = useState<string | null>(null);
  const patchArtifact = usePatchArtifact(projectId);
  const isLocalFallback = artifact.id < 0;

  const handlePin = useCallback(async () => {
    if (pinning || isLocalFallback) return;
    setPinError(null);
    setPinning(true);
    try {
      await patchArtifact.mutateAsync({ aid: artifact.id, pinned: !artifact.pinned });
    } catch {
      setPinError("Pin 操作失败，请稍后重试。");
    } finally {
      setPinning(false);
    }
  }, [artifact.id, artifact.pinned, isLocalFallback, pinning, patchArtifact]);

  const handleRetryPersist = useCallback(async () => {
    if (!onRetryPersist || retryingPersist) return;
    setPersistError(null);
    setRetryingPersist(true);
    try {
      await onRetryPersist(artifact);
    } catch {
      setPersistError("持久化失败，请稍后重试。");
    } finally {
      setRetryingPersist(false);
    }
  }, [artifact, onRetryPersist, retryingPersist]);

  const typeLabel = TYPE_LABELS[artifact.type] ?? artifact.type;
  const badgeClass = TYPE_BADGE_CLASS[artifact.type] ?? "badge";

  return (
    <div className="artifact-card card" data-testid="artifact-card">
      {/* 类型徽章 + 标题行 */}
      <div className="artifact-card-header">
        <span className={badgeClass} title={`工件类型: ${artifact.type}`}>
          {typeLabel}
        </span>
        <span className="artifact-title" title={artifact.title}>
          {artifact.title || "(无标题)"}
        </span>
        {isLocalFallback && (
          <span className="badge" title="该工件尚未保存到后端">
            未持久化
          </span>
        )}
      </div>

      {/* 操作行 */}
      <div className="artifact-card-actions">
        {/* 展开 Canvas */}
        <button
          className="btn btn-ghost"
          onClick={() => onExpand(artifact)}
          title="在 Canvas 中展开查看（含 grounding 溯源）"
        >
          展开
        </button>

        {isLocalFallback ? (
          <button
            className="btn btn-ghost"
            disabled={retryingPersist || !onRetryPersist}
            onClick={() => void handleRetryPersist()}
            title="重新保存工件，成功后即可 Pin"
          >
            {retryingPersist ? "持久化中" : "重试持久化"}
          </button>
        ) : (
          <button
            className={`btn btn-ghost ${artifact.pinned ? "artifact-pinned" : ""}`}
            disabled={pinning}
            onClick={() => void handlePin()}
            title={artifact.pinned ? "取消 pin" : "Pin 工件（跨会话保留）"}
            aria-pressed={artifact.pinned}
          >
            {artifact.pinned ? "已 Pin" : "Pin"}
          </button>
        )}

        {/* 重跑（可选） */}
        {onRerun && (
          <button
            className="btn btn-ghost"
            onClick={() => onRerun(artifact)}
            title="重新运行此 agent 指令"
          >
            重跑
          </button>
        )}
      </div>

      {/* 用户标注（若有） */}
      {artifact.userAnnotation && (
        <div className="artifact-annotation muted" style={{ fontSize: "0.82rem", marginTop: "0.4rem" }}>
          {artifact.userAnnotation}
        </div>
      )}
      {(pinError || persistError) && (
        <div role="alert" style={{ color: "var(--danger)", fontSize: "0.82rem", marginTop: "0.4rem" }}>
          {pinError ?? persistError}
        </div>
      )}
    </div>
  );
}
