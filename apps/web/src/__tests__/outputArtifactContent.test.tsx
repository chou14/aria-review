import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import type { ArtifactItem } from "../api/client";

const {
  mockUseProject,
  mockUseArtifacts,
  mockUsePatchArtifact,
  mockUseProjectPapers,
} = vi.hoisted(() => ({
  mockUseProject: vi.fn(),
  mockUseArtifacts: vi.fn(),
  mockUsePatchArtifact: vi.fn(),
  mockUseProjectPapers: vi.fn(),
}));

vi.mock("../api/agentHooks", () => ({
  getPanelRCorpusId: (activeCorpus: { rCorpusId?: string | null } | null | undefined) =>
    activeCorpus?.rCorpusId ?? "",
  useProject: (...args: unknown[]) => mockUseProject(...args),
  useArtifacts: (...args: unknown[]) => mockUseArtifacts(...args),
  usePatchArtifact: (...args: unknown[]) => mockUsePatchArtifact(...args),
  useProjectPapers: (...args: unknown[]) => mockUseProjectPapers(...args),
}));

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getRun: vi.fn(),
  };
});

vi.mock("../components/ReportPanel", () => ({
  ReportPanel: () => <div>报告导出面板</div>,
}));

vi.mock("../components/PrismaPanel", () => ({
  PrismaPanel: () => <div>PRISMA 流程图</div>,
}));

vi.mock("../lib/markdown", () => ({
  renderMarkdown: (md: string) => `<p>${md}</p>`,
}));

import { getRun } from "../api/client";
import { OutputView } from "../pages/OutputView";

const PINNED_ARTIFACT: ArtifactItem = {
  id: 2,
  projectId: 5,
  runId: 10,
  type: "review",
  title: "已 Pin 综述",
  pinned: true,
  order: 0,
};

function renderOutputView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projects/5/output"]}>
        <Routes>
          <Route path="/projects/:pid/output" element={<OutputView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockReadyOutput(
  artifacts: ArtifactItem[],
  artifactsQuery?: {
    data?: { artifacts: ArtifactItem[] };
    isLoading?: boolean;
    error?: unknown;
    refetch?: () => unknown;
  },
) {
  mockUseProject.mockReturnValue({
    data: {
      name: "测试项目",
      activeCorpus: {
        corpusId: 1,
        rCorpusId: "r_corpus_001",
        status: "ready",
        stale: false,
        documentCount: 8,
        contentHash: "xyz",
      },
    },
    isLoading: false,
    error: null,
  });
  mockUseArtifacts.mockReturnValue(
    artifactsQuery ?? {
      data: { artifacts },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    },
  );
}

describe("OutputView 已 Pin 工件内容", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePatchArtifact.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseProjectPapers.mockReturnValue({ data: { papers: [] }, isLoading: false, error: null });
  });

  it("已 Pin 工件列表加载中时显示加载态", () => {
    mockReadyOutput([], {
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    renderOutputView();

    expect(screen.getByText("已 Pin 综述工件")).toBeInTheDocument();
    expect(screen.getByText(/加载已 Pin 综述工件/)).toBeInTheDocument();
  });

  it("已 Pin 工件列表加载失败时显示错误和重试", () => {
    const refetch = vi.fn();
    mockReadyOutput([], {
      data: undefined,
      isLoading: false,
      error: new Error("network down"),
      refetch,
    });

    renderOutputView();

    expect(screen.getByText("已 Pin 综述工件加载失败，请重试。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("已 Pin 工件为空时保持原有空态：不渲染汇集区", () => {
    mockReadyOutput([]);

    renderOutputView();

    expect(screen.queryByText("已 Pin 综述工件")).toBeNull();
  });

  it("有 runId 的 Pin 工件展开后渲染 finalOutput 内容", async () => {
    mockReadyOutput([PINNED_ARTIFACT]);
    vi.mocked(getRun).mockResolvedValue({
      runId: "10",
      status: "done",
      finalOutput: "## 完整综述\n这里是运行产出的全文。",
      evidenceRefs: [{ paper_id: 7, span: "证据", claim: "这里是运行产出的全文。", match_quality: "green" }],
    });

    renderOutputView();
    fireEvent.click(screen.getByRole("button", { name: "展开" }));

    expect(await screen.findByText(/完整综述/)).toBeInTheDocument();
    expect(screen.getAllByText(/这里是运行产出的全文/).length).toBeGreaterThan(0);
    expect(getRun).toHaveBeenCalledWith(5, "10");
  });

  it("加载失败时显示错误和重试，重试成功后渲染内容", async () => {
    mockReadyOutput([PINNED_ARTIFACT]);
    vi.mocked(getRun)
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce({
        runId: "10",
        status: "done",
        finalOutput: "重试后读取到的综述正文",
        evidenceRefs: [],
      });

    renderOutputView();
    fireEvent.click(screen.getByRole("button", { name: "展开" }));

    expect(await screen.findByText("加载工件内容失败。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => {
      expect(screen.getByText(/重试后读取到的综述正文/)).toBeInTheDocument();
    });
    expect(getRun).toHaveBeenCalledTimes(2);
  });

  it("无 runId 工件展开后说明未关联运行记录", () => {
    mockReadyOutput([{ ...PINNED_ARTIFACT, runId: null }]);

    renderOutputView();
    fireEvent.click(screen.getByRole("button", { name: "展开" }));

    expect(screen.getByText(/该工件未关联运行记录/)).toBeInTheDocument();
    expect(getRun).not.toHaveBeenCalled();
  });
});
