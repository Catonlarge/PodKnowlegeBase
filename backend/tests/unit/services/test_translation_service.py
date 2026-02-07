"""
TranslationService 单元测试

测试翻译服务的核心功能：
1. 批量翻译
2. 断点续传
3. RLHF 双文本存储
4. 多语言支持
5. 错误处理和重试

Updated for StructuredLLM migration with Pydantic validation.
"""
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from sqlalchemy import func

from app.services.translation_service import TranslationService
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


# ========================================================================
# Fixtures
# ========================================================================

@pytest.fixture
def translation_service(test_session):
    """创建 TranslationService 实例（使用 mock API key）"""
    return TranslationService(test_session, provider="moonshot", api_key=None)


@pytest.fixture
def episode_with_cues(test_session):
    """创建带有 TranscriptCue 的 Episode"""
    # 创建 Episode
    episode = Episode(
        title="Test Episode",
        file_hash="test_hash_123",
        duration=600.0,
        workflow_status=WorkflowStatus.SEGMENTED.value
    )
    test_session.add(episode)
    test_session.flush()

    # 创建 AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=600.0,
        status="completed"
    )
    test_session.add(segment)
    test_session.flush()

    # 创建 10 个 TranscriptCue
    cues = []
    for i in range(10):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=i * 60.0,
            end_time=(i + 1) * 60.0,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=f"Hello world {i}"
        )
        cues.append(cue)
        test_session.add(cue)
    test_session.flush()

    return episode


# ========================================================================
# Init 测试组
# ========================================================================

class TestInit:
    """测试 TranslationService 初始化"""

    def test_init(self, test_session):
        """
        Given: 数据库会话
        When: 创建 TranslationService (无 API key)
        Then: 对象初始化成功，structured_llm 为 None
        """
        # Act
        service = TranslationService(test_session, provider="moonshot", api_key=None)

        # Assert
        assert service.db == test_session
        assert service.structured_llm is None
        assert service.BATCH_SIZE == 50
        assert service.provider == "moonshot"


# ========================================================================
# GetPendingCues 测试组
# ========================================================================

class TestGetPendingCues:
    """测试 _get_pending_cues 方法"""

    def test_get_pending_cues_all_pending(self, translation_service, episode_with_cues):
        """
        Given: Episode 有 10 个 TranscriptCue，无翻译记录
        When: 调用 _get_pending_cues
        Then: 返回全部 10 个 Cue
        """
        # Act
        pending_cues = translation_service._get_pending_cues(episode_with_cues.id, "zh")

        # Assert
        assert len(pending_cues) == 10

    def test_get_pending_cues_partial_completed(self, translation_service, episode_with_cues, test_session):
        """
        Given: Episode 有 10 个 TranscriptCue，其中 5 个已完成翻译
        When: 调用 _get_pending_cues
        Then: 只返回未完成的 5 个 Cue
        """
        # Arrange - 获取前 5 个 Cue 并创建已完成的翻译
        cues = test_session.query(TranscriptCue).filter(
            TranscriptCue.segment_id is not None
        ).limit(5).all()

        for cue in cues:
            translation = Translation(
                cue_id=cue.id,
                language_code="zh",
                original_translation=f"翻译 {cue.text}",
                translation=f"翻译 {cue.text}",
                translation_status=TranslationStatus.COMPLETED.value
            )
            test_session.add(translation)
        test_session.flush()

        # Act
        pending_cues = translation_service._get_pending_cues(episode_with_cues.id, "zh")

        # Assert
        assert len(pending_cues) == 5

    def test_get_pending_cues_all_completed(self, translation_service, episode_with_cues, test_session):
        """
        Given: Episode 有 10 个 TranscriptCue，全部已完成翻译
        When: 调用 _get_pending_cues
        Then: 返回空列表
        """
        # Arrange - 为所有 Cue 创建已完成的翻译
        cues = test_session.query(TranscriptCue).filter(
            TranscriptCue.segment_id is not None
        ).all()

        for cue in cues:
            translation = Translation(
                cue_id=cue.id,
                language_code="zh",
                original_translation=f"翻译 {cue.text}",
                translation=f"翻译 {cue.text}",
                translation_status=TranslationStatus.COMPLETED.value
            )
            test_session.add(translation)
        test_session.flush()

        # Act
        pending_cues = translation_service._get_pending_cues(episode_with_cues.id, "zh")

        # Assert
        assert len(pending_cues) == 0

    def test_get_pending_cues_includes_failed(self, translation_service, episode_with_cues, test_session):
        """
        Given: Episode 有部分翻译状态为 failed
        When: 调用 _get_pending_cues
        Then: 返回 pending 和 failed 的 Cue
        """
        # Arrange - 创建 3 个 completed，2 个 failed，其余 pending
        cues = test_session.query(TranscriptCue).filter(
            TranscriptCue.segment_id is not None
        ).limit(5).all()

        for i, cue in enumerate(cues):
            status = (
                TranslationStatus.COMPLETED.value if i < 3
                else TranslationStatus.FAILED.value
            )
            translation = Translation(
                cue_id=cue.id,
                language_code="zh",
                original_translation=f"翻译 {cue.text}",
                translation=f"翻译 {cue.text}",
                translation_status=status,
                translation_error="API error" if status == TranslationStatus.FAILED.value else None
            )
            test_session.add(translation)
        test_session.flush()

        # Act
        pending_cues = translation_service._get_pending_cues(episode_with_cues.id, "zh")

        # Assert - 应该返回 failed 和 pending 的（10 - 3 = 7）
        assert len(pending_cues) == 7


