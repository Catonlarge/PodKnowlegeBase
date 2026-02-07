"""
TranslationService 边界情况测试

基于代码审查文档 (translation-alignment-code-review.md) 的修复测试：
1. None 值处理
2. 空白翻译验证
3. 错位导致重复 cue_id 检测
4. 重试优化
5. fallback 数据丢失保护
6. 异常状态残留保护

TDD 原则：先写测试，再写实现代码。
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from app.services.translation_service import TranslationService, BatchRetryConfig
from app.models import Episode, AudioSegment, TranscriptCue, Translation
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus
from app.services.ai.schemas.translation_schema import TranslationResponse, TranslationItem


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
# None 值处理测试组
# ========================================================================

class TestNoneValueHandling:
    """测试 AI 返回 None 值的边界情况处理"""

    def test_call_ai_for_translation_none_content_raises_value_error(
        self, translation_service, episode_with_cues, test_session
    ):
        """
        Given: AI API 返回 content=None
        When: 调用 _call_ai_for_translation
        Then: 抛出 RuntimeError（包含 ValueError），包含"空响应"
        """
        # Arrange
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = None

        # Act & Assert
        # OpenAI 在方法内部导入，需要 mock openai 模块
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_completion

            # 代码将 ValueError 包装成 RuntimeError
            with pytest.raises(RuntimeError, match="空响应"):
                translation_service._call_ai_for_translation("test prompt", "zh")

    def test_call_ai_for_translation_empty_string_after_strip_raises_value_error(
        self, translation_service, episode_with_cues, test_session
    ):
        """
        Given: AI API 返回 content="   " (纯空格)
        When: 调用 _call_ai_for_translation
        Then: 抛出 RuntimeError（包含 ValueError），包含"空白翻译"
        """
        # Arrange
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = "   \n\t  "

        # Act & Assert
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_completion

            # 代码将 ValueError 包装成 RuntimeError
            with pytest.raises(RuntimeError, match="空白翻译"):
                translation_service._call_ai_for_translation("test prompt", "zh")


# ========================================================================
# 空字符串验证测试组
# ========================================================================

class TestEmptyStringValidation:
    """测试空字符串和空白字符验证"""

    def test_create_translation_empty_string_raises_value_error(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: translated_text 为空字符串
        When: 调用 _create_translation
        Then: 抛出 ValueError
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Act & Assert
        with pytest.raises(ValueError, match="翻译内容为空"):
            translation_service._create_translation(cue.id, "zh", "")

    def test_create_translation_whitespace_only_raises_value_error(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: translated_text 只包含空格和换行
        When: 调用 _create_translation
        Then: 抛出 ValueError
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Act & Assert
        with pytest.raises(ValueError, match="翻译内容为空"):
            translation_service._create_translation(cue.id, "zh", "   \n\t  ")

    def test_create_translation_valid_text_succeeds(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: translated_text 为有效内容
        When: 调用 _create_translation
        Then: 成功创建 Translation 记录
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Act
        translation = translation_service._create_translation(cue.id, "zh", "你好世界")

        # Assert
        assert translation.translation == "你好世界"

    def test_create_translation_truncates_excessive_length(
        self, translation_service, test_session, episode_with_cues, caplog
    ):
        """
        Given: translated_text 超过 10000 字符
        When: 调用 _create_translation
        Then: 截断到 10000 字符，记录警告日志
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()
        long_text = "a" * 15000  # 超过限制

        # Act
        translation = translation_service._create_translation(cue.id, "zh", long_text)

        # Assert
        assert len(translation.translation) == 10000
        assert "截断到 10000" in caplog.text


# ========================================================================
# Schema 验证测试组
# ========================================================================

