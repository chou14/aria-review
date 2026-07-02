"""检索契约常量。

SearchTool 与 schema 共享同一上限，避免前后端/R 端语义漂移。
"""

SEARCH_LIMIT_MAX = 500
SEARCH_LIMIT_ERROR_MESSAGE = f"检索上限 {SEARCH_LIMIT_MAX}"
