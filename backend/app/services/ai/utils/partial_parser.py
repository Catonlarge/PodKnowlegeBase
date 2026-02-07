"""
增量解析工具 - 用于从损坏的 JSON 中提取有效数据

支持从部分损坏的 JSON 响应中提取有效数据，实现增量保存策略。
"""
import json
from typing import List, Dict, Any, TypeVar, Type, Callable, Tuple
from pydantic import BaseModel, ValidationError
from loguru import logger

T = TypeVar('T', bound=BaseModel)


def parse_partial_json_list(
    json_text: str,
    schema: Type[T],
    validate_func: Callable[[T], None] = None
) -> Tuple[List[T], List[str]]:
    """
    从 JSON 数组中增量解析有效项

    Args:
        json_text: JSON 文本
        schema: Pydantic 模型类
        validate_func: 额外的业务验证函数

    Returns:
        (valid_items, invalid_items): 有效项列表和无效项描述

    Example:
        >>> valid, invalid = parse_partial_json_list(
        ...     '[{"cue_id": 1, "text": "hello"}, {"cue_id": 2, "text": null}]',
        ...     TranslationItem
        ... )
        >>> len(valid)
        1
        >>> len(invalid)
        1
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}")
        return [], [f"JSON 解析失败: {str(e)[:100]}"]

    if not isinstance(data, list):
        logger.warning(f"根节点不是列表，类型: {type(data).__name__}")
        return [], [f"根节点不是列表，类型: {type(data).__name__}"]

    valid_items = []
    invalid_items = []

    for idx, item in enumerate(data):
        try:
            validated = schema.model_validate(item)
            if validate_func:
                validate_func(validated)
            valid_items.append(validated)
        except ValidationError as e:
            error_msg = f"索引 {idx}: {str(e)[:100]}"
            invalid_items.append(error_msg)
            logger.debug(f"Schema 验证失败: {error_msg}")
        except Exception as e:
            error_msg = f"索引 {idx}: {str(e)[:100]}"
            invalid_items.append(error_msg)
            logger.debug(f"业务验证失败: {error_msg}")

    logger.info(f"增量解析完成: {len(valid_items)} 有效, {len(invalid_items)} 无效")
    return valid_items, invalid_items


def extract_fields_from_dict(
    data: Dict[str, Any],
    field_mappings: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    从字典中提取指定字段（支持别名映射）

    Args:
        data: 原始字典
        field_mappings: {'目标字段': ['源字段1', '源字段2', ...]}

    Returns:
        提取后的字典

    Example:
        >>> data = {'title': 'hello', 'desc': 'world', 'extra': 'ignore'}
        >>> mappings = {'name': ['title', 'name'], 'content': ['desc', 'content']}
        >>> extract_fields_from_dict(data, mappings)
        {'name': 'hello', 'content': 'world'}
    """
    result = {}
    for target_field, source_fields in field_mappings.items():
        for source_field in source_fields:
            # 仅当字段存在且值不为 None 时才使用（空字符串是有效值）
            if source_field in data and data[source_field] is not None:
                result[target_field] = data[source_field]
                break
    return result


def safe_get_nested(data: Dict[str, Any], *keys, default=None):
    """
    安全获取嵌套字典的值

    Args:
        data: 字典数据
        *keys: 键路径
        default: 默认值

    Returns:
        获取的值或默认值

    Example:
        >>> data = {'a': {'b': {'c': 'value'}}}
        >>> safe_get_nested(data, 'a', 'b', 'c')
        'value'
        >>> safe_get_nested(data, 'a', 'x', 'y', default='default')
        'default'
    """
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
