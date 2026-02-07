"""
AI 服务工具集

提供增量解析、兜底处理等通用工具。
"""

from .partial_parser import (
    parse_partial_json_list,
    extract_fields_from_dict,
    safe_get_nested
)

from .fallback import (
    ai_fallback,
    silent_fallback,
    log_and_reraise
)

__all__ = [
    # partial_parser
    'parse_partial_json_list',
    'extract_fields_from_dict',
    'safe_get_nested',
    # fallback
    'ai_fallback',
    'silent_fallback',
    'log_and_reraise',
]
