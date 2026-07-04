"""检索候选元数据清洗辅助。"""
from __future__ import annotations

import math
from typing import Any


def parse_year(value: Any, date_hint: Any = None) -> int | None:
    """把检索候选的出版年归一为 int（Sciverse 返回 float 如 2025.0；str 亦兼容）。

    value 无效时从 date_hint（如 '2025-08-18'）前 4 位兜底。范围外(1500-2100)返回 None。
    """
    for candidate in (value, str(date_hint or "")[:4]):
        if candidate is None or isinstance(candidate, bool):
            continue
        try:
            if isinstance(candidate, str):
                text = candidate.strip()
                if not text:
                    continue
                parsed = int(float(text))
            elif isinstance(candidate, float):
                if not math.isfinite(candidate):
                    continue
                parsed = int(candidate)
            else:
                parsed = int(candidate)
        except (TypeError, ValueError, OverflowError):
            continue
        if 1500 <= parsed <= 2100:
            return parsed
    return None


def parse_cited_by_count(value: Any) -> int | None:
    """把检索候选的 citedByCount 归一为非负整数；无效/负值返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            parsed = int(float(text))
        elif isinstance(value, float):
            if not math.isfinite(value):
                return None
            parsed = int(value)
        else:
            parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None

