// 路由级错误边界：优先识别 lazy chunk 失效，避免部署后旧 chunk 404 造成白屏。
import { Component, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

interface RouteErrorBoundaryProps {
  children: ReactNode;
  onChunkRetry?: () => void;
}

interface InnerProps extends RouteErrorBoundaryProps {
  resetKey: string;
}

interface State {
  error: unknown;
}

export function isChunkLoadError(error: unknown): boolean {
  const name = typeof error === "object" && error && "name" in error ? String(error.name) : "";
  const message = error instanceof Error ? error.message : String(error ?? "");
  const text = `${name} ${message}`.toLowerCase();

  return [
    "chunkloaderror",
    "loading chunk",
    "failed to fetch dynamically imported module",
    "error loading dynamically imported module",
    "importing a module script failed",
    "modulepreload",
    "css_chunk_load_failed",
  ].some((needle) => text.includes(needle));
}

function errorDetails(error: unknown): string {
  if (error instanceof Error) {
    return error.stack || `${error.name}: ${error.message}`;
  }
  return String(error ?? "未知错误");
}

class RouteErrorBoundaryInner extends Component<InnerProps, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  componentDidUpdate(prevProps: InnerProps): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: unknown): void {
    // 仅记录，不上报；路由层负责给用户可恢复出口。
    console.error("RouteErrorBoundary 捕获路由错误:", error);
  }

  private retryChunk = (): void => {
    if (this.props.onChunkRetry) {
      this.props.onChunkRetry();
      return;
    }
    window.location.reload();
  };

  private retryRender = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;

    const chunkError = isChunkLoadError(this.state.error);
    return (
      <div className="container" style={{ paddingTop: "2rem" }}>
        <div className="card" role="alert" style={{ maxWidth: 640, margin: "0 auto", padding: "2rem" }}>
          <h2 style={{ margin: "0 0 0.5rem" }}>{chunkError ? "加载失败" : "页面渲染出错"}</h2>
          <p style={{ margin: "0 0 1.25rem", color: "var(--ink-3)", fontSize: "0.9rem" }}>
            {chunkError
              ? "当前页面资源加载失败，可能是应用已更新导致旧资源失效。请重试加载。"
              : "当前路由遇到了渲染异常。你可以先重试；若仍失败，请保留错误详情排查。"}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={chunkError ? this.retryChunk : this.retryRender}>
              重试
            </button>
            <a className="btn" href="/">
              返回首页
            </a>
          </div>
          {!chunkError && (
            <details style={{ marginTop: "1.25rem", color: "var(--ink-2)", fontSize: "0.85rem" }}>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>查看错误详情</summary>
              <pre
                style={{
                  margin: "0.75rem 0 0",
                  whiteSpace: "pre-wrap",
                  overflowX: "auto",
                  background: "var(--paper-2)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-sm)",
                  padding: "0.85rem 1rem",
                }}
              >
                {errorDetails(this.state.error)}
              </pre>
            </details>
          )}
        </div>
      </div>
    );
  }
}

export function RouteErrorBoundary({ children, onChunkRetry }: RouteErrorBoundaryProps) {
  const location = useLocation();
  const resetKey = `${location.pathname}${location.search}`;

  return (
    <RouteErrorBoundaryInner resetKey={resetKey} onChunkRetry={onChunkRetry}>
      {children}
    </RouteErrorBoundaryInner>
  );
}
