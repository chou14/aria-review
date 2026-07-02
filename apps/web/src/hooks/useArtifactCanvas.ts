import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCreateArtifact } from "../api/agentHooks";
import type { ArtifactItem } from "../api/agentHooks";
import { getArtifactCanvasContent, useArtifactContent } from "./useArtifactContent";
import type { AgentRunCompleteInfo } from "./useAgentRunStream";

export function useArtifactCanvas(projectId: number) {
  const qc = useQueryClient();
  const createArtifact = useCreateArtifact(projectId);
  const [localArtifacts, setLocalArtifacts] = useState<ArtifactItem[]>([]);
  const [canvasArtifact, setCanvasArtifact] = useState<ArtifactItem | null>(null);
  const processedRef = useRef<Set<string>>(new Set());

  const canvasContentState = useArtifactContent(projectId, canvasArtifact);
  const canvasContent = getArtifactCanvasContent(canvasArtifact, canvasContentState);
  const canvasEvidenceRefs = canvasContentState.data?.evidenceRefs ?? null;

  const handleRunComplete = useCallback(
    async ({ runId, finalOutput, eventSeq }: AgentRunCompleteInfo) => {
      const dedupKey = `${runId}:${eventSeq}`;
      if (processedRef.current.has(dedupKey)) return;
      processedRef.current.add(dedupKey);

      // SSE run_complete 才是 agent 真正完成的时点，此时刷新受工具写入影响的缓存。
      void qc.invalidateQueries({ queryKey: ["projectLibraryStats", projectId] });
      void qc.invalidateQueries({ queryKey: ["globalLibraryStats"] });
      void qc.invalidateQueries({ queryKey: ["project", projectId] });

      const titleMatch = finalOutput.match(/^#+\s+(.+)/m);
      const title = titleMatch ? titleMatch[1].trim() : `综述 ${new Date().toLocaleTimeString()}`;

      try {
        const artifact = await createArtifact.mutateAsync({
          type: "review",
          title,
          runId: Number(runId),
          sourceEventSeq: eventSeq,
          contentRef: `run:${runId}`,
          pinned: false,
        });
        setLocalArtifacts((prev) => [artifact, ...prev]);
      } catch {
        setLocalArtifacts((prev) => [
          {
            id: -1 * Date.now(),
            projectId,
            runId: Number(runId),
            type: "review",
            title,
            sourceEventSeq: eventSeq,
            contentRef: `run:${runId}`,
            pinned: false,
            order: 0,
          },
          ...prev,
        ]);
      }
    },
    [createArtifact, projectId, qc],
  );

  const handleRetryPersist = useCallback(
    async (artifact: ArtifactItem) => {
      if (artifact.id >= 0) return;
      const persisted = await createArtifact.mutateAsync({
        type: artifact.type,
        title: artifact.title,
        runId: artifact.runId == null ? null : Number(artifact.runId),
        sourceEventSeq: artifact.sourceEventSeq ?? null,
        contentRef: artifact.contentRef ?? null,
        pinned: artifact.pinned,
        userAnnotation: artifact.userAnnotation ?? null,
        order: artifact.order,
      });
      setLocalArtifacts((prev) => prev.map((item) => (item.id === artifact.id ? persisted : item)));
      setCanvasArtifact((current) => (current?.id === artifact.id ? persisted : current));
    },
    [createArtifact],
  );

  const handleExpand = useCallback((artifact: ArtifactItem) => {
    setCanvasArtifact(artifact);
  }, []);

  return {
    localArtifacts,
    canvasArtifact,
    setCanvasArtifact,
    canvasContentState,
    canvasContent,
    canvasEvidenceRefs,
    hasCanvas: canvasArtifact !== null,
    handleRunComplete,
    handleRetryPersist,
    handleExpand,
  };
}
