"""
Unit Tests for SubtitleProofreadingService Validation

This module tests the original_text validation logic in SubtitleProofreadingService.
Tests follow BDD naming convention and avoid conditional logic.
"""
import pytest
from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.models import TranscriptCue, TranscriptCorrection, AudioSegment, Episode


class TestOriginalTextValidation:
    """测试 original_text 验证逻辑"""

    def test_original_text_mismatch_rejected(self, test_session):
        """
        Given: AI 返回的 original_text 与数据库不一致
        When: 调用 apply_corrections
        Then: 跳过该修正，返回 0
        """
        # 创建测试数据
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_001",
            duration=300.0
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=1,
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(segment_id=segment.id, start_time=0.0, end_time=5.0, text="Hello World")
        test_session.add(cue)
        test_session.flush()

        # AI 返回的 original_text 与数据库不一致
        corrections = [{
            "cue_id": cue.id,
            "original_text": "Wrong Text",  # 与 cue.text 不一致
            "corrected_text": "Hello World!",
            "reason": "test",
            "confidence": 0.95
        }]

        service = SubtitleProofreadingService(test_session)
        count = service.apply_corrections(corrections, cues=[cue])

        # 应该跳过该修正
        assert count == 0
        assert cue.corrected_text is None
        assert cue.is_corrected is False

    def test_original_text_match_uses_db_value(self, test_session):
        """
        Given: AI 返回的 original_text 与数据库一致
        When: 调用 apply_corrections
        Then: 使用数据库的 original_text 创建 TranscriptCorrection
        """
        # 创建测试数据
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_001",
            duration=300.0
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=1,
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(segment_id=segment.id, start_time=0.0, end_time=5.0, text="Hello World")
        test_session.add(cue)
        test_session.flush()

        # AI 返回的 original_text 与数据库一致
        corrections = [{
            "cue_id": cue.id,
            "original_text": "Hello World",  # 与 cue.text 一致
            "corrected_text": "Hello World!",
            "reason": "Add punctuation",
            "confidence": 0.95
        }]

        service = SubtitleProofreadingService(test_session)
        count = service.apply_corrections(corrections, cues=[cue])

        # 应该成功应用
        assert count == 1
        assert cue.corrected_text == "Hello World!"
        assert cue.is_corrected is True

        # 验证 TranscriptCorrection 使用数据库的 original_text
        correction_record = test_session.query(TranscriptCorrection).filter_by(cue_id=cue.id).first()
        assert correction_record is not None
        assert correction_record.original_text == "Hello World"  # 使用数据库值
        assert correction_record.corrected_text == "Hello World!"

    def test_apply_corrections_without_cues_param_does_not_validate(self, test_session):
        """
        Given: 不提供 cues 参数
        When: 调用 apply_corrections
        Then: 不验证 original_text，直接应用（向后兼容）
        """
        # 创建测试数据
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_001",
            duration=300.0
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=1,
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(segment_id=segment.id, start_time=0.0, end_time=5.0, text="Hello World")
        test_session.add(cue)
        test_session.flush()

        # 不提供 cues 参数，不验证 original_text
        corrections = [{
            "cue_id": cue.id,
            "original_text": "Different Text",  # 即使不一致也会应用
            "corrected_text": "Hello World!",
            "reason": "test",
            "confidence": 0.95
        }]

        service = SubtitleProofreadingService(test_session)
        count = service.apply_corrections(corrections)  # 不传入 cues

        # 应该成功应用（向后兼容）
        assert count == 1
        assert cue.corrected_text == "Hello World!"

    def test_multiple_corrections_with_mixed_validation_results(self, test_session):
        """
        Given: 多个修正，有的 original_text 匹配，有的不匹配
        When: 调用 apply_corrections
        Then: 只应用匹配的修正
        """
        # 创建测试数据
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_001",
            duration=300.0
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=1,
            segment_id="seg_001",
            start_time=0.0,
            end_time=20.0
        )
        test_session.add(segment)
        test_session.flush()

        cue1 = TranscriptCue(segment_id=segment.id, start_time=0.0, end_time=5.0, text="Hello World")
        cue2 = TranscriptCue(segment_id=segment.id, start_time=5.0, end_time=10.0, text="Good Morning")
        test_session.add_all([cue1, cue2])
        test_session.flush()

        # 混合修正
        corrections = [
            {
                "cue_id": cue1.id,
                "original_text": "Hello World",  # 匹配
                "corrected_text": "Hello World!",
                "reason": "Add punctuation",
                "confidence": 0.95
            },
            {
                "cue_id": cue2.id,
                "original_text": "Wrong Text",  # 不匹配
                "corrected_text": "Good Morning!",
                "reason": "test",
                "confidence": 0.95
            }
        ]

        service = SubtitleProofreadingService(test_session)
        count = service.apply_corrections(corrections, cues=[cue1, cue2])

        # 只应用了匹配的修正
        assert count == 1
        assert cue1.corrected_text == "Hello World!"
        assert cue1.is_corrected is True
        assert cue2.corrected_text is None
        assert cue2.is_corrected is False
