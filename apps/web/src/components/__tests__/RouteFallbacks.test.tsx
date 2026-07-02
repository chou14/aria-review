import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RouteErrorBoundary, isChunkLoadError } from "../RouteErrorBoundary";
import { RouteLoadingFallback } from "../RouteFallback";

function ThrowError({ error }: { error: unknown }): never {
  throw error;
}

describe("RouteLoadingFallback", () => {
  it("渲染全局页面加载态", () => {
    render(<RouteLoadingFallback />);

    expect(screen.getByRole("status")).toHaveTextContent("页面加载中…");
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });
});

describe("RouteErrorBoundary", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it("识别动态 import chunk 加载失败", () => {
    expect(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: /assets/page.js"))).toBe(true);
    expect(isChunkLoadError({ name: "ChunkLoadError", message: "Loading chunk 12 failed." })).toBe(true);
  });

  it("捕获 chunk 加载错误后渲染重试按钮", () => {
    const onChunkRetry = vi.fn();

    render(
      <MemoryRouter>
        <RouteErrorBoundary onChunkRetry={onChunkRetry}>
          <ThrowError error={new TypeError("Failed to fetch dynamically imported module: /assets/page.js")} />
        </RouteErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "加载失败" })).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "重试" });

    fireEvent.click(retry);

    expect(onChunkRetry).toHaveBeenCalledTimes(1);
  });

  it("非 chunk 渲染错误显示通用错误态与可折叠详情", () => {
    render(
      <MemoryRouter>
        <RouteErrorBoundary>
          <ThrowError error={new Error("render boom")} />
        </RouteErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "页面渲染出错" })).toBeInTheDocument();
    expect(screen.getByText("查看错误详情")).toBeInTheDocument();
    expect(screen.getByText(/render boom/)).toBeInTheDocument();
  });
});
