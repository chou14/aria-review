import type { components } from "./schema";

export type RunStatus = components["schemas"]["RunStatus"];
export type ScratchpadRunStatus = components["schemas"]["ScratchpadState"]["run_status"];

export const RUN_STATUS_RUNNING: RunStatus = "running";
export const RUN_STATUS_DONE: RunStatus = "done";
export const RUN_STATUS_FAILED: RunStatus = "failed";
export const RUN_STATUS_CANCELLED: RunStatus = "cancelled";

export function normalizeRunStatus(status: string | undefined): RunStatus {
  // deprecated: 历史 run_complete 可能带 completed，入口兼容为 done。
  return status === "completed" ? RUN_STATUS_DONE : (status as RunStatus);
}

export function isTerminalScratchpadRunStatus(status: ScratchpadRunStatus | undefined): boolean {
  return status === RUN_STATUS_DONE || status === RUN_STATUS_FAILED;
}
