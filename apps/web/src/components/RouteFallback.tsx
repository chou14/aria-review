// 路由级加载态：给 lazy page 一个轻量、居中的全局兜底，避免慢网切页白屏。
export function RouteLoadingFallback({ label = "页面加载中…" }: { label?: string }) {
  return (
    <div className="container" style={{ paddingTop: "2rem" }}>
      <div
        style={{
          minHeight: "min(420px, calc(100vh - 140px))",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          className="state"
          role="status"
          aria-busy="true"
          aria-live="polite"
          style={{ justifyContent: "center" }}
        >
          <span className="spinner" />
          <span>{label}</span>
        </div>
      </div>
    </div>
  );
}
