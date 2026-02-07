"""
Unit Tests for Translation Schema

This module tests the Pydantic schemas for translation service.
Tests follow BDD naming convention and avoid conditional logic.
"""
import pytest
from pydantic import ValidationError

from app.services.ai.schemas.translation_schema import (
    TranslationItem,
    TranslationResponse
)


class TestTranslationItem:
    """测试 TranslationItem 模型"""

    def test_valid_translation_item_with_minimal_data_passes_validation(self):
        """
        Given: 包含最小有效数据的 TranslationItem
        When: 创建模型实例
        Then: 验证通过，字段正确赋值
        """
        item = TranslationItem(
            cue_id=1,
            original_text="Hello world",
            translated_text="你好世界"
        )

        assert item.cue_id == 1
        assert item.original_text == "Hello world"
        assert item.translated_text == "你好世界"

    def test_valid_translation_item_with_maximal_data_passes_validation(self):
        """
        Given: 包含最大有效数据的 TranslationItem
        When: 创建模型实例
        Then: 验证通过
        """
        item = TranslationItem(
            cue_id=99999,
            original_text="a" * 500,
            translated_text="b" * 500
        )

        assert item.cue_id == 99999
        assert len(item.original_text) == 500
        assert len(item.translated_text) == 500

    def test_valid_translation_item_with_chinese_text_passes_validation(self):
        """
        Given: 包含中文文本的 TranslationItem
        When: 创建模型实例
        Then: 验证通过
        """
        item = TranslationItem(
            cue_id=1,
            original_text="Hello world",
            translated_text="你好，这是一个测试翻译的内容"
        )

        assert item.translated_text == "你好，这是一个测试翻译的内容"

    def test_translation_item_with_zero_cue_id_raises_validation_error(self):
        """
        Given: cue_id 为 0
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            TranslationItem(
                cue_id=0,
                original_text="Hello",
                translated_text="你好"
            )

    def test_translation_item_with_negative_cue_id_raises_validation_error(self):
        """
        Given: cue_id 为负数
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            TranslationItem(
                cue_id=-1,
                original_text="Hello",
                translated_text="你好"
            )

    def test_translation_item_with_empty_original_text_raises_validation_error(self):
        """
        Given: original_text 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            TranslationItem(
                cue_id=1,
                original_text="",
                translated_text="你好"
            )

    def test_translation_item_with_too_long_original_text_raises_validation_error(self):
        """
        Given: original_text 长度大于 500
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            TranslationItem(
                cue_id=1,
                original_text="a" * 501,
                translated_text="你好"
            )

    def test_translation_item_with_empty_translated_text_raises_validation_error(self):
        """
        Given: translated_text 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            TranslationItem(
                cue_id=1,
                original_text="Hello",
                translated_text=""
            )

    def test_translation_item_with_too_long_translated_text_raises_validation_error(self):
        """
        Given: translated_text 长度大于 500
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            TranslationItem(
                cue_id=1,
                original_text="Hello",
                translated_text="a" * 501
            )

    def test_translation_item_with_special_characters_passes_validation(self):
        """
        Given: 包含特殊字符的文本
        When: 创建模型实例
        Then: 验证通过
        """
        item = TranslationItem(
            cue_id=1,
            original_text="Hello! @#$%^&*()",
            translated_text="你好！@#$%^&*()"
        )

        assert item.original_text == "Hello! @#$%^&*()"
        assert item.translated_text == "你好！@#$%^&*()"


class TestTranslationResponse:
    """测试 TranslationResponse 模型"""

    def test_valid_response_with_empty_translations_list_passes_validation(self):
        """
        Given: 包含空 translations 列表的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = TranslationResponse(translations=[])

        assert len(response.translations) == 0

    def test_valid_response_with_single_translation_passes_validation(self):
        """
        Given: 包含单个 translation 的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = TranslationResponse(
            translations=[
                TranslationItem(
                    cue_id=1,
                    original_text="Hello world",
                    translated_text="你好世界"
                )
            ]
        )

        assert len(response.translations) == 1
        assert response.translations[0].cue_id == 1

    def test_valid_response_with_multiple_unique_translations_passes_validation(self):
        """
        Given: 包含多个不同 cue_id 的 translation 的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = TranslationResponse(
            translations=[
                TranslationItem(
                    cue_id=1,
                    original_text="Hello",
                    translated_text="你好"
                ),
                TranslationItem(
                    cue_id=2,
                    original_text="World",
                    translated_text="世界"
                ),
                TranslationItem(
                    cue_id=3,
                    original_text="Good morning",
                    translated_text="早上好"
                ),
            ]
        )

        assert len(response.translations) == 3

    def test_response_with_duplicate_cue_ids_raises_validation_error(self):
        """
        Given: 包含重复 cue_id 的 translations
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="存在重复的cue_id"):
            TranslationResponse(
                translations=[
                    TranslationItem(
                        cue_id=1,
                        original_text="Hello",
                        translated_text="你好"
                    ),
                    TranslationItem(
                        cue_id=1,
                        original_text="World",
                        translated_text="世界"
                    ),
                ]
            )

    def test_response_with_multiple_duplicate_cue_ids_raises_validation_error(self):
        """
        Given: 包含多组重复 cue_id 的 translations
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="存在重复的cue_id"):
            TranslationResponse(
                translations=[
                    TranslationItem(
                        cue_id=1,
                        original_text="Text1",
                        translated_text="译文1"
                    ),
                    TranslationItem(
                        cue_id=1,
                        original_text="Text2",
                        translated_text="译文2"
                    ),
                    TranslationItem(
                        cue_id=2,
                        original_text="Text3",
                        translated_text="译文3"
                    ),
                    TranslationItem(
                        cue_id=2,
                        original_text="Text4",
                        translated_text="译文4"
                    ),
                ]
            )

    def test_response_default_factory_creates_empty_list(self):
        """
        Given: 不提供 translations 参数
        When: 创建模型实例
        Then: translations 默认为空列表
        """
        response = TranslationResponse()

        assert response.translations == []
        assert isinstance(response.translations, list)

    def test_response_json_serialization_deserialization(self):
        """
        Given: 有效的 TranslationResponse
        When: 序列化为 JSON 再反序列化
        Then: 数据保持一致
        """
        original = TranslationResponse(
            translations=[
                TranslationItem(
                    cue_id=1,
                    original_text="Hello world",
                    translated_text="你好世界"
                ),
                TranslationItem(
                    cue_id=2,
                    original_text="Good morning",
                    translated_text="早上好"
                ),
            ]
        )

        # 序列化
        json_str = original.model_dump_json()

        # 反序列化
        restored = TranslationResponse.model_validate_json(json_str)

        assert len(restored.translations) == 2
        assert restored.translations[0].cue_id == 1
        assert restored.translations[1].cue_id == 2
        assert restored.translations[0].translated_text == "你好世界"
        assert restored.translations[1].original_text == "Good morning"

    def test_response_preserves_original_text_in_translations(self):
        """
        Given: 包含原文的翻译响应
        When: 创建模型实例
        Then: 原文正确保留
        """
        response = TranslationResponse(
            translations=[
                TranslationItem(
                    cue_id=1,
                    original_text="The quick brown fox",
                    translated_text="敏捷的棕色狐狸"
                ),
                TranslationItem(
                    cue_id=2,
                    original_text="jumps over the lazy dog",
                    translated_text="跳过了懒狗"
                ),
            ]
        )

        assert response.translations[0].original_text == "The quick brown fox"
        assert response.translations[1].original_text == "jumps over the lazy dog"
