import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import type { ArtifactItem } from "../../api/client";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    getRun: vi.fn(),
  };
});

import { getRun } from "../../api/client";
import { useArtifactContent } from "../useArtifactContent";

const ARTIFACT: ArtifactItem = {
  id: 1,
  projectId: 5,
  runId: 10,
  type: "review",
  title: "已 Pin 综述",
  pinned: true,
  order: 0,
};

function Harness({ artifact = ARTIFACT }: { artifact?: ArtifactItem | null }) {
  const state = useArtifactContent(5, artifact);

  return (
    <div>
      <div data-testid="status">
        {state.loading ? "loading" : state.error ? "error" : state.data ? "success" : "idle"}
      </div>
      <div data-testid="content">{state.data?.content ?? ""}</div>
      <div data-testid="refs">{state.data?.evidenceRefs?.length ?? 0}</div>
      <button type="button" onClick={state.retry}>
        重试
      </button>
    </div>
  );
}

describe("useArtifactContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("成功拉取 run 并注入 finalOutput/evidenceRefs", async () => {
    vi.mocked(getRun).mockResolvedValue({
      runId: "10",
      status: "done",
      finalOutput: "## 完整综述\n正文",
      evidenceRefs: [{ paper_id: 1, span: "Smith", claim: "Smith 认为。", match_quality: "green" }],
    });

    render(<Harness />);

    expect(await screen.findByText("success")).toBeInTheDocument();
    expect(screen.getByTestId("content")).toHaveTextContent("完整综述");
    expect(screen.getByTestId("refs")).toHaveTextContent("1");
    expect(getRun).toHaveBeenCalledWith(5, "10");
  });

  it("请求未完成时暴露 loading 态", async () => {
    vi.mocked(getRun).mockImplementation(
      () => new Promise(() => undefined),
    );

    render(<Harness />);

    expect(await screen.findByText("loading")).toBeInTheDocument();
  });

  it("请求失败时暴露 error，并支持 retry 重新拉取", async () => {
    vi.mocked(getRun)
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce({
        runId: "10",
        status: "done",
        finalOutput: "重试后的正文",
        evidenceRefs: [],
      });

    render(<Harness />);

    expect(await screen.findByText("error")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => {
      expect(screen.getByText("success")).toBeInTheDocument();
    });
    expect(screen.getByTestId("content")).toHaveTextContent("重试后的正文");
    expect(getRun).toHaveBeenCalledTimes(2);
  });

  it("无 runId 工件不发起请求，保持 idle", () => {
    render(<Harness artifact={{ ...ARTIFACT, runId: null }} />);

    expect(screen.getByText("idle")).toBeInTheDocument();
    expect(getRun).not.toHaveBeenCalled();
  });
});
