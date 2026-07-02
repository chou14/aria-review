/**
 * projectGateP2.test.tsx — P2-1 project 查询三态闸门。
 *
 * 覆盖：
 * 1. ProjectGate loading / error(+重试、原始错误折叠) / success。
 * 2. AnalysisView / OutputView / ResearchView 在 useProject error 时显示真实错误，
 *    不误导为“去构建语料”。
 * 3. project 成功但无 ready corpus 时，页面内语料闸门仍按原逻辑显示。
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectGate } from "../components/ProjectGate";

const {
  mockUseProject,
  mockUseHealth,
  mockUseMaterializeCorpus,
  mockUseDiscoverGaps,
  mockUseLatestGapDiscoverRun,
  mockUseScratchpad,
  mockUseVerifyGap,
  mockUseGapVerdict,
  mockUsePatchGap,
} = vi.hoisted(() => ({
  mockUseProject: vi.fn(),
  mockUseHealth: vi.fn(),
  mockUseMaterializeCorpus: vi.fn(),
  mockUseDiscoverGaps: vi.fn(),
  mockUseLatestGapDiscoverRun: vi.fn(),
  mockUseScratchpad: vi.fn(),
  mockUseVerifyGap: vi.fn(),
  mockUseGapVerdict: vi.fn(),
  mockUsePatchGap: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useHealth: (...args: unknown[]) => mockUseHealth(...args),
}));

vi.mock("../api/agentHooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/agentHooks")>();
  return {
    ...actual,
    useProject: (...args: unknown[]) => mockUseProject(...args),
    useMaterializeCorpus: (...args: unknown[]) => mockUseMaterializeCorpus(...args),
    useDiscoverGaps: (...args: unknown[]) => mockUseDiscoverGaps(...args),
    useLatestGapDiscoverRun: (...args: unknown[]) => mockUseLatestGapDiscoverRun(...args),
    useScratchpad: (...args: unknown[]) => mockUseScratchpad(...args),
    useVerifyGap: (...args: unknown[]) => mockUseVerifyGap(...args),
    useGapVerdict: (...args: unknown[]) => mockUseGapVerdict(...args),
    usePatchGap: (...args: unknown[]) => mockUsePatchGap(...args),
  };
});

import { AnalysisView } from "../pages/AnalysisView";
import { OutputView } from "../pages/OutputView";
import { ResearchView } from "../pages/ResearchView";

function renderWithProviders(ui: React.ReactElement, path: string, route: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockProjectError(refetch = vi.fn()) {
  const error = Object.assign(new Error("Agent 连接失败"), {
    friendlyMessage: "无法读取项目信息，请确认 Agent 服务已启动。",
    originalMessage: "connect ECONNREFUSED 127.0.0.1:8765",
  });
  mockUseProject.mockReturnValue({ data: undefined, isLoading: false, error, refetch });
  return { error, refetch };
}

function mockProjectLoading() {
  mockUseProject.mockReturnValue({ data: undefined, isLoading: true, error: null, refetch: vi.fn() });
}

function mockProjectNoCorpus() {
  mockUseProject.mockReturnValue({
    data: { name: "测试项目", activeCorpus: null, latestCorpus: null },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseHealth.mockReturnValue({ data: undefined, isError: false });
  mockUseMaterializeCorpus.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, error: null });
  mockUseDiscoverGaps.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, error: null });
  mockUseLatestGapDiscoverRun.mockReturnValue({ data: { jobs: [] }, isLoading: false, error: null });
  mockUseScratchpad.mockReturnValue({ data: null, isLoading: false, error: null });
  mockUseVerifyGap.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, error: null, variables: null });
  mockUseGapVerdict.mockReturnValue({ data: null, isError: false, error: null });
  mockUsePatchGap.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, error: null });
  mockProjectNoCorpus();
});

describe("ProjectGate", () => {
  it("loading 时渲染页面级加载态", () => {
    render(
      <ProjectGate project={{ isLoading: true }}>
        <div>成功内容</div>
      </ProjectGate>,
    );

    expect(screen.getByText(/加载项目/)).toBeInTheDocument();
    expect(screen.queryByText("成功内容")).toBeNull();
  });

  it("error 时渲染友好错误、原始错误折叠与重试按钮", () => {
    const refetch = vi.fn();
    const error = Object.assign(new Error("HTTP 500"), {
      friendlyMessage: "Agent 暂时不可用",
      originalMessage: "fetch failed: ECONNREFUSED",
    });

    render(
      <ProjectGate project={{ error, refetch }}>
        <div>成功内容</div>
      </ProjectGate>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Agent 暂时不可用");
    expect(screen.getByText("查看原始错误")).toBeInTheDocument();
    expect(screen.getByText("fetch failed: ECONNREFUSED")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("成功内容")).toBeNull();
  });

  it("成功时渲染 children", () => {
    render(
      <ProjectGate project={{ isLoading: false, error: null }}>
        <div>成功内容</div>
      </ProjectGate>,
    );

    expect(screen.getByText("成功内容")).toBeInTheDocument();
  });

  it("有缓存数据时后台刷新失败不阻断页面（stale-while-error）", () => {
    render(
      <ProjectGate project={{ error: new Error("后台刷新失败"), data: { id: 5, name: "p" } }}>
        <div>成功内容</div>
      </ProjectGate>,
    );

    expect(screen.getByText("成功内容")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("三大页面 project 查询三态", () => {
  it("AnalysisView useProject error 时显示真实错误和重试，不显示构建语料引导", () => {
    const { refetch } = mockProjectError();
    renderWithProviders(<AnalysisView />, "/projects/5/analysis/overview", "/projects/:pid/analysis/:view");

    expect(screen.getByRole("alert")).toHaveTextContent("无法读取项目信息");
    expect(screen.queryByText("分析语料未就绪")).toBeNull();
    expect(screen.queryByRole("button", { name: /构建分析语料/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("OutputView useProject error 时显示真实错误和重试，不显示构建语料引导", () => {
    const { refetch } = mockProjectError();
    renderWithProviders(<OutputView />, "/projects/5/output", "/projects/:pid/output");

    expect(screen.getByRole("alert")).toHaveTextContent("无法读取项目信息");
    expect(screen.queryByText("需先构建分析语料")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("ResearchView useProject error 时显示真实错误和重试，不显示构建语料引导", () => {
    const { refetch } = mockProjectError();
    renderWithProviders(<ResearchView />, "/projects/5/research", "/projects/:pid/research");

    expect(screen.getByRole("alert")).toHaveTextContent("无法读取项目信息");
    expect(screen.queryByText(/需先在「分析」区构建就绪/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("loading 时显示项目加载态，不提前显示语料引导", () => {
    mockProjectLoading();
    renderWithProviders(<AnalysisView />, "/projects/5/analysis/overview", "/projects/:pid/analysis/:view");

    expect(screen.getByText(/加载项目/)).toBeInTheDocument();
    expect(screen.queryByText("分析语料未就绪")).toBeNull();
  });

  it("project 成功且无 ready corpus 时仍显示页面内语料 gate", () => {
    mockProjectNoCorpus();

    renderWithProviders(<AnalysisView />, "/projects/5/analysis/overview", "/projects/:pid/analysis/:view");
    expect(screen.getByText("分析语料未就绪")).toBeInTheDocument();

    renderWithProviders(<OutputView />, "/projects/5/output", "/projects/:pid/output");
    expect(screen.getByText("需先构建分析语料")).toBeInTheDocument();

    renderWithProviders(<ResearchView />, "/projects/5/research", "/projects/:pid/research");
    expect(screen.getByText(/需先在「分析」区构建就绪/)).toBeInTheDocument();
  });
});
