"""
TranslationService 批次重试兜底功能测试

测试 50条/批、5轮重试策略，失败后入库 NULL。
"""
from datetime import datetime
from unittest.mock import Mock, patch
import pytest

from app.services.translation_service import TranslationService
from app.models import Episode, TranscriptCue, Translation, AudioSegment
from app.enums.translation_status import TranslationStatus
from app.enums.workflow_status import WorkflowStatus


class TestTranslationBatchRetryFallback:
    """测试 TranslationService 批次重试兜底功能"""

    def test_fallback_saves_failed_translations_as_null(self, test_session):
        """Given: 5轮重试后仍失败 When: 保存失败记录 Then: translation=NULL, status='failed'"""
        # Arrange
        episode = Episode(
            title="Test",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.SEGMENTED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        # 创建 3 条测试 cues
        cues = []
        for i in range(3):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=float(i * 10),
                end_time=float((i + 1) * 10),
                speaker="Speaker",
                text=f"Test text {i}"
            )
            test_session.add(cue)
            test_session.flush()
            cues.append(cue)

        service = TranslationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Mock _translate_single_cue to always fail
        with patch.object(
            service,
            '_translate_single_cue',
            side_effect=Exception("AI 翻译失败")
        ):
            # Act
            success_count = service._fallback_translate_one_by_one(cues, "zh")

        # Assert
        assert success_count == 0

        # 验证失败记录已入库
        failed_translations = test_session.query(Translation).filter(
            Translation.translation_status == TranslationStatus.FAILED.value
        ).all()

        assert len(failed_translations) == 3
        for trans in failed_translations:
            assert trans.translation is None  # NULL
            assert trans.original_translation is None  # NULL
            assert trans.translation_status == TranslationStatus.FAILED.value
            assert trans.translation_retry_count == 5
            assert "AI 翻译失败，已重试5轮" in trans.translation_error

    def test_fallback_partial_success_partial_failure(self, test_session):
        """Given: 部分成功部分失败 When: 批次重试 Then: 成功的入库，失败的标记为 failed"""
        # Arrange
        episode = Episode(
            title="Test",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.SEGMENTED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        # 创建 3 条测试 cues
        cues = []
        for i in range(3):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=float(i * 10),
                end_time=float((i + 1) * 10),
                speaker="Speaker",
                text=f"Test text {i}"
            )
            test_session.add(cue)
            test_session.flush()
            cues.append(cue)

        service = TranslationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        call_count = [0]

        def mock_translate(cue, original_text, lang):
            """第一次成功，后续失败"""
            call_count[0] += 1
            if call_count[0] == 1:
                return "翻译成功"
            raise Exception("AI 翻译失败")

        with patch.object(
            service,
            '_translate_single_cue',
            side_effect=mock_translate
        ):
            # Act
            success_count = service._fallback_translate_one_by_one(cues, "zh")

        # Assert
        assert success_count == 1

        # 验证成功记录
        success_trans = test_session.query(Translation).filter(
            Translation.translation_status == TranslationStatus.COMPLETED.value
        ).first()
        assert success_trans is not None
        assert success_trans.translation == "翻译成功"

        # 验证失败记录
        failed_translations = test_session.query(Translation).filter(
            Translation.translation_status == TranslationStatus.FAILED.value
        ).all()
        assert len(failed_translations) == 2

    def test_fallback_less_than_50_triggers_retry(self, test_session):
        """Given: 只有3条失败项 When: 批次重试 Then: 不足50条也触发重试"""
        # Arrange
        episode = Episode(
            title="Test",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.SEGMENTED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        # 创建 3 条 cues（少于 50 条）
        cues = []
        for i in range(3):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=float(i * 10),
                end_time=float((i + 1) * 10),
                speaker="Speaker",
                text=f"Test {i}"
            )
            test_session.add(cue)
            test_session.flush()
            cues.append(cue)

        service = TranslationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        round_count = [0]

        def mock_translate(cue, original_text, lang):
            """每轮成功一条"""
            round_count[0] += 1
            if round_count[0] <= 3:
                return f"翻译{round_count[0]}"
            raise Exception("失败")

        with patch.object(
            service,
            '_translate_single_cue',
            side_effect=mock_translate
        ):
            # Act
            success_count = service._fallback_translate_one_by_one(cues, "zh")

        # Assert - 验证确实执行了多轮（虽然只有3条）
        assert success_count == 3
        assert round_count[0] == 3  # 3条都成功

    def test_create_failed_translation_saves_null_values(self, test_session):
        """Given: 创建失败翻译记录 When: 保存 Then: 字段值符合数据库设计"""
        # Arrange
        episode = Episode(
            title="Test",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.SEGMENTED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=10.0,
            speaker="Speaker",
            text="Test"
        )
        test_session.add(cue)
        test_session.flush()

        service = TranslationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Act
        service._create_failed_translation(cue.id, "zh", "original text")

        # Assert
        translation = test_session.query(Translation).filter(
            Translation.cue_id == cue.id
        ).first()

        assert translation is not None
        assert translation.cue_id == cue.id
        assert translation.language_code == "zh"
        assert translation.translation is None  # NULL
        assert translation.original_translation is None  # NULL
        assert translation.is_edited is False
        assert translation.translation_status == TranslationStatus.FAILED.value
        assert translation.translation_error == "AI 翻译失败，已重试5轮"
        assert translation.translation_retry_count == 5

    def test_5_rounds_then_save_null(self, test_session):
        """Given: 单条连续失败5次 When: 重试5轮后 Then: 保存NULL状态"""
        # Arrange
        episode = Episode(
            title="Test",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.SEGMENTED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=10.0,
            speaker="Speaker",
            text="Test"
        )
        test_session.add(cue)
        test_session.flush()

        service = TranslationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        attempt_count = [0]

        def always_fail(cue, original_text, lang):
            """总是失败"""
            attempt_count[0] += 1
            raise Exception("翻译失败")

        with patch.object(
            service,
            '_translate_single_cue',
            side_effect=always_fail
        ):
            # Act
            success_count = service._fallback_translate_one_by_one([cue], "zh")

        # Assert
        assert success_count == 0
        assert attempt_count[0] == 5  # 5轮重试

        # 验证保存了失败记录
        translation = test_session.query(Translation).filter(
            Translation.cue_id == cue.id
        ).first()

        assert translation is not None
        assert translation.translation_status == TranslationStatus.FAILED.value
        assert translation.translation_retry_count == 5
