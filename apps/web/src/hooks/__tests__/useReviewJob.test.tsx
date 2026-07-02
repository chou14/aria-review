import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiJob } from "../../api/client";
import { asRCorpusId } from "../../api/corpusIds";

const { createAiJobSpy, getAiJobSpy, listAiJobsSpy } = vi.hoisted(() => ({
  createAiJobSpy: vi.fn(),
  getAiJobSpy: vi.fn(),
  listAiJobsSpy: vi.fn(),
}));

vi.mock("../../api/client", async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    createAiJob: (...a: unknown[]) => createAiJobSpy(...a),
    getAiJob: (...a: unknown[]) => getAiJobSpy(...a),
    listAiJobs: (...a: unknown[]) => listAiJobsSpy(...a),
  };
});

import { useReviewJob } from "../useReviewJob";

const PID = "7";
const CORPUS = asRCorpusId("r1");
const KEY = `bibliocn.ai.review.${PID}.${CORPUS}`;

function job(overrides: Partial<AiJob>): AiJob {
  return {
    id: 1,
    projectId: 7,
    corpusId: CORPUS,
    kind: "review",
    status: "done",
    resultText: "",
    events: [],
    request: {},
    ...overrides,
  } as unknown as AiJob;
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useReviewJob", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    listAiJobsSpy.mockResolvedValue({ jobs: [] });
  });

  it("恢复 localStorage 中的 jobId 并 hydrate 综述状态", async () => {
    localStorage.setItem(KEY, "12");
    getAiJobSpy.mockResolvedValue(job({ id: 12, resultText: "恢复正文", request: { type: "master", topic: "恢复主题" } }));

    const { result } = renderHook(
      () => useReviewJob({ projectId: PID, corpusId: CORPUS }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.text).toBe("恢复正文");
    });
    expect(result.current.type).toBe("master");
    expect(result.current.topic).toBe("恢复主题");
    expect(getAiJobSpy).toHaveBeenCalledWith(PID, 12);
  });

  it("坏缓存回退 listAiJobs，避免恢复路径留白", async () => {
    localStorage.setItem(KEY, "999");
    getAiJobSpy.mockRejectedValue(new Error("not found"));
    listAiJobsSpy.mockResolvedValue({ jobs: [job({ id: 22, resultText: "最新正文" })] });

    const { result } = renderHook(
      () => useReviewJob({ projectId: PID, corpusId: CORPUS }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.text).toBe("最新正文");
    });
    expect(localStorage.getItem(KEY)).toBe("22");
    expect(listAiJobsSpy).toHaveBeenCalledWith(PID, { kind: "review", corpusId: CORPUS, limit: 1 });
  });

  it("生成后轮询到 done 并写入结果", async () => {
    createAiJobSpy.mockResolvedValue(job({ id: 31, status: "running", request: { topic: "AI 教育" } }));
    getAiJobSpy.mockResolvedValue(job({ id: 31, status: "done", resultText: "完成正文" }));

    const { result } = renderHook(
      () => useReviewJob({
        projectId: PID,
        corpusId: CORPUS,
        projectStats: { includedCount: 2, readableFulltextCount: 2 },
      }),
      { wrapper },
    );

    act(() => {
      result.current.setTopic("AI 教育");
    });
    await act(async () => {
      await result.current.generate();
    });

    await waitFor(() => {
      expect(result.current.running).toBe(false);
      expect(result.current.text).toBe("完成正文");
    });
    expect(createAiJobSpy).toHaveBeenCalledWith(
      PID,
      { kind: "review", corpusId: CORPUS, type: "undergrad", topic: "AI 教育" },
      {},
    );
  });
});