# ========================================================================
# CreateTranslation 测试组
# ========================================================================

class TestCreateTranslation:
    """测试 _create_translation 方法"""

    def test_create_translation_sets_both_fields(self, translation_service, test_session, episode_with_cues):
        """
        Given: cue_id 和翻译文本
        When: 调用 _create_translation
        Then: original_translation 和 translation 都被设置
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()
        translated_text = "你好世界"

        # Act
        translation = translation_service._create_translation(cue.id, "zh", translated_text)
        test_session.flush()
        test_session.refresh(translation)

        # Assert
        assert translation.original_translation == translated_text
        assert translation.translation == translated_text
        assert translation.is_edited is False

    def test_create_translation_status_completed(self, translation_service, test_session, episode_with_cues):
        """
        Given: cue_id 和翻译文本
        When: 调用 _create_translation
        Then: translation_status 为 completed
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Act
        translation = translation_service._create_translation(cue.id, "zh", "你好世界")
        test_session.flush()
        test_session.refresh(translation)

        # Assert
        assert translation.translation_status == TranslationStatus.COMPLETED.value
        assert translation.translation_completed_at is not None


# ========================================================================
# TranslateCue 测试组
# ========================================================================

class TestTranslateCue:
    """测试 translate_cue 方法"""

    def test_translate_cue_success(self, translation_service, test_session, episode_with_cues):
        """
        Given: TranscriptCue 和 Mock AI 服务
        When: 调用 translate_cue
        Then: 返回 Translation 对象，状态为 completed
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Mock _call_ai_for_translation 方法
        with patch.object(translation_service, '_call_ai_for_translation', return_value="你好世界"):
            # Act
            translation = translation_service.translate_cue(cue, "zh")
            test_session.refresh(translation)

            # Assert
            assert translation is not None
            assert translation.cue_id == cue.id
            assert translation.language_code == "zh"
            assert translation.translation == "你好世界"
            assert translation.translation_status == TranslationStatus.COMPLETED.value

    def test_translate_cue_dual_text_storage(self, translation_service, test_session, episode_with_cues):
        """
        Given: 翻译完成
        When: 查询 Translation
        Then: original_translation 和 translation 相同，is_edited = False
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Mock _call_ai_for_translation 方法
        with patch.object(translation_service, '_call_ai_for_translation', return_value="你好世界"):
            # Act
            translation = translation_service.translate_cue(cue, "zh")
            test_session.refresh(translation)

            # Assert
            assert translation.original_translation == "你好世界"
            assert translation.translation == "你好世界"
            assert translation.is_edited is False

    def test_translate_cue_api_error(self, translation_service, test_session, episode_with_cues):
        """
        Given: Mock AI 服务抛出异常
        When: 调用 translate_cue
        Then: Translation 状态为 failed，记录错误信息
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Mock _call_ai_for_translation 方法抛出异常
        with patch.object(translation_service, '_call_ai_for_translation', side_effect=RuntimeError("API Error")):
            # Act & Assert
            with pytest.raises(RuntimeError, match="翻译失败"):
                translation_service.translate_cue(cue, "zh")

            # 验证创建了 failed 状态的 Translation
            translation = test_session.query(Translation).filter(
                Translation.cue_id == cue.id
            ).first()

            assert translation is not None
            assert translation.translation_status == TranslationStatus.FAILED.value
            assert "API Error" in translation.translation_error

    def test_translate_cue_updates_timestamps(self, translation_service, test_session, episode_with_cues):
        """
        Given: TranscriptCue
        When: 调用 translate_cue
        Then: translation_started_at 和 translation_completed_at 被设置
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Mock _call_ai_for_translation 方法
        with patch.object(translation_service, '_call_ai_for_translation', return_value="你好"):
            # Act
            before_time = datetime.now()
            translation = translation_service.translate_cue(cue, "zh")
            after_time = datetime.now()
            test_session.refresh(translation)

            # Assert
            assert translation.translation_started_at is not None
            assert translation.translation_completed_at is not None
            assert before_time <= translation.translation_started_at <= after_time


