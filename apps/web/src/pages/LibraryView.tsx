/**
 * LibraryView.tsx — 文献库三栏视图（M1）
 *
 * 布局：左栏筛选 + 中栏虚拟列表 + 右栏详情
 * 路由：/projects/:pid/library（Outlet 容器已由此组件直接渲染，
 *       原子路由 library/:paperId 现通过 URL 同步到右栏，不再独立页面）
 *
 * 说明：本组件直接实现三栏，不再只渲染 <Outlet />，
 *       因此 routes.tsx 的 library/:paperId 子路由仍保留兼容性
 *       但右栏内容由内部 selectedPaperId 状态控制，并与 URL 同步。
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useBackfillMetadata,
  useBackfillFulltext,
  useExtractStructured,
  useImportPapers,
  usePatchInclusion,
  useProject,
  useProjectPapers,
} from "../api/agentHooks";
import type { BackfillMetadataResult, ExtractStructuredResult, FulltextBackfillResult, ProjectPaperItem } from "../api/client";
import { useSciverseSettings } from "../api/useSciverseSettings";
import { useLibraryListState } from "../hooks/useLibraryListState";
export type { ExtractionFilter, SortDir, SortField, StatusFilter } from "../hooks/useLibraryListState";
import { ErrMsg, Loading } from "../lib/ui";
import { ImportDialog } from "./library/ImportDialog";
import { LibFilterPanel } from "./library/LibFilterPanel";
import { LibPaperDetail } from "./library/LibPaperDetail";
import { LibPaperList } from "./library/LibPaperList";
import { ScreeningMode } from "./library/ScreeningMode";

export function LibraryView() {
  const { pid, paperId: paperIdParam } = useParams<{ pid: string; paperId?: string }>();
  const pidNum = Number(pid);
  const navigate = useNavigate();

  const { data, isLoading, error } = useProjectPapers(pidNum);
  const { data: project } = useProject(pidNum);
  const patch = usePatchInclusion(pidNum);
  const importMut = useImportPapers(pidNum);
  const backfillMut = useBackfillMetadata(pidNum);
  const fulltextBackfillMut = useBackfillFulltext(pidNum);
  const extractMut = useExtractStructured(pidNum);
  const { settings: sciverse } = useSciverseSettings();

  // ---- AI 动作反馈状态 ----
  const [backfillResult, setBackfillResult] = useState<BackfillMetadataResult | null>(null);
  const [fulltextBackfillResult, setFulltextBackfillResult] = useState<FulltextBackfillResult | null>(null);
  const [extractResult, setExtractResult] = useState<ExtractStructuredResult | null>(null);

  // ---- 选中详情的 paperId（URL 同步） ----
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(
    paperIdParam ? Number(paperIdParam) : null,
  );

  // ---- 筛选模式 ----
  const [screeningMode, setScreeningMode] = useState(false);
  const [screeningIndex, setScreeningIndex] = useState(0);
  // P1-4：进入筛选模式时冻结 paperId 队列快照，筛选全程基于此快照，
  // 避免 PATCH 后 filtered 列表重排/缩减导致 index+1 跳篇。
  const [screeningQueue, setScreeningQueue] = useState<number[]>([]);

  // ---- 导入弹层 ----
  const [showImport, setShowImport] = useState(false);

  // paperIdParam 变化时同步右栏（支持深链接）
  useEffect(() => {
    if (paperIdParam) setSelectedPaperId(Number(paperIdParam));
  }, [paperIdParam]);

  // 选中行 → 更新 URL
  const handleSelectRow = useCallback(
    (pid2: number) => {
      setSelectedPaperId(pid2);
      navigate(`/projects/${pid}/library/${pid2}`, { replace: true });
    },
    [pid, navigate],
  );

  // 进入筛选模式时，从过滤后列表第一篇开始
  // P1-4：冻结 paperId 快照，筛选全程基于此快照，不随 filtered 动态变化。
  const startScreening = (filteredPapers: ProjectPaperItem[]) => {
    if (filteredPapers.length === 0) return;
    setScreeningQueue(filteredPapers.map((p) => p.paperId));
    setScreeningIndex(0);
    setScreeningMode(true);
  };

  const papers = data?.papers ?? [];
  const listState = useLibraryListState({
    papers,
    patchInclusion: (paperId, status) => patch.mutateAsync({ paperId, inclusionStatus: status }),
  });

  const runProjectFulltextBackfill = useCallback(async () => {
    setFulltextBackfillResult(null);
    fulltextBackfillMut.reset();
    const aggregate: FulltextBackfillResult = {
      total: 0,
      fetched: 0,
      failed: [],
      skipped: 0,
      remaining: 0,
    };
    let remaining: number | null = null;
    for (let i = 0; i < 20; i += 1) {
      // 已失败项传给后端排除：避免失败项每轮占据前排、饿死后续候选（codex 复核 P2）
      const excludePaperIds = aggregate.failed.map((f) => f.paperId);
      const batch = await fulltextBackfillMut.mutateAsync({
        maxPapers: 50,
        excludePaperIds: excludePaperIds.length > 0 ? excludePaperIds : undefined,
        sciverse: {
          apiToken: sciverse.apiToken || undefined,
          baseUrl: sciverse.baseUrl || undefined,
        },
      });
      // total 取首轮全量；fetched/failed 跨轮累加；skipped/remaining 取最新一轮（非累加口径）
      if (i === 0) aggregate.total = batch.total;
      aggregate.fetched += batch.fetched;
      aggregate.skipped = batch.skipped;
      aggregate.failed = aggregate.failed.concat(batch.failed ?? []);
      aggregate.remaining = batch.remaining;
      setFulltextBackfillResult({ ...aggregate, failed: [...aggregate.failed] });
      const madeProgress = batch.fetched + (batch.failed?.length ?? 0) > 0;
      if (batch.remaining <= 0 || !madeProgress || batch.remaining === remaining) break;
      remaining = batch.remaining;
    }
  }, [fulltextBackfillMut, sciverse.apiToken, sciverse.baseUrl]);

  if (isLoading) return <Loading label="加载文献库…" />;
  if (error) return <ErrMsg error={error} />;

  // P1-4：筛选模式下的当前文献——从冻结快照（screeningQueue）取 paperId，
  // 再从全量 papers 中找详情，不受过滤条件动态变化影响，确保不跳篇。
  const screeningPaperId = screeningMode ? screeningQueue[screeningIndex] : null;
  const screeningPaper = screeningPaperId != null
    ? (papers.find((p) => p.paperId === screeningPaperId) ?? null)
    : null;

  return (
    <>
      {/* 筛选模式遮罩层（全屏） */}
      {screeningMode && screeningPaper && (
        <ScreeningMode
          paper={screeningPaper}
          current={screeningIndex}
          total={screeningQueue.length}
          researchQuestion={project?.researchQuestion ?? ""}
          onDecide={async (status, exclusionReason) => {
            await patch.mutateAsync({
              paperId: screeningPaper.paperId,
              inclusionStatus: status,
              exclusionReason,
            });
            // P1-4：基于快照长度判断是否到末尾，不依赖实时 filtered.length
            if (screeningIndex + 1 < screeningQueue.length) {
              setScreeningIndex((i) => i + 1);
            } else {
              setScreeningMode(false);
            }
          }}
          onClose={() => setScreeningMode(false)}
        />
      )}

      {/* 导入弹层 */}
      {showImport && (
        <ImportDialog
          importing={importMut.isPending}
          result={importMut.data}
          error={importMut.error}
          onImport={(files, defaultStatus) => importMut.mutate({ files, defaultStatus })}
          onClose={() => {
            setShowImport(false);
            importMut.reset();
          }}
        />
      )}

      {/* 三栏主体（窄屏选中文献时加 --detail-open，详情覆盖层浮起，dogfood A1） */}
      <div className={selectedPaperId ? "lib-shell lib-shell--detail-open" : "lib-shell"}>
        {/* 左栏：筛选 */}
        <div className="lib-shell-filter">
          <LibFilterPanel
            counts={listState.counts}
            statusFilter={listState.statusFilter}
            onStatusFilter={listState.setStatusFilter}
            search={listState.search}
            onSearch={listState.setSearch}
            // tags 筛选：PaperDetail 有 tags，但 ProjectPaperItem 没有 tags 字段
            // TODO: 若 GET /projects/{pid}/papers 返回 tags，则在此实现标签筛选
          />
        </div>

        {/* 中栏：列表 */}
        <div className="lib-shell-list">
          <LibPaperList
            papers={listState.filtered}
            allPapers={papers}
            selected={listState.selected}
            selectedPaperId={selectedPaperId}
            sortField={listState.sortField}
            sortDir={listState.sortDir}
            onSort={listState.handleSort}
            onSelectRow={handleSelectRow}
            onToggleSelect={listState.handleToggleSelect}
            onSelectAll={listState.handleSelectAll}
            onBulkStatus={listState.handleBulkStatus}
            onStartScreening={() => startScreening(listState.filtered)}
            onShowImport={() => setShowImport(true)}
            isBulkPending={patch.isPending}
            extractionFilter={listState.extractionFilter}
            onExtractionFilter={listState.setExtractionFilter}
            isBackfilling={backfillMut.isPending}
            isFulltextBackfilling={fulltextBackfillMut.isPending}
            isExtracting={extractMut.isPending}
            backfillResult={backfillResult}
            fulltextBackfillResult={fulltextBackfillResult}
            extractResult={extractResult}
            backfillError={backfillMut.error}
            fulltextBackfillError={fulltextBackfillMut.error}
            extractError={extractMut.error}
            onBackfill={() => {
              setBackfillResult(null);
              backfillMut.reset();
              backfillMut.mutate({ onlyMissing: true }, {
                onSuccess: (r) => setBackfillResult(r),
              });
            }}
            onFulltextBackfill={() => {
              void runProjectFulltextBackfill().catch(() => undefined);
            }}
            onExtract={() => {
              setExtractResult(null);
              extractMut.reset();
              extractMut.mutate({ reextract: false }, {
                onSuccess: (r) => setExtractResult(r),
              });
            }}
            onClearBackfillResult={() => setBackfillResult(null)}
            onClearFulltextBackfillResult={() => setFulltextBackfillResult(null)}
            onClearExtractResult={() => setExtractResult(null)}
          />
        </div>

        {/* 右栏：详情 */}
        <div className="lib-shell-detail">
          {selectedPaperId ? (
            <LibPaperDetail
              pid={pidNum}
              paperId={selectedPaperId}
              onBack={() => {
                // codex A1-P2: 同步 URL 回列表，否则刷新/重建会经 paperIdParam 重新打开覆盖层
                setSelectedPaperId(null);
                navigate(`/projects/${pid}/library`, { replace: true });
              }}
            />
          ) : (
            <div className="lib-empty" style={{ padding: "2rem 1rem" }}>
              <p style={{ fontSize: "0.9rem", color: "var(--ink-3)" }}>
                选择左侧文献查看详情
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
