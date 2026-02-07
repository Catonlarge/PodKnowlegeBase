"""
Unit Tests for Proofreading Schema

This module tests the Pydantic schemas for subtitle proofreading service.
Tests follow BDD naming convention and avoid conditional logic.
"""
import pytest
from pydantic import ValidationError

from app.services.ai.schemas.proofreading_schema import (
    CorrectionSuggestion,
    ProofreadingResponse
)


class TestCorrectionSuggestion:
    """测试 CorrectionSuggestion 模型"""

    def test_valid_correction_suggestion_with_minimal_data_passes_validation(self):
        """
        Given: 包含最小有效数据的 CorrectionSuggestion
        When: 创建模型实例
        Then: 验证通过，字段正确赋值
        """
        correction = CorrectionSuggestion(
            cue_id=1,
            original_text="Hello warld",
            corrected_text="Hello world",
            reason="拼写错误",
            confidence=0.95
        )

        assert correction.cue_id == 1
        assert correction.original_text == "Hello warld"
        assert correction.corrected_text == "Hello world"
        assert correction.reason == "拼写错误"
        assert correction.confidence == 0.95

    def test_valid_correction_suggestion_with_maximal_data_passes_validation(self):
        """
        Given: 包含最大有效数据的 CorrectionSuggestion
        When: 创建模型实例
        Then: 验证通过
        """
        correction = CorrectionSuggestion(
            cue_id=99999,
            original_text="a" * 500,
            corrected_text="b" * 500,
            reason="c" * 200,
            confidence=1.0
        )

        assert correction.cue_id == 99999
        assert len(correction.original_text) == 500
        assert len(correction.corrected_text) == 500
        assert len(correction.reason) == 200
        assert correction.confidence == 1.0

    def test_correction_suggestion_with_zero_cue_id_raises_validation_error(self):
        """
        Given: cue_id 为 0
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=0,
                original_text="Hello",
                corrected_text="Hi",
                reason="test",
                confidence=0.9
            )

    def test_correction_suggestion_with_negative_cue_id_raises_validation_error(self):
        """
        Given: cue_id 为负数
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=-1,
                original_text="Hello",
                corrected_text="Hi",
                reason="test",
                confidence=0.9
            )

    def test_correction_suggestion_with_empty_original_text_raises_validation_error(self):
        """
        Given: original_text 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="",
                corrected_text="Hi",
                reason="test",
                confidence=0.9
            )

    def test_correction_suggestion_with_too_long_original_text_raises_validation_error(self):
        """
        Given: original_text 长度大于 500
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="a" * 501,
                corrected_text="Hi",
                reason="test",
                confidence=0.9
            )

    def test_correction_suggestion_with_empty_corrected_text_raises_validation_error(self):
        """
        Given: corrected_text 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="Hello",
                corrected_text="",
                reason="test",
                confidence=0.9
            )

    def test_correction_suggestion_with_too_long_corrected_text_raises_validation_error(self):
        """
        Given: corrected_text 长度大于 500
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="Hello",
                corrected_text="a" * 501,
                reason="test",
                confidence=0.9
            )

    def test_correction_suggestion_with_empty_reason_raises_validation_error(self):
        """
        Given: reason 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="Hello",
                corrected_text="Hi",
                reason="",
                confidence=0.9
            )

    def test_correction_suggestion_with_too_long_reason_raises_validation_error(self):
        """
        Given: reason 长度大于 200
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="Hello",
                corrected_text="Hi",
                reason="a" * 201,
                confidence=0.9
            )

    def test_correction_suggestion_with_confidence_below_zero_raises_validation_error(self):
        """
        Given: confidence 小于 0.0
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="Hello",
                corrected_text="Hi",
                reason="test",
                confidence=-0.1
            )

    def test_correction_suggestion_with_confidence_above_one_raises_validation_error(self):
        """
        Given: confidence 大于 1.0
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            CorrectionSuggestion(
                cue_id=1,
                original_text="Hello",
                corrected_text="Hi",
                reason="test",
                confidence=1.1
            )

    def test_correction_suggestion_with_boundary_confidence_values_pass_validation(self):
        """
        Given: confidence 为边界值 0.0 和 1.0
        When: 创建模型实例
        Then: 验证通过
        """
        correction_min = CorrectionSuggestion(
            cue_id=1,
            original_text="Hello",
            corrected_text="Hi",
            reason="test",
            confidence=0.0
        )

        correction_max = CorrectionSuggestion(
            cue_id=2,
            original_text="World",
            corrected_text="Earth",
            reason="test2",
            confidence=1.0
        )

        assert correction_min.confidence == 0.0
        assert correction_max.confidence == 1.0


