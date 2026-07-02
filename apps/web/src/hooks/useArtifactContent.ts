import { useCallback, useEffect, useState } from "react";
import { getRun } from "../api/client";
import type { ArtifactItem } from "../api/client";
import type { FrontendEvidenceRef } from "../components/GroundingOverlay";

export interface ArtifactContentData {
  content: string | null;
  evidenceRefs: FrontendEvidenceRef[] | null;
}

export interface ArtifactContentState {
  loading: boolean;
  error: Error | null;
  data: ArtifactContentData | null;
  retry: () => void;
}

export function getArtifactCanvasContent(
  artifact: ArtifactItem | null,
  contentState: ArtifactContentState,
): string | null {
  if (!artifact) return null;
  const runId = Number(artifact.runId ?? 0);
  if (!Number.isFinite(runId) || runId <= 0) {
    return "（该工件未关联运行记录，无法读取运行产出。）";
  }
  if (contentState.loading) return "（正在加载工件内容…）";
  if (contentState.error) return "（加载工件内容失败，请稍后重试。）";
  return contentState.data?.content ?? null;
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value;
  return new Error("加载工件内容失败");
}

export function useArtifactContent(
  projectId: number,
  artifact: ArtifactItem | null,
): ArtifactContentState {
  const [state, setState] = useState<Omit<ArtifactContentState, "retry">>({
    loading: false,
    error: null,
    data: null,
  });
  const [reloadSeq, setReloadSeq] = useState(0);

  const retry = useCallback(() => {
    setReloadSeq((seq) => seq + 1);
  }, []);

  const rawRunId = artifact?.runId ?? null;
  const runIdNum = Number(rawRunId ?? 0);
  const runId = Number.isFinite(runIdNum) && runIdNum > 0 ? String(rawRunId) : null;

  useEffect(() => {
    if (!artifact || !runId || projectId <= 0) {
      setState({ loading: false, error: null, data: null });
      return;
    }

    let cancelled = false;
    setState({ loading: true, error: null, data: null });

    void getRun(projectId, String(runId))
      .then((detail) => {
        if (cancelled) return;
        setState({
          loading: false,
          error: null,
          data: {
            content: detail.finalOutput ?? null,
            evidenceRefs: (detail.evidenceRefs as FrontendEvidenceRef[] | null) ?? null,
          },
        });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({ loading: false, error: toError(error), data: null });
      });

    return () => {
      cancelled = true;
    };
  }, [artifact?.id, projectId, reloadSeq, runId]);

  return { ...state, retry };
}
