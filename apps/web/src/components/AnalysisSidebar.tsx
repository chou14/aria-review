/**
 * AnalysisSidebar.tsx — 分析区左侧分组导航
 *
 * 4 组 × 13 视图，可折叠到图标轨（collapsed 态）。
 * 复用 styles.css 的 .sidebar/.sidebar-section/.sidebar-item 等现有类。
 * 当前选中项高亮（--cinnabar）。未就绪的组（需要 activeCorpus）在无语料时置灰。
 */
import type { ActiveCorpus } from "../api/agentHooks";
import {
  ANALYSIS_GROUPS,
  findViewMeta,
  type AnalysisViewId,
} from "./analysisViews";
import type { AnalysisViewDefinition } from "./analysisViews";

export { ANALYSIS_GROUPS, findViewMeta };
export type { AnalysisViewId };

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

interface AnalysisSidebarProps {
  activeView: AnalysisViewId;
  onSelect: (view: AnalysisViewId) => void;
  activeCorpus: ActiveCorpus | null | undefined;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function AnalysisSidebar({
  activeView,
  onSelect,
  activeCorpus,
  collapsed,
  onToggleCollapse,
}: AnalysisSidebarProps) {
  const corpusReady = activeCorpus?.status === "ready";

  return (
    <aside
      className={`sidebar${collapsed ? " collapsed" : ""}`}
      aria-label="分析导航"
      style={{ position: "sticky", top: "var(--topbar-h, 54px)", alignSelf: "flex-start", zIndex: 5 }}
    >
      {/* 折叠切换按钮 */}
      <button
        className="sidebar-item"
        onClick={onToggleCollapse}
        title={collapsed ? "展开侧边栏" : "折叠侧边栏"}
        aria-label={collapsed ? "展开侧边栏" : "折叠侧边栏"}
        style={{ justifyContent: "center", borderBottom: "1px solid var(--line)", padding: "0.55rem" }}
      >
        <span style={{ fontSize: "0.88rem" }}>{collapsed ? "▶" : "◀"}</span>
        {!collapsed && <span style={{ fontSize: "0.78rem", color: "var(--ink-3)", marginLeft: 2 }}>收起</span>}
      </button>

      {/* 4 分组 */}
      {ANALYSIS_GROUPS.map((group) => {
        // 组级置灰：仅当组内全部视图都需 corpus 且语料未就绪（部分视图可用时不整组置灰）。
        const groupDisabled =
          !corpusReady && group.views.every((view: AnalysisViewDefinition) => view.requiresCorpus);
        return (
          <div
            key={group.key}
            className="sidebar-section"
            style={{ opacity: groupDisabled ? 0.45 : 1 }}
            aria-disabled={groupDisabled}
          >
            {/* 分组标题（折叠态只显示图标） */}
            {!collapsed && (
              <div className="sidebar-title" title={groupDisabled ? "需要先构建分析语料" : undefined}>
                {group.label}
                {groupDisabled && (
                  <span
                    style={{ marginLeft: "0.35rem", fontSize: "0.68rem", color: "var(--ink-3)" }}
                    title="需先构建语料"
                  >
                    (未就绪)
                  </span>
                )}
              </div>
            )}

            {/* 视图条目：逐视图按 registry.requiresCorpus 判定置灰。 */}
            {group.views.map((view) => {
              const isActive = activeView === view.id;
              const disabled = !corpusReady && view.requiresCorpus;
              return (
                <button
                  key={view.id}
                  className={`sidebar-item${isActive ? " active" : ""}`}
                  onClick={() => !disabled && onSelect(view.id)}
                  disabled={disabled}
                  title={collapsed ? `${view.label}：${view.desc}` : view.desc}
                  aria-current={isActive ? "page" : undefined}
                  style={{
                    cursor: disabled ? "not-allowed" : "pointer",
                    justifyContent: collapsed ? "center" : "flex-start",
                  }}
                >
                  <span style={{ fontSize: "1rem", flexShrink: 0 }}>{view.icon}</span>
                  {!collapsed && <span>{view.label}</span>}
                </button>
              );
            })}
          </div>
        );
      })}
    </aside>
  );
}