# ========================================================================
# BatchTranslate 测试组
# ========================================================================

class TestBatchTranslate:
    """测试 batch_translate 方法"""

    def test_batch_translate_success(self, translation_service, episode_with_cues):
        """
        Given: Episode 和 TranscriptCue 列表
        When: 调用 batch_translate
        Then: 返回成功翻译数量，创建 Translation 记录
        """
        # Arrange
        with patch.object(translation_service, '_call_ai_for_translation', return_value="翻译结果"):
            # Act
            count = translation_service.batch_translate(episode_with_cues.id, "zh")

            # Assert
            assert count == 10

    def test_batch_translate_resume_from_checkpoint(self, translation_service, episode_with_cues, test_session):
        """
        Given: 部分 Cue 已翻译
        When: 再次调用 batch_translate
        Then: 只翻译未完成的 Cue，跳过已完成的
        """
        # Arrange - 为前 5 个 Cue 创建已完成翻译
        cues = test_session.query(TranscriptCue).order_by(TranscriptCue.id).limit(5).all()

        for cue in cues:
            translation = Translation(
                cue_id=cue.id,
                language_code="zh",
                original_translation="已翻译",
                translation="已翻译",
                translation_status=TranslationStatus.COMPLETED.value
            )
            test_session.add(translation)
        test_session.flush()

        with patch.object(translation_service, '_call_ai_for_translation', return_value="新翻译"):
            # Act
            count = translation_service.batch_translate(episode_with_cues.id, "zh")

            # Assert - 只翻译了 5 个（第 6-10 个）
            assert count == 5

    def test_batch_translate_batch_processing(self, translation_service, episode_with_cues, test_session):
        """
        Given: 120 个 TranscriptCue
        When: 调用 batch_translate
        Then: 分批处理（BATCH_SIZE=50）
        """
        # Arrange - 创建更多 Cue
        segment = test_session.query(AudioSegment).first()

        # 添加更多 Cue（已有 10 个，再添加 110 个）
        for i in range(10, 120):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 5.0,
                end_time=(i + 1) * 5.0,
                speaker="SPEAKER_00",
                text=f"Text {i}"
            )
            test_session.add(cue)
        test_session.flush()

        # 修改 TranslationService 的 BATCH_SIZE 为测试友好值
        original_batch_size = TranslationService.BATCH_SIZE
        TranslationService.BATCH_SIZE = 30

        try:
            with patch.object(translation_service, '_call_ai_for_translation', return_value="翻译"):
                # Act
                count = translation_service.batch_translate(episode_with_cues.id, "zh")

                # Assert - 应该有 120 个 Cue，分 4 批（30+30+30+30）
                assert count == 120
        finally:
            TranslationService.BATCH_SIZE = original_batch_size

    def test_batch_translate_retry_failed(self, translation_service, episode_with_cues, test_session):
        """
        Given: 部分翻译状态为 failed
        When: enable_retry=True 调用 batch_translate
        Then: 重新翻译失败的 Cue
        """
        # Arrange - 创建 3 个 completed，2 个 failed
        cues = test_session.query(TranscriptCue).limit(5).all()

        for i, cue in enumerate(cues):
            status = (
                TranslationStatus.COMPLETED.value if i < 3
                else TranslationStatus.FAILED.value
            )
            translation = Translation(
                cue_id=cue.id,
                language_code="zh",
                original_translation="旧翻译",
                translation="旧翻译",
                translation_status=status,
                translation_error="API error" if status == TranslationStatus.FAILED.value else None
            )
            test_session.add(translation)
        test_session.flush()

        # Act - 默认 enable_retry=True
        with patch.object(translation_service, '_call_ai_for_translation', return_value="新翻译"):
            count = translation_service.batch_translate(episode_with_cues.id, "zh")

            # Assert - 应该翻译 7 个（10 - 3 completed）
            assert count == 7
            # 验证 failed 的被重新翻译
            failed_translations = test_session.query(Translation).filter(
                Translation.translation_status == TranslationStatus.COMPLETED.value
            ).all()
            assert len(failed_translations) == 10  # 最终全部完成

    def test_batch_translate_multiple_languages(self, translation_service, episode_with_cues, test_session):
        """
        Given: language_code='ja'
        When: 调用 batch_translate
        Then: 创建日语 Translation
        """
        # Arrange
        with patch.object(translation_service, '_call_ai_for_translation', return_value="こんにちは"):
            # Act
            count = translation_service.batch_translate(episode_with_cues.id, "ja")

            # Assert
            assert count == 10

            # 验证语言代码
            translations = test_session.query(Translation).filter(
                Translation.language_code == "ja"
            ).all()
            assert len(translations) == 10
            assert all(t.language_code == "ja" for t in translations)

    def test_batch_translate_no_pending_cues(self, translation_service, episode_with_cues, test_session):
        """
        Given: 所有 Cue 已翻译完成
        When: 调用 batch_translate
        Then: 返回 0，不调用 AI
        """
        # Arrange - 为所有 Cue 创建已完成翻译
        cues = test_session.query(TranscriptCue).all()

        for cue in cues:
            translation = Translation(
                cue_id=cue.id,
                language_code="zh",
                original_translation="已翻译",
                translation="已翻译",
                translation_status=TranslationStatus.COMPLETED.value
            )
            test_session.add(translation)
        test_session.flush()

        # Act
        count = translation_service.batch_translate(episode_with_cues.id, "zh")

        # Assert
        assert count == 0


