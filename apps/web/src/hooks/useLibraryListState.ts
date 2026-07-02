import { useCallback, useMemo, useState } from "react";
import type { InclusionStatus, ProjectPaperItem } from "../api/client";

/** 排序字段 */
export type SortField = "title" | "year" | "screeningScore";
export type SortDir = "asc" | "desc";

/** 筛选面板选中的状态过滤 */
export type StatusFilter = InclusionStatus | "all";

/** 已解析过滤（元索引雏形） */
export type ExtractionFilter = "all" | "extracted" | "not-extracted";

interface UseLibraryListStateOptions {
  papers: ProjectPaperItem[];
  patchInclusion: (paperId: number, status: InclusionStatus) => Promise<unknown>;
}

/** 过滤+排序后的列表 */
export function applyLibraryFilter(
  papers: ProjectPaperItem[],
  search: string,
  status: StatusFilter,
  extractionFilter: ExtractionFilter,
  sortField: SortField,
  sortDir: SortDir,
): ProjectPaperItem[] {
  let list = papers;

  if (status !== "all") {
    list = list.filter((p) => p.inclusionStatus === status);
  }

  if (extractionFilter === "extracted") {
    list = list.filter((p) => p.hasExtraction);
  } else if (extractionFilter === "not-extracted") {
    list = list.filter((p) => !p.hasExtraction);
  }

  if (search.trim()) {
    const q = search.trim().toLowerCase();
    list = list.filter((p) => (p.title ?? "").toLowerCase().includes(q));
  }

  return [...list].sort((a, b) => {
    let cmp = 0;
    if (sortField === "title") {
      cmp = (a.title ?? "").localeCompare(b.title ?? "", "zh");
    } else if (sortField === "year") {
      cmp = (a.year ?? 0) - (b.year ?? 0);
    } else if (sortField === "screeningScore") {
      cmp = (a.screeningScore ?? -1) - (b.screeningScore ?? -1);
    }
    return sortDir === "asc" ? cmp : -cmp;
  });
}

/** 计算各状态计数 */
export function countLibraryStatus(papers: ProjectPaperItem[]) {
  const counts: Record<StatusFilter, number> = { all: 0, candidate: 0, included: 0, excluded: 0, maybe: 0 };
  for (const p of papers) {
    counts.all++;
    counts[p.inclusionStatus]++;
  }
  return counts;
}

export function useLibraryListState({ papers, patchInclusion }: UseLibraryListStateOptions) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [extractionFilter, setExtractionFilter] = useState<ExtractionFilter>("all");
  const [sortField, setSortField] = useState<SortField>("year");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const counts = useMemo(() => countLibraryStatus(papers), [papers]);
  const filtered = useMemo(
    () => applyLibraryFilter(papers, search, statusFilter, extractionFilter, sortField, sortDir),
    [papers, search, statusFilter, extractionFilter, sortField, sortDir],
  );

  const handleSort = useCallback((field: SortField) => {
    if (sortField === field) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }, [sortField]);

  const handleToggleSelect = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    if (selected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((p) => p.paperId)));
    }
  }, [filtered, selected.size]);

  const handleBulkStatus = useCallback(async (status: InclusionStatus) => {
    // 只对「当前过滤列表 ∩ selected」执行，避免跨过滤误操作隐藏文献。
    const filteredIds = new Set(filtered.map((p) => p.paperId));
    const ids = Array.from(selected).filter((id) => filteredIds.has(id));
    if (ids.length === 0) return;

    const results = await Promise.allSettled(
      ids.map((paperId) => patchInclusion(paperId, status)),
    );
    const failed = results.filter((r) => r.status === "rejected");
    if (failed.length > 0) {
      alert(`批量操作：${ids.length - failed.length} 篇成功，${failed.length} 篇失败`);
    }

    setSelected((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
  }, [filtered, patchInclusion, selected]);

  return {
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    extractionFilter,
    setExtractionFilter,
    sortField,
    sortDir,
    selected,
    counts,
    filtered,
    handleSort,
    handleToggleSelect,
    handleSelectAll,
    handleBulkStatus,
  };
}