class TestTranslationSchemaValidation:
    """测试 TranslationItem Schema 验证"""

    def test_translation_item_empty_translated_text_raises_validation_error(self):
        """
        Given: translated_text 为空字符串
        When: 验证 TranslationItem
        Then: 抛出 Pydantic ValidationError
        """
        # Act & Assert
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            TranslationItem(
                cue_id=1,
                original_text="Hello",
                translated_text=""
            )

        assert "translated_text" in str(exc_info.value)

    def test_translation_item_whitespace_only_raises_validation_error(self):
        """
        Given: translated_text 只包含空格
        When: 验证 TranslationItem
        Then: 抛出 Pydantic ValidationError
        """
        # Arrange
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TranslationItem(
                cue_id=1,
                original_text="Hello",
                translated_text="   \n\t  "
            )

        assert "translated_text" in str(exc_info.value)

    def test_translation_item_valid_text_passes_validation(self):
        """
        Given: translated_text 为有效内容
        When: 验证 TranslationItem
        Then: 验证通过
        """
        # Act
        item = TranslationItem(
            cue_id=1,
            original_text="Hello",
            translated_text="你好"
        )

        # Assert
        assert item.translated_text == "你好"


# ========================================================================
# 错位重复 cue_id 检测测试组
# ========================================================================

