"""Run 状态常量与兼容归一化。"""
from __future__ import annotations

from typing import Literal

RunStatus = Literal[
    "queued",
    "running",
    "awaiting_confirmation",
    "paused",
    "done",
    "failed",
    "cancelled",
]

RUN_STATUS_VALUES: tuple[RunStatus, ...] = (
    "queued",
    "running",
    "awaiting_confirmation",
    "paused",
    "done",
    "failed",
    "cancelled",
)
RUN_TERMINAL_STATUSES: tuple[str, ...] = ("done", "failed", "cancelled", "error")
RUN_STATUS_DEPRECATED_ALIASES = {
    # deprecated: 历史 research run 曾对外输出 completed；入口继续兼容为 done。
    "completed": "done",
}


def normalize_run_status(status: str | None, *, default: RunStatus = "running") -> str:
    """把历史别名归一为当前 run 状态命名。

    只归一已知别名，未知值**原样透传**：零伪造 demo/runlog 用 "error" 作拒绝终态
    （可验证工件口径，不得改写）；静默吞掉未知状态会把 error 变 running，
    属于静默数据破坏（本函数上线首日即因此吞过 demo 的 error）。
    """
    if status is None:
        return default
    return RUN_STATUS_DEPRECATED_ALIASES.get(status, status)


def is_terminal_run_status(status: str | None) -> bool:
    """判断 run 是否处于终态，兼容历史 completed 别名与 runlog 的 error。"""
    return normalize_run_status(status) in RUN_TERMINAL_STATUSES
