"""
跨平台标题清理工具

确保标题在 Obsidian (Markdown) 和 Notion 中正确显示。
"""

import re
from typing import Optional

# 跨平台标题配置
DISPLAY_TITLE_MAX_LENGTH = 100  # Notion API 建议长度
DISPLAY_TITLE_ELLIPSIS = "..."


def sanitize_title(title: str, max_length: Optional[int] = None) -> str:
    """
    清理标题，确保跨平台兼容性。

    处理规则:
    1. 移除换行符和回车符
    2. 去除首尾空白
    3. 限制长度（截断并添加省略号）
    4. 保留原始特殊字符（由各平台渲染时处理转义）

    Args:
        title: 原始标题
        max_length: 最大长度（默认使用 DISPLAY_TITLE_MAX_LENGTH）

    Returns:
        str: 清理后的标题

    Examples:
        >>> sanitize_title("Hello\\nWorld")
        'Hello World'
        >>> sanitize_title("A" * 150)
        'AAA...AAA' (100 chars + ...)
    """
    if not title:
        return ""

    # 1. 移除换行符，替换为空格
    cleaned = re.sub(r'[\n\r]+', ' ', title)

    # 2. 去除首尾空白
    cleaned = cleaned.strip()

    # 3. 移除多余的内部空格
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # 4. 限制长度
    limit = max_length or DISPLAY_TITLE_MAX_LENGTH
    if len(cleaned) > limit:
        # 截断并添加省略号
        ellipsis_length = len(DISPLAY_TITLE_ELLIPSIS)
        truncate_length = limit - ellipsis_length
        cleaned = cleaned[:truncate_length] + DISPLAY_TITLE_ELLIPSIS

    return cleaned
