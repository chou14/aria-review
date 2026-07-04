/**
 * PaperStatusBadges.tsx — 文献逐篇 PDF/OCR/元数据状态徽章（Task 6）
 *
 * 按 paper 的 hasPdf/sciverseDocId/ocrStatus 渲染徽章：
 *   含全文       — hasPdf=true 或 sciverseDocId 非空
 *   已OCR       — ocrStatus="done"
 *   解析中      — ocrStatus="processing"
 *   待OCR       — ocrStatus="pending"
 *   OCR失败     — ocrStatus="failed"
 *   仅题录       — hasPdf=false 且无 sciverseDocId（无全文）
 *
 * 无障碍: title + aria-label 双保险，屏幕阅读器可达。
 */

type OcrStatus = "none" | "pending" | "processing" | "done" | "failed";

interface Props {
  hasPdf: boolean;
  ocrStatus: OcrStatus;
  sciverseDocId?: string | null;
  hasReadableFulltext?: boolean | null;
}

export function PaperStatusBadges({ hasPdf, ocrStatus, sciverseDocId, hasReadableFulltext }: Props) {
  const hasSciverseDoc = !!sciverseDocId?.trim();
  const hasFulltext = Boolean(hasPdf || hasSciverseDoc || hasReadableFulltext);

  return (
    <span className="paper-status-badges">
      {hasFulltext ? (
        <>
          <span
            className="paper-badge paper-badge--fulltext"
            title={hasPdf ? "已有全文附件" : "Sciverse 可拉取全文"}
            aria-label={hasPdf ? "已有全文附件" : "Sciverse 可拉取全文"}
          >
            含全文
          </span>
          {/* OCR 状态 */}
          {hasPdf && ocrStatus === "done" && (
            <span
              className="paper-badge paper-badge--ocr-done"
              title="PDF 已完成 OCR 解析，可用作综述语料"
              aria-label="PDF 已完成 OCR 解析，可用作综述语料"
            >
              已OCR
            </span>
          )}
          {hasPdf && ocrStatus === "processing" && (
            <span
              className="paper-badge paper-badge--ocr-pending"
              title="PDF 正在 OCR 解析中，请稍候"
              aria-label="PDF 正在 OCR 解析中，请稍候"
            >
              解析中
            </span>
          )}
          {hasPdf && ocrStatus === "pending" && (
            <span
              className="paper-badge paper-badge--ocr-pending"
              title="PDF 等待 OCR 解析队列"
              aria-label="PDF 等待 OCR 解析队列"
            >
              待OCR
            </span>
          )}
          {hasPdf && ocrStatus === "failed" && (
            <span
              className="paper-badge paper-badge--ocr-failed"
              title="OCR 解析失败，可删除后重新上传 PDF"
              aria-label="OCR 解析失败，可删除后重新上传 PDF"
            >
              OCR失败
            </span>
          )}
        </>
      ) : (
        /* 无全文 — 仅题录 */
        <span
          className="paper-badge paper-badge--meta-only"
          title="仅题录元数据，无法用于研究空白精读，可尝试补全文"
          aria-label="仅题录元数据，无法用于研究空白精读，可尝试补全文"
        >
          仅题录
        </span>
      )}
    </span>
  );
}
