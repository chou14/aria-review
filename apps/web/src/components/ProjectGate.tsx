import type React from "react";
import { ErrMsg, Loading } from "../lib/ui";

type ProjectQueryState = {
  isLoading?: boolean;
  error?: unknown;
  refetch?: () => unknown;
  /** 有缓存数据时后台刷新失败不阻断页面（stale-while-error） */
  data?: unknown;
};

interface ProjectGateProps {
  project: ProjectQueryState;
  children: React.ReactNode;
  loadingLabel?: string;
}

// 项目查询的页面级三态闸门：只有 project 成功后，页面内才判断语料是否就绪。
export function ProjectGate({ project, children, loadingLabel = "加载项目…" }: ProjectGateProps) {
  if (project.isLoading) {
    return <Loading label={loadingLabel} />;
  }

  if (project.error && project.data == null) {
    return (
      <ErrMsg
        error={project.error}
        action={
          project.refetch ? (
            <button type="button" className="btn" onClick={() => project.refetch?.()}>
              重试
            </button>
          ) : null
        }
      />
    );
  }

  return <>{children}</>;
}
