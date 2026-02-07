"""
增量解析工具单元测试

测试 parse_partial_json_list, extract_fields_from_dict, safe_get_nested 函数。
"""
import pytest
from pydantic import BaseModel, ValidationError, Field

from app.services.ai.utils.partial_parser import (
    parse_partial_json_list,
    extract_fields_from_dict,
    safe_get_nested
)


class TestItem(BaseModel):
    """测试用的 Pydantic 模型"""
    cue_id: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)


class TestParsePartialJsonList:
    """测试 parse_partial_json_list 函数"""

    def test_valid_json_returns_all_items(self):
        """Given: 有效JSON When: 解析 Then: 返回所有项"""
        json_text = '[{"cue_id": 1, "text": "hello"}, {"cue_id": 2, "text": "world"}]'
        valid, invalid = parse_partial_json_list(json_text, TestItem)

        assert len(valid) == 2
        assert len(invalid) == 0
        assert valid[0].cue_id == 1
        assert valid[1].cue_id == 2

    def test_empty_json_returns_empty_lists(self):
        """Given: 空JSON数组 When: 解析 Then: 返回空列表"""
        json_text = '[]'
        valid, invalid = parse_partial_json_list(json_text, TestItem)

        assert valid == []
        assert invalid == []

    def test_invalid_json_format_returns_error(self):
        """Given: 无效JSON格式 When: 解析 Then: 返回错误信息"""
        json_text = '{invalid json}'
        valid, invalid = parse_partial_json_list(json_text, TestItem)

        assert valid == []
        assert len(invalid) == 1
        assert "JSON 解析失败" in invalid[0]

    def test_non_list_root_returns_error(self):
        """Given: 根节点不是数组 When: 解析 Then: 返回错误信息"""
        json_text = '{"cue_id": 1, "text": "hello"}'
        valid, invalid = parse_partial_json_list(json_text, TestItem)

        assert valid == []
        assert len(invalid) == 1
        assert "根节点不是列表" in invalid[0]

    def test_partial_invalid_items_filters_correctly(self):
        """Given: 部分项无效 When: 解析 Then: 返回有效项和无效项描述"""
        json_text = '[{"cue_id": 1, "text": "valid"}, {"cue_id": -1, "text": "invalid"}, {"cue_id": 2, "text": "also valid"}]'
        valid, invalid = parse_partial_json_list(json_text, TestItem)

        assert len(valid) == 2
        assert len(invalid) == 1
        assert valid[0].cue_id == 1
        assert valid[1].cue_id == 2
        assert "索引 1" in invalid[0]

    def test_with_validation_func_passes_valid_items(self):
        """Given: 有效项和验证函数 When: 解析 Then: 通过验证的项被返回"""
        def validate_cue_id_positive(item):
            if item.cue_id < 0:
                raise ValueError("cue_id must be positive")

        json_text = '[{"cue_id": 1, "text": "hello"}, {"cue_id": 2, "text": "world"}]'
        valid, invalid = parse_partial_json_list(json_text, TestItem, validate_cue_id_positive)

        assert len(valid) == 2
        assert len(invalid) == 0

    def test_with_validation_func_filters_invalid_items(self):
        """Given: 验证函数拒绝某些项 When: 解析 Then: 无效项被过滤"""
        def validate_cue_id_even_only(item):
            if item.cue_id % 2 != 0:
                raise ValueError("cue_id must be even")

        json_text = '[{"cue_id": 1, "text": "odd"}, {"cue_id": 2, "text": "even"}]'
        valid, invalid = parse_partial_json_list(json_text, TestItem, validate_cue_id_even_only)

        assert len(valid) == 1
        assert valid[0].cue_id == 2
        assert len(invalid) == 1
        assert "索引 0" in invalid[0]


class TestExtractFieldsFromDict:
    """测试 extract_fields_from_dict 函数"""

    def test_extract_single_field(self):
        """Given: 单个映射 When: 提取 Then: 返回正确值"""
        data = {'title': 'hello', 'desc': 'world'}
        mappings = {'name': ['title', 'name']}

        result = extract_fields_from_dict(data, mappings)

        assert result == {'name': 'hello'}

    def test_extract_multiple_fields(self):
        """Given: 多个映射 When: 提取 Then: 返回所有映射"""
        data = {'title': 'hello', 'desc': 'world', 'date': '2026-02-07'}
        mappings = {
            'name': ['title', 'name'],
            'content': ['desc', 'content'],
            'created': ['date']
        }

        result = extract_fields_from_dict(data, mappings)

        assert result == {'name': 'hello', 'content': 'world', 'created': '2026-02-07'}

    def test_fallback_to_alias(self):
        """Given: 第一个字段不存在 When: 提取 Then: 使用别名"""
        data = {'name': 'fallback', 'desc': 'content'}
        mappings = {'title': ['title', 'name']}

        result = extract_fields_from_dict(data, mappings)

        assert result == {'title': 'fallback'}

    def test_missing_field_returns_empty(self):
        """Given: 字段不存在 When: 提取 Then: 结果中不包含该字段"""
        data = {'desc': 'content'}
        mappings = {'title': ['title', 'name']}

        result = extract_fields_from_dict(data, mappings)

        assert result == {}

    def test_null_value_is_skipped(self):
        """Given: 字段值为 None When: 提取 Then: 跳过该值，尝试下一个别名"""
        data = {'title': None, 'name': 'actual'}
        mappings = {'title': ['title', 'name']}

        result = extract_fields_from_dict(data, mappings)

        assert result == {'title': 'actual'}

    def test_empty_string_is_considered_valid(self):
        """Given: 字段值为空字符串 When: 提取 Then: 空字符串是有效值"""
        data = {'title': '', 'name': 'fallback'}
        mappings = {'title': ['title', 'name']}

        result = extract_fields_from_dict(data, mappings)

        assert result == {'title': ''}


class TestSafeGetNested:
    """测试 safe_get_nested 函数"""

    def test_get_nested_value(self):
        """Given: 嵌套字典 When: 获取 Then: 返回正确值"""
        data = {'a': {'b': {'c': 'value'}}}

        result = safe_get_nested(data, 'a', 'b', 'c')

        assert result == 'value'

    def test_missing_key_returns_default(self):
        """Given: 路径中键不存在 When: 获取 Then: 返回默认值"""
        data = {'a': {'b': {'c': 'value'}}}

        result = safe_get_nested(data, 'a', 'x', 'y', default='default')

        assert result == 'default'

    def test_non_dict_middle_value_returns_default(self):
        """Given: 中间值不是字典 When: 获取 Then: 返回默认值"""
        data = {'a': {'b': 'not_a_dict'}}

        result = safe_get_nested(data, 'a', 'b', 'c', default='default')

        assert result == 'default'

    def test_default_is_none(self):
        """Given: 不提供默认值 When: 获取失败 Then: 返回 None"""
        data = {'a': {'b': 'value'}}

        result = safe_get_nested(data, 'a', 'x', 'y')

        assert result is None

    def test_empty_path_returns_original_data(self):
        """Given: 空路径 When: 获取 Then: 返回原始数据"""
        data = {'a': 'value'}

        result = safe_get_nested(data)

        assert result == data

    def test_single_level_key(self):
        """Given: 单层键 When: 获取 Then: 返回对应值"""
        data = {'key': 'value'}

        result = safe_get_nested(data, 'key')

        assert result == 'value'
