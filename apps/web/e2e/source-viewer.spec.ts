import { test, expect } from "@playwright/test";
import sampleMarkdown from "../../../packages/contracts/fixtures/sample_markdown.json" with { type: "json" };
import sampleStructure from "../../../packages/contracts/fixtures/sample_structure.json" with { type: "json" };

/**
 * F2 — SourceViewer 按 block 的 md_line_start/end 做行级高亮（markdown 级，必达档）。
 * 直接消费 packages/contracts/fixtures 共享契约样例，page.route 注入，不依赖后端。
 */
const MARKDOWN = sampleMarkdown;
// block_idx 3 = Abstract 正文（行 7：This study investigates…）
const FOCUS = sampleStructure.blocks.find((b) => b.block_idx === 3)!;

test("SourceViewer 按 block 高亮目标段", async ({ page }) => {
  await page.route("**/projects/*/papers/*/structure", (r) => r.fulfill({ json: sampleStructure }));
  await page.route("**/projects/*/papers/*/markdown", (r) => r.fulfill({ json: MARKDOWN }));

  await page.goto("/dev/source-viewer?paperId=10&blockIdx=" + FOCUS.block_idx);

  const hl = page.locator("[data-block-highlight='true']");
  await expect(hl).toBeVisible();
  // 高亮覆盖 block 真实行范围（7-10）的内容，不含相邻段
  await expect(hl).toContainText("This study investigates");
  await expect(hl).not.toContainText("Deep Learning Approaches"); // block 0 标题(行1)
  await expect(hl).not.toContainText("Bibliometric analysis has become"); // block 5(行11, 1 Introduction)
});
