/**
 * ReviewPanel.precheck.test.tsx — 生成综述前置检查
 *
 * 目标：空项目 / 未纳入 / 无可读全文时，前端直接禁用生成并给出中文引导，
 * 不再让用户点击后看到后端裸 422/400。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { asRCorpusId } from "../../api/corpusIds";

const CID = asRCorpusId("r1");

const { getAiJobSpy, listAiJobsSpy, createAiJobSpy } = vi.hoisted(() => ({
  getAiJobSpy: vi.fn(),
  listAiJobsSpy: vi.fn(),
  createAiJobSpy: vi.fn(),
}));

vi.mock("../../api/client", async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    getAiJob: (...a: unknown[]) => getAiJobSpy(...a),
    listAiJobs: (...a: unknown[]) => listAiJobsSpy(...a),
    createAiJob: (...a: unknown[]) => createAiJobSpy(...a),
  };
});

import { ReviewPanel } from "../ReviewPanel";

function renderPanel(stats: { includedCount: number; readableFulltextCount: number }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReviewPanel projectId="7" corpusId={CID} projectStats={stats} />
    </QueryClientProvider>,
  );
}

function fillTopic() {
  fireEvent.change(screen.getByLabelText("研究主题"), {
    target: { value: "人工智能教育应用" },
  });
}

beforeEach(() => {
  localStorage.clear();
  getAiJobSpy.mockReset();
  listAiJobsSpy.mockReset();
  createAiJobSpy.mockReset();
  listAiJobsSpy.mockResolvedValue({ jobs: [] });
});

describe("ReviewPanel 生成前置检查", () => {
  it("空项目 includedCount=0：禁用生成，并引导去文献库纳排", () => {
    renderPanel({ includedCount: 0, readableFulltextCount: 0 });
    fillTopic();

    expect(screen.getByRole("button", { name: "生成综述" })).toBeDisabled();
    expect(screen.getByText("先纳入文献", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去文献库纳排" })).toHaveAttribute(
      "href",
      "/projects/7/library",
    );
  });

  it("有全文但未纳入 includedCount=0：仍先要求纳排", () => {
    renderPanel({ includedCount: 0, readableFulltextCount: 2 });
    fillTopic();

    expect(screen.getByRole("button", { name: "生成综述" })).toBeDisabled();
    expect(screen.getByText("先纳入文献", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去文献库纳排" })).toBeInTheDocument();
  });

  it("已纳入但 readableFulltextCount=0：禁用生成，并引导导入/解析全文", () => {
    renderPanel({ includedCount: 3, readableFulltextCount: 0 });
    fillTopic();

    expect(screen.getByRole("button", { name: "生成综述" })).toBeDisabled();
    expect(screen.getByText("先导入/解析全文", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去文献库导入全文" })).toHaveAttribute(
      "href",
      "/projects/7/library",
    );
  });

  it("已纳入且有可读全文：填写主题后生成按钮可用", () => {
    renderPanel({ includedCount: 3, readableFulltextCount: 2 });
    fillTopic();

    expect(screen.getByRole("button", { name: "生成综述" })).toBeEnabled();
    expect(screen.queryByText(/先纳入文献|先导入\/解析全文/)).not.toBeInTheDocument();
  });
});
