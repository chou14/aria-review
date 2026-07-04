/**
 * RequireAuth — 路由守卫（Phase B）。未登录 → 跳 /login（记住来源路径）。
 * 作为 layout route 的 element，用 <Outlet/> 渲染受保护子路由。
 */
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export function RequireAuth() {
  const { isLoading, isAuthenticated } = useAuth();
  const loc = useLocation();

  // DEV/E2E：放行守卫，保持现有 playwright e2e 与本地开发不被登录阻挡；生产构建守卫生效。
  if (import.meta.env.DEV) return <Outlet />;

  if (isLoading) {
    return (
      <div
        className="container"
        style={{ paddingTop: "3rem", textAlign: "center", color: "var(--ink-3)" }}
      >
        加载中…
      </div>
    );
  }
  if (!isAuthenticated) {
    // 首页路人 → 公开落地页讲清楚产品；深链接/会话过期 → 直接回登录（保留 from，登录后原路返回）。
    if (loc.pathname === "/") {
      return <Navigate to="/welcome" replace />;
    }
    return <Navigate to="/login" state={{ from: loc.pathname + loc.search }} replace />;
  }
  return <Outlet />;
}