# ========================================================================
# BatchRetry 测试组 - 批次重试机制
# ========================================================================

class TestBatchRetry:
    """测试批次重试机制"""

    def test_success_on_first_try(self, translation_service, episode_with_cues, test_session):
        """
        Given: 10条Cue，LLM 返回正确 JSON
        When: 调用 batch_translate
        Then: 不重试，直接成功
        """
        # Arrange
        mock_response = {
            "translations": [
                {"cue_id": c.id, "translation": f"翻译 {i}"}
                for i, c in enumerate(test_session.query(TranscriptCue).all())
            ]
        }

        # Act
        with patch.object(translation_service, '_call_ai_for_batch', return_value=mock_response):
            count = translation_service.batch_translate(episode_with_cues.id, "zh")

        # Assert
        assert count == 10

    def test_success_on_second_try(self, translation_service, episode_with_cues, test_session):
        """
        Given: 10条Cue，第1次返回非JSON，第2次返回正确JSON
        When: 调用 batch_translate
        Then: 重试1次后成功
        """
        # Arrange
        cues = test_session.query(TranscriptCue).all()
        mock_response = {
            "translations": [
                {"cue_id": c.id, "translation": f"翻译 {i}"}
                for i, c in enumerate(cues)
            ]
        }

        # Act - 第1次失败，第2次成功
        with patch.object(translation_service, '_call_ai_for_batch', side_effect=["invalid json", mock_response]):
            count = translation_service.batch_translate(episode_with_cues.id, "zh")

        # Assert
        assert count == 10

    def test_success_on_third_try(self, translation_service, episode_with_cues, test_session):
        """
        Given: 10条Cue，前2次返回非JSON，第3次返回正确JSON
        When: 调用 batch_translate (max_retries=2)
        Then: 重试2次后成功，不降级
        """
        # Arrange
        cues = test_session.query(TranscriptCue).all()
        mock_response = {
            "translations": [
                {"cue_id": c.id, "translation": f"翻译 {i}"}
                for i, c in enumerate(cues)
            ]
        }

        # Act - 前2次失败，第3次成功
        with patch.object(translation_service, '_call_ai_for_batch', side_effect=["invalid", "json", mock_response]):
            count = translation_service.batch_translate(episode_with_cues.id, "zh")

        # Assert
        assert count == 10

    def test_all_retries_trigger_degradation(self, translation_service, episode_with_cues, test_session):
        """
        Given: 10条Cue，3次都返回非JSON (max_retries=2)
        When: 调用 batch_translate
        Then: 降级到小批次或逐条翻译
        """
        # Arrange - Mock 批量翻译失败，逐条翻译成功
        with patch.object(translation_service, '_call_ai_for_batch', side_effect=RuntimeError("JSON parse error")):
            with patch.object(translation_service, '_call_ai_for_translation', return_value="翻译"):
                # Act
                count = translation_service.batch_translate(episode_with_cues.id, "zh")

        # Assert - 应该回退到逐条翻译成功
        assert count == 10