class TestProofreadingResponse:
    """测试 ProofreadingResponse 模型"""

    def test_response_with_empty_corrections_list_raises_validation_error(self):
        """
        Given: 包含空 corrections 列表的响应
        When: 创建模型实例
        Then: 抛出 ValidationError (至少需要1个修正建议)
        """
        with pytest.raises(ValidationError) as exc_info:
            ProofreadingResponse(corrections=[])
        assert "at least 1" in str(exc_info.value).lower() or "至少" in str(exc_info.value)

    def test_valid_response_with_single_correction_passes_validation(self):
        """
        Given: 包含单个 correction 的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = ProofreadingResponse(
            corrections=[
                CorrectionSuggestion(
                    cue_id=1,
                    original_text="Hello warld",
                    corrected_text="Hello world",
                    reason="拼写错误",
                    confidence=0.95
                )
            ]
        )

        assert len(response.corrections) == 1
        assert response.corrections[0].cue_id == 1

    def test_valid_response_with_multiple_unique_corrections_passes_validation(self):
        """
        Given: 包含多个不同 cue_id 的 correction 的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = ProofreadingResponse(
            corrections=[
                CorrectionSuggestion(
                    cue_id=1,
                    original_text="Text1",
                    corrected_text="Fixed1",
                    reason="reason1",
                    confidence=0.9
                ),
                CorrectionSuggestion(
                    cue_id=2,
                    original_text="Text2",
                    corrected_text="Fixed2",
                    reason="reason2",
                    confidence=0.8
                ),
                CorrectionSuggestion(
                    cue_id=3,
                    original_text="Text3",
                    corrected_text="Fixed3",
                    reason="reason3",
                    confidence=0.95
                ),
            ]
        )

        assert len(response.corrections) == 3

    def test_response_with_duplicate_cue_ids_raises_validation_error(self):
        """
        Given: 包含重复 cue_id 的 corrections
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="存在重复的cue_id"):
            ProofreadingResponse(
                corrections=[
                    CorrectionSuggestion(
                        cue_id=1,
                        original_text="Text1",
                        corrected_text="Fixed1",
                        reason="reason1",
                        confidence=0.9
                    ),
                    CorrectionSuggestion(
                        cue_id=1,
                        original_text="Text2",
                        corrected_text="Fixed2",
                        reason="reason2",
                        confidence=0.8
                    ),
                ]
            )

    def test_response_with_multiple_duplicate_cue_ids_raises_validation_error(self):
        """
        Given: 包含多组重复 cue_id 的 corrections
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="存在重复的cue_id"):
            ProofreadingResponse(
                corrections=[
                    CorrectionSuggestion(
                        cue_id=1,
                        original_text="Text1",
                        corrected_text="Fixed1",
                        reason="reason1",
                        confidence=0.9
                    ),
                    CorrectionSuggestion(
                        cue_id=1,
                        original_text="Text2",
                        corrected_text="Fixed2",
                        reason="reason2",
                        confidence=0.8
                    ),
                    CorrectionSuggestion(
                        cue_id=2,
                        original_text="Text3",
                        corrected_text="Fixed3",
                        reason="reason3",
                        confidence=0.7
                    ),
                    CorrectionSuggestion(
                        cue_id=2,
                        original_text="Text4",
                        corrected_text="Fixed4",
                        reason="reason4",
                        confidence=0.6
                    ),
                ]
            )

    def test_response_without_corrections_parameter_raises_validation_error(self):
        """
        Given: 不提供 corrections 参数
        When: 创建模型实例
        Then: 抛出 ValidationError (corrections 是必需参数)
        """
        with pytest.raises(ValidationError) as exc_info:
            ProofreadingResponse()
        assert "field required" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()

    def test_response_json_serialization_deserialization(self):
        """
        Given: 有效的 ProofreadingResponse
        When: 序列化为 JSON 再反序列化
        Then: 数据保持一致
        """
        original = ProofreadingResponse(
            corrections=[
                CorrectionSuggestion(
                    cue_id=1,
                    original_text="Hello warld",
                    corrected_text="Hello world",
                    reason="拼写错误",
                    confidence=0.95
                ),
                CorrectionSuggestion(
                    cue_id=2,
                    original_text="Good mornign",
                    corrected_text="Good morning",
                    reason="拼写错误",
                    confidence=0.88
                ),
            ]
        )

        # 序列化
        json_str = original.model_dump_json()

        # 反序列化
        restored = ProofreadingResponse.model_validate_json(json_str)

        assert len(restored.corrections) == 2
        assert restored.corrections[0].cue_id == 1
        assert restored.corrections[1].cue_id == 2
        assert restored.corrections[0].corrected_text == "Hello world"
        assert restored.corrections[1].reason == "拼写错误"
