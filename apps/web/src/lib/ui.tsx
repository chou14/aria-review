import type React from "react";

// 共享的查询态展示 (DRY: 各分析页复用)
export function Loading({ label }: { label: string }) {
  return (
    <div className="state" aria-live="polite">
      <span className="spinner" /> {label}
    </div>
  );
}

type FriendlyError = Error & {
  friendlyMessage?: string;
  originalMessage?: string;
};

function getDisplayMessage(error: unknown): string {
  const err = error as FriendlyError | undefined;
  return err?.friendlyMessage ?? err?.message ?? "出错了";
}

function getOriginalMessage(error: unknown): string | undefined {
  const err = error as FriendlyError | undefined;
  return err?.originalMessage;
}

export function ErrMsg({
  error,
  action,
}: {
  error: unknown;
  action?: React.ReactNode;
}) {
  const message = getDisplayMessage(error);
  const originalMessage = getOriginalMessage(error);
  const showOriginal = !!originalMessage && originalMessage !== message;

  return (
    <div className="state state-err" role="alert">
      <div>{message}</div>
      {action}
      {showOriginal && (
        <details>
          <summary>查看原始错误</summary>
          <pre>{originalMessage}</pre>
        </details>
      )}
    </div>
  );
}

// 作者格式化 (DRY): 兼容字符串与 CSL 对象 ({literal} / {family,given})
type CreatorLike = string | { family?: string; given?: string; literal?: string };
export function formatCreators(creators?: CreatorLike[]): string {
  if (!creators || creators.length === 0) return "";
  return creators
    .map((c) => {
      if (typeof c === "string") return c;
      if (c.literal) return c.literal;
      return [c.given, c.family].filter(Boolean).join(" ");
    })
    .filter(Boolean)
    .join("; ");
}

// 表格单元格样式 (沿用; 与全局 table.tbl 协同)
export const cell: React.CSSProperties = {
  borderBottom: "1px solid var(--line)",
  padding: "6px 10px",
  textAlign: "left",
};
