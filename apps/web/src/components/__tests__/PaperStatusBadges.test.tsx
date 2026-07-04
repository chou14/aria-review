/**
 * PaperStatusBadges.test.tsx — Task 6 TDD 测试
 *
 * 覆盖：
 *   1. {hasPdf:true, ocrStatus:"done"} → 出现含全文徽章 + 已OCR 徽章
 *   2. {hasPdf:false, ocrStatus:"none"} → 出现"仅题录"徽章
 *   3. {hasPdf:true, ocrStatus:"pending"} → 出现含全文徽章 + 待OCR 徽章
 *   4. {hasPdf:true, ocrStatus:"failed"} → 出现含全文徽章 + OCR失败 徽章
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PaperStatusBadges } from "../PaperStatusBadges";

describe("PaperStatusBadges", () => {
  it("hasPdf+done → 含全文和已OCR 徽章均可见", () => {
    render(
      <PaperStatusBadges hasPdf={true} ocrStatus="done" />,
    );
    expect(screen.getByText(/含全文/)).toBeInTheDocument();
    expect(screen.getByText(/已OCR/)).toBeInTheDocument();
    expect(screen.queryByText(/仅题录/)).toBeNull();
  });

  it("hasPdf:false + ocrStatus:none → 仅题录徽章，无全文和 OCR 徽章", () => {
    render(
      <PaperStatusBadges hasPdf={false} ocrStatus="none" />,
    );
    const badge = screen.getByText(/仅题录/);
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("title", expect.stringContaining("无法用于研究空白精读"));
    expect(screen.queryByText(/含全文/)).toBeNull();
    expect(screen.queryByText(/已OCR/)).toBeNull();
  });

  it("hasPdf+pending → 含全文徽章 + 待OCR 徽章", () => {
    render(
      <PaperStatusBadges hasPdf={true} ocrStatus="pending" />,
    );
    expect(screen.getByText(/含全文/)).toBeInTheDocument();
    expect(screen.getByText(/待OCR/)).toBeInTheDocument();
  });

  it("hasPdf+failed → 含全文徽章 + OCR失败 徽章", () => {
    render(
      <PaperStatusBadges hasPdf={true} ocrStatus="failed" />,
    );
    expect(screen.getByText(/含全文/)).toBeInTheDocument();
    expect(screen.getByText(/OCR失败/)).toBeInTheDocument();
  });

  it("hasPdf+processing → 含全文徽章 + 解析中 徽章", () => {
    render(
      <PaperStatusBadges hasPdf={true} ocrStatus="processing" />,
    );
    expect(screen.getByText(/含全文/)).toBeInTheDocument();
    expect(screen.getByText(/解析中/)).toBeInTheDocument();
  });

  it("sciverseDocId 非空且无 PDF 时显示含全文", () => {
    render(
      <PaperStatusBadges hasPdf={false} ocrStatus="none" sciverseDocId="doc-1" />,
    );
    expect(screen.getByText(/含全文/)).toBeInTheDocument();
    expect(screen.queryByText(/仅题录/)).toBeNull();
  });
});