# ========================================================================
# JSONValidation 测试组 - JSON 验证逻辑
# ========================================================================

class TestJSONValidation:
    """测试 JSON 验证逻辑"""

    def test_valid_json_passes(self, translation_service, episode_with_cues, test_session):
        """
        Given: LLM 返回正确格式的 JSON
        When: 调用 _validate_and_parse_translations
        Then: 返回翻译列表，不抛出异常
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(3).all()
        valid_response = {
            "translations": [
                {"cue_id": cues[0].id, "translation": "翻译1"},
                {"cue_id": cues[1].id, "translation": "翻译2"},
                {"cue_id": cues[2].id, "translation": "翻译3"},
            ]
        }

        # Act & Assert - 不应抛出异常
        result = translation_service._validate_and_parse_translations(
            json.dumps(valid_response), cues
        )

        assert len(result) == 3
        assert result[0]["cue_id"] == cues[0].id
        assert result[0]["translation"] == "翻译1"

    def test_json_parse_error_raises_value_error(self, translation_service, episode_with_cues, test_session):
        """
        Given: LLM 返回非 JSON 文本
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"JSON 解析失败"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(3).all()

        # Act & Assert
        with pytest.raises(ValueError, match="JSON 解析失败"):
            translation_service._validate_and_parse_translations("this is not json", cues)

    def test_missing_translations_field_raises(self, translation_service, episode_with_cues, test_session):
        """
        Given: JSON 缺少 translations 字段
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"缺少 'translations' 字段"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(3).all()
        invalid_response = {"data": "something"}

        # Act & Assert
        with pytest.raises(ValueError, match="缺少 'translations' 字段"):
            translation_service._validate_and_parse_translations(
                json.dumps(invalid_response), cues
            )

    def test_translations_not_list_raises(self, translation_service, episode_with_cues, test_session):
        """
        Given: translations 不是列表类型
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"不是列表类型"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(3).all()
        invalid_response = {"translations": "not a list"}

        # Act & Assert
        with pytest.raises(ValueError, match="'translations' 不是列表类型"):
            translation_service._validate_and_parse_translations(
                json.dumps(invalid_response), cues
            )

    def test_wrong_cue_id_type_raises(self, translation_service, episode_with_cues, test_session):
        """
        Given: cue_id 是字符串而非整数
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"类型错误"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(3).all()
        invalid_response = {
            "translations": [
                {"cue_id": "not_a_number", "translation": "翻译"}
            ]
        }

        # Act & Assert
        with pytest.raises(ValueError, match="'cue_id' 类型错误"):
            translation_service._validate_and_parse_translations(
                json.dumps(invalid_response), cues
            )

    def test_incomplete_translations_raises(self, translation_service, episode_with_cues, test_session):
        """
        Given: 只返回部分翻译（3条输入只返回2条）
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"缺少.*条翻译"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(3).all()
        incomplete_response = {
            "translations": [
                {"cue_id": cues[0].id, "translation": "翻译1"},
                {"cue_id": cues[1].id, "translation": "翻译2"},
                # 缺少第3条
            ]
        }

        # Act & Assert
        with pytest.raises(ValueError, match="缺少 1 条翻译"):
            translation_service._validate_and_parse_translations(
                json.dumps(incomplete_response), cues
            )

    def test_duplicate_cue_id_raises(self, translation_service, episode_with_cues, test_session):
        """
        Given: 返回重复的 cue_id
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"重复的 cue_id"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(2).all()
        duplicate_response = {
            "translations": [
                {"cue_id": cues[0].id, "translation": "翻译1"},
                {"cue_id": cues[0].id, "translation": "翻译2"},  # 重复
            ]
        }

        # Act & Assert
        with pytest.raises(ValueError, match="重复的 cue_id"):
            translation_service._validate_and_parse_translations(
                json.dumps(duplicate_response), cues
            )

    def test_invalid_cue_id_raises(self, translation_service, episode_with_cues, test_session):
        """
        Given: cue_id 不在输入列表中
        When: 调用 _validate_and_parse_translations
        Then: 抛出 ValueError，包含"无效的 cue_id"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(2).all()
        invalid_response = {
            "translations": [
                {"cue_id": cues[0].id, "translation": "翻译1"},
                {"cue_id": 99999, "translation": "翻译2"},  # 无效的 cue_id
            ]
        }

        # Act & Assert
        with pytest.raises(ValueError, match="无效的 cue_id"):
            translation_service._validate_and_parse_translations(
                json.dumps(invalid_response), cues
            )

    def test_markdown_wrapped_json_passes(self, translation_service, episode_with_cues, test_session):
        """
        Given: JSON 被 ```json ``` 包裹
        When: 调用 _validate_and_parse_translations
        Then: 成功解析，返回翻译列表
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(2).all()
        markdown_json = '''```json
{
    "translations": [
        {"cue_id": ''' + str(cues[0].id) + ''', "translation": "翻译1"},
        {"cue_id": ''' + str(cues[1].id) + ''', "translation": "翻译2"}
    ]
}
```'''

        # Act & Assert
        result = translation_service._validate_and_parse_translations(markdown_json, cues)

        assert len(result) == 2
        assert result[0]["translation"] == "翻译1"


# ========================================================================
# ErrorClassification 测试组 - 错误分类
# ========================================================================

class TestErrorClassification:
    """测试错误分类"""

    def test_format_error_classification(self, translation_service, episode_with_cues, test_session):
        """
        Given: JSON 解析错误、缺少字段、类型错误
        When: 调用 _classify_validation_error
        Then: 返回 "format"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(2).all()
        error = ValueError("JSON 解析失败")

        # Act
        error_type = translation_service._classify_validation_error(error, cues)

        # Assert
        assert error_type == "format"

    def test_incomplete_error_classification(self, translation_service, episode_with_cues, test_session):
        """
        Given: 缺少部分翻译
        When: 调用 _classify_validation_error
        Then: 返回 "incomplete"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(2).all()
        error = ValueError("缺少 1 条翻译")

        # Act
        error_type = translation_service._classify_validation_error(error, cues)

        # Assert
        assert error_type == "incomplete"

    def test_error_classification(self, translation_service, episode_with_cues, test_session):
        """
        Given: 无效 cue_id、重复 cue_id
        When: 调用 _classify_validation_error
        Then: 返回 "error"
        """
        # Arrange
        cues = test_session.query(TranscriptCue).limit(2).all()
        error = ValueError("无效的 cue_id")

        # Act
        error_type = translation_service._classify_validation_error(error, cues)

        # Assert
        assert error_type == "error"


# ========================================================================
# UpdateEpisodeStatus 测试组
# ========================================================================

class TestUpdateEpisodeStatus:
    """测试 _update_episode_status 方法"""

    def test_update_episode_status_to_translated(self, translation_service, episode_with_cues, test_session):
        """
        Given: Episode.workflow_status = SEGMENTED
        When: 调用 _update_episode_status
        Then: workflow_status 更新为 TRANSLATED
        """
        # Arrange
        assert episode_with_cues.workflow_status == WorkflowStatus.SEGMENTED.value

        # Act
        translation_service._update_episode_status(episode_with_cues.id)
        test_session.refresh(episode_with_cues)

        # Assert
        assert episode_with_cues.workflow_status == WorkflowStatus.TRANSLATED.value