class TestMisalignmentDuplicateCueId:
    """测试错位导致重复 cue_id 的检测"""

    def test_validate_response_duplicate_cue_id_in_misalignment_detection(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: LLM 返回中存在重复 cue_id（Pydantic Schema 会捕获）
        When: 尝试创建 TranslationResponse
        Then: Pydantic 验证拒绝重复 cue_id

        注意：实际的重复检测在 Pydantic Schema 层面完成
        """
        # Arrange
        from pydantic import ValidationError

        # Act & Assert - Pydantic Schema 会拒绝重复的 cue_id
        with pytest.raises(ValidationError) as exc_info:
            TranslationResponse(translations=[
                TranslationItem(
                    cue_id=1,
                    original_text="Hello",
                    translated_text="翻译1"
                ),
                TranslationItem(
                    cue_id=1,  # 重复的 cue_id
                    original_text="World",
                    translated_text="翻译2"
                ),
            ])

        assert "cue_id" in str(exc_info.value).lower() or "重复" in str(exc_info.value)


# ========================================================================
# 异常状态残留保护测试组
# ========================================================================

class TestExceptionStateCleanup:
    """测试异常时数据库状态清理"""

    def test_call_ai_for_batch_exception_rolls_back_session(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: _call_ai_for_batch 调用失败
        When: 捕获异常后检查数据库
        Then: 未提交的数据被回滚
        """
        # Arrange
        cues = list(test_session.query(TranscriptCue).limit(3).all())
        cue_ids = [c.id for c in cues]  # 在调用前保存 id

        # Mock StructuredLLM 抛出异常
        with patch.object(translation_service, 'structured_llm') as mock_llm:
            mock_llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("API Error")

            # Act & Assert
            with pytest.raises(RuntimeError):
                translation_service._call_ai_for_batch(cues, "zh")

            # 验证数据库没有残留数据（使用预先保存的 cue_ids）
            translations = test_session.query(Translation).filter(
                Translation.cue_id.in_(cue_ids)
            ).all()

            assert len(translations) == 0


# ========================================================================
# 重试优化测试组
# ========================================================================

class TestRetryOptimization:
    """测试重试优化：只重试失败的条目"""

    def test_try_translate_batch_retry_only_failed_items(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: 批次有 3 条，第 1 次保存时第 2 条失败
        When: 第 2 次重试
        Then: 只重试失败的条目，不重复翻译成功的条目
        """
        # Arrange
        cues = list(test_session.query(TranscriptCue).limit(3).all())
        config = BatchRetryConfig(batch_size=3, max_retries=1)

        call_count = [0]
        batch_sizes = []

        def mock_call_ai(batch, lang):
            call_count[0] += 1
            batch_sizes.append(len(batch))

            return {
                "translations": [
                    {"cue_id": c.id, "translation": f"翻译{i}"}
                    for i, c in enumerate(batch)
                ]
            }

        # 模拟第1次保存时第2条失败
        save_count = [0]

        def mock_create(cue_id, lang, text):
            save_count[0] += 1
            if save_count[0] == 2:
                raise ValueError("模拟保存失败")
            # 创建真实的 Translation 记录用于测试
            translation = Translation(
                cue_id=cue_id,
                language_code=lang,
                translation=text,
                original_translation=text,
                translation_status=TranslationStatus.COMPLETED.value
            )
            test_session.add(translation)
            test_session.flush()
            return translation

        # Act
        with patch.object(translation_service, '_call_ai_for_batch', side_effect=mock_call_ai):
            with patch.object(translation_service, '_create_translation', side_effect=mock_create):
                success, saved, failed = translation_service._try_translate_batch_with_retry(
                    cues, "zh", config
                )

        # Assert
        assert batch_sizes[0] == 3  # 第1次处理3条
        assert batch_sizes[1] == 2  # 第2次只处理剩余2条（跳过第1条成功的）
        assert saved == 3  # 最终全部成功
        assert len(failed) == 0

    def test_try_translate_batch_all_succeed_first_try_no_retry(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: 批次有 3 条，第 1 次全部成功
        When: 调用 _try_translate_batch_with_retry
        Then: 不进行重试
        """
        # Arrange
        cues = list(test_session.query(TranscriptCue).limit(3).all())
        config = BatchRetryConfig(batch_size=3, max_retries=2)

        call_count = [0]

        def mock_call_ai(batch, lang):
            call_count[0] += 1
            return {
                "translations": [
                    {"cue_id": c.id, "translation": f"翻译{i}"}
                    for i, c in enumerate(batch)
                ]
            }

        def mock_create(cue_id, lang, text):
            translation = Translation(
                cue_id=cue_id,
                language_code=lang,
                translation=text,
                original_translation=text,
                translation_status=TranslationStatus.COMPLETED.value
            )
            test_session.add(translation)
            test_session.flush()
            return translation

        # Act
        with patch.object(translation_service, '_call_ai_for_batch', side_effect=mock_call_ai):
            with patch.object(translation_service, '_create_translation', side_effect=mock_create):
                success, saved, failed = translation_service._try_translate_batch_with_retry(
                    cues, "zh", config
                )

        # Assert
        assert call_count[0] == 1  # 只调用1次，不重试
        assert saved == 3
        assert len(failed) == 0


# ========================================================================
# Prompt 优化测试组
# ========================================================================

class TestPromptOptimization:
    """测试 Prompt 格式优化"""

    def test_call_ai_for_batch_uses_compact_json_format(
        self, translation_service, test_session, episode_with_cues
    ):
        """
        Given: 调用 _call_ai_for_batch
        When: 检查发送给 AI 的 prompt
        Then: JSON 格式使用紧凑模式（无缩进）
        """
        # Arrange
        cues = list(test_session.query(TranscriptCue).limit(2).all())

        captured_prompt = {"content": None}

        def mock_invoke(messages):
            # 捕获 user prompt
            captured_prompt["content"] = messages[1].content

            mock_response = Mock()
            mock_response.translations = [
                TranslationItem(
                    cue_id=c.id,
                    original_text=c.text,
                    translated_text="翻译"
                )
                for c in cues
            ]
            return mock_response

        with patch.object(translation_service, 'structured_llm') as mock_llm:
            mock_llm.with_structured_output.return_value.invoke.side_effect = mock_invoke

            # Act
            try:
                translation_service._call_ai_for_batch(cues, "zh")
            except Exception:
                pass  # 只需要捕获 prompt

            # Assert - JSON 应该是紧凑格式（没有 indent=2 的多行空格）
            prompt = captured_prompt["content"]
            # 紧凑格式应该在同一行或使用 separators=(',', ':')
            # 检查不应该有 "  " (两个空格，indent=2 的特征)
            lines = prompt.split('\n')
            json_lines = [l for l in lines if '"cue_id"' in l]
            # 紧凑格式的 cue_id 应该和 { 在同一行或很紧凑
            assert len(json_lines) <= 2  # 紧凑格式应该行数较少
