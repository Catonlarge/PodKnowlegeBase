"""
Unit tests for SegmentationService.

These tests use mocking to avoid actual AI API calls.
"""
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.services.segmentation_service import SegmentationService
from app.models import Episode, Chapter, TranscriptCue, AudioSegment
from app.enums.workflow_status import WorkflowStatus


class TestSegmentationServiceInit:
    """Test SegmentationService initialization."""

    def test_init_stores_session_and_ai_service(self, test_session):
        """Given: A test session and mock AI service
        When: Initializing SegmentationService
        Then: Stores db session and ai_service
        """
        # Arrange
        mock_ai = Mock()

        # Act
        service = SegmentationService(test_session, mock_ai)

        # Assert
        assert service.db == test_session
        assert service.ai_service == mock_ai


class TestSegmentationServiceBuildTranscriptText:
    """Test transcript text building."""

    def test_build_transcript_text_formats_cues_with_timestamps(self, test_session):
        """Given: A list of TranscriptCue objects
        When: Calling _build_transcript_text
        Then: Returns formatted text with timestamps
        """
        # Arrange
        cues = [
            TranscriptCue(
                segment_id=1,
                start_time=0.0,
                end_time=3.0,
                speaker="SPEAKER_00",
                text="Hello world"
            ),
            TranscriptCue(
                segment_id=1,
                start_time=5.0,
                end_time=8.0,
                speaker="SPEAKER_00",
                text="How are you?"
            ),
        ]
        service = SegmentationService(test_session, Mock())

        # Act
        result = service._build_transcript_text(cues)

        # Assert
        assert "[00:00]" in result
        assert "[00:05]" in result
        assert "Hello world" in result
        assert "How are you?" in result


class TestSegmentationServiceParseAIResponse:
    """Test AI response parsing."""

    def test_parse_ai_response_valid_json(self, test_session):
        """Given: AI returns valid JSON
        When: Calling _parse_ai_response
        Then: Returns list of chapter dictionaries
        """
        # Arrange
        service = SegmentationService(test_session, Mock())
        response_text = '''{
  "chapters": [
    {
      "title": "开场介绍",
      "summary": "主持人介绍了今天的主题",
      "start_time": 0.0,
      "end_time": 120.0
    }
  ]
}'''

        # Act
        result = service._parse_ai_response(response_text)

        # Assert
        assert len(result) == 1
        assert result[0]["title"] == "开场介绍"
        assert result[0]["summary"] == "主持人介绍了今天的主题"
        assert result[0]["start_time"] == 0.0
        assert result[0]["end_time"] == 120.0

    def test_parse_ai_response_strips_json_markers(self, test_session):
        """Given: AI returns JSON with ```json markers
        When: Calling _parse_ai_response
        Then: Strips markers and parses correctly
        """
        # Arrange
        service = SegmentationService(test_session, Mock())
        response_text = '''```json
{
  "chapters": [
    {"title": "第一章", "summary": "摘要", "start_time": 0.0, "end_time": 100.0}
  ]
}
```'''

        # Act
        result = service._parse_ai_response(response_text)

        # Assert
        assert len(result) == 1
        assert result[0]["title"] == "第一章"

    def test_parse_ai_response_raises_on_invalid_json(self, test_session):
        """Given: AI returns invalid JSON
        When: Calling _parse_ai_response
        Then: Raises ValueError
        """
        # Arrange
        service = SegmentationService(test_session, Mock())
        response_text = "This is not valid JSON"

        # Act & Assert
        with pytest.raises(ValueError, match="JSON 解析失败"):
            service._parse_ai_response(response_text)

    def test_parse_ai_response_raises_on_missing_chapters_key(self, test_session):
        """Given: AI returns JSON without 'chapters' key
        When: Calling _parse_ai_response
        Then: Raises ValueError
        """
        # Arrange
        service = SegmentationService(test_session, Mock())
        response_text = '{"data": []}'

        # Act & Assert
        with pytest.raises(ValueError, match="缺少 'chapters' 字段"):
            service._parse_ai_response(response_text)


class TestSegmentationServiceCreateChapters:
    """Test Chapter creation."""

    def test_create_chapters_saves_to_database(self, test_session):
        """Given: Episode and chapter data
        When: Calling _create_chapters
        Then: Creates Chapter records in database
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        chapters_data = [
            {
                "title": "开场介绍",
                "summary": "主持人介绍主题",
                "start_time": 0.0,
                "end_time": 200.0
            },
            {
                "title": "核心内容",
                "summary": "深入讨论",
                "start_time": 200.0,
                "end_time": 600.0
            },
        ]

        service = SegmentationService(test_session, Mock())

        # Act
        chapters = service._create_chapters(episode.id, chapters_data)

        # Assert
        assert len(chapters) == 2
        assert chapters[0].title == "开场介绍"
        assert chapters[0].chapter_index == 0
        assert chapters[0].episode_id == episode.id

        assert chapters[1].title == "核心内容"
        assert chapters[1].chapter_index == 1

        # Verify database persistence
        db_chapters = test_session.query(Chapter).filter(
            Chapter.episode_id == episode.id
        ).all()
        assert len(db_chapters) == 2


class TestSegmentationServiceAssociateCuesToChapters:
    """Test Cue to Chapter association."""

    def test_associate_cues_to_chapters_by_time(self, test_session):
        """Given: Chapters and TranscriptCues
        When: Calling _associate_cues_to_chapters
        Then: Associates cues to correct chapters based on time
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        # Create chapters
        chapter1 = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            summary="摘要1",
            start_time=0.0,
            end_time=300.0
        )
        chapter2 = Chapter(
            episode_id=episode.id,
            chapter_index=1,
            title="第二章",
            summary="摘要2",
            start_time=300.0,
            end_time=600.0
        )
        test_session.add_all([chapter1, chapter2])
        test_session.flush()

        # Create AudioSegment for cues
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

        # Create cues across chapters
        cue1 = TranscriptCue(
            segment_id=segment.id,
            start_time=60.0,
            end_time=65.0,
            speaker="SPEAKER_00",
            text="Text in chapter 1"
        )
        cue2 = TranscriptCue(
            segment_id=segment.id,
            start_time=400.0,
            end_time=405.0,
            speaker="SPEAKER_00",
            text="Text in chapter 2"
        )
        test_session.add_all([cue1, cue2])
        test_session.flush()

        chapters = [chapter1, chapter2]
        service = SegmentationService(test_session, Mock())

        # Act
        service._associate_cues_to_chapters(episode.id, chapters)

        # Assert
        test_session.refresh(cue1)
        test_session.refresh(cue2)

        assert cue1.chapter_id == chapter1.id
        assert cue2.chapter_id == chapter2.id


class TestSegmentationServiceUpdateEpisodeStatus:
    """Test Episode workflow status update."""

    def test_update_episode_status_to_segmented(self, test_session):
        """Given: Episode with TRANSCRIBED status
        When: Calling _update_episode_status
        Then: Updates status to SEGMENTED
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        service = SegmentationService(test_session, Mock())

        # Act
        service._update_episode_status(episode.id)

        # Assert
        test_session.refresh(episode)
        assert episode.workflow_status == WorkflowStatus.SEGMENTED.value


class TestSegmentationServiceAnalyzeAndSegment:
    """Test main analyze_and_segment method."""

    def test_analyze_and_segment_creates_chapters_from_transcript(self, test_session):
        """Given: Episode with TranscriptCues and mocked AI
        When: Calling analyze_and_segment
        Then: Returns Chapter list with Chinese titles
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        # Create segment for cues
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

        # Create cues
        for i in range(10):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 60.0,
                end_time=(i + 1) * 60.0,
                speaker="SPEAKER_00",
                text=f"Test sentence {i}"
            )
            test_session.add(cue)
        test_session.flush()

        # Mock AI response
        mock_ai = Mock()
        mock_ai.query.return_value = {
            "chapters": [
                {
                    "title": "开场介绍",
                    "summary": "主持人介绍了今天的主题",
                    "start_time": 0.0,
                    "end_time": 300.0
                },
                {
                    "title": "核心内容",
                    "summary": "深入讨论了核心话题",
                    "start_time": 300.0,
                    "end_time": 600.0
                }
            ]
        }

        service = SegmentationService(test_session, mock_ai)

        # Act
        chapters = service.analyze_and_segment(episode.id)

        # Assert
        assert len(chapters) == 2
        assert chapters[0].title == "开场介绍"
        assert chapters[0].summary == "主持人介绍了今天的主题"
        assert chapters[1].title == "核心内容"

        # Verify AI was called with prompt
        assert mock_ai.query.called
        call_args = mock_ai.query.call_args[0]
        assert "Test sentence 0" in call_args[0]

        # Verify episode status updated
        test_session.refresh(episode)
        assert episode.workflow_status == WorkflowStatus.SEGMENTED.value

    def test_analyze_and_segment_chinese_output(self, test_session):
        """Given: English transcript
        When: Calling analyze_and_segment
        Then: Chapter titles and summaries are in Chinese
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            speaker="SPEAKER_00",
            text="Hello world"
        )
        test_session.add(cue)
        test_session.flush()

        mock_ai = Mock()
        mock_ai.query.return_value = {
            "chapters": [
                {
                    "title": "开场介绍",
                    "summary": "这是中文摘要",
                    "start_time": 0.0,
                    "end_time": 600.0
                }
            ]
        }

        service = SegmentationService(test_session, mock_ai)

        # Act
        chapters = service.analyze_and_segment(episode.id)

        # Assert
        assert chapters[0].title == "开场介绍"
        # Verify Chinese characters present
        assert any('\u4e00' <= char <= '\u9fff' for char in chapters[0].summary)

    def test_analyze_and_segment_time_coverage(self, test_session):
        """Given: 600 second transcript
        When: Calling analyze_and_segment
        Then: Chapter time ranges cover full duration
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

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

        for i in range(10):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 60.0,
                end_time=(i + 1) * 60.0,
                speaker="SPEAKER_00",
                text=f"Text {i}"
            )
            test_session.add(cue)
        test_session.flush()

        mock_ai = Mock()
        mock_ai.query.return_value = {
            "chapters": [
                {"title": "第一章", "summary": "摘要1", "start_time": 0.0, "end_time": 200.0},
                {"title": "第二章", "summary": "摘要2", "start_time": 200.0, "end_time": 400.0},
                {"title": "第三章", "summary": "摘要3", "start_time": 400.0, "end_time": 600.0}
            ]
        }

        service = SegmentationService(test_session, mock_ai)

        # Act
        chapters = service.analyze_and_segment(episode.id)

        # Assert
        assert chapters[0].start_time == 0.0
        assert chapters[-1].end_time == 600.0

        # Verify continuity
        for i in range(len(chapters) - 1):
            assert chapters[i].end_time == chapters[i + 1].start_time

    def test_analyze_and_segment_cue_association(self, test_session):
        """Given: Multiple chapters
        When: Calling analyze_and_segment
        Then: Each cue associated to correct chapter
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

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

        # Create 10 cues
        cues = []
        for i in range(10):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 60.0,
                end_time=(i + 1) * 60.0,
                speaker="SPEAKER_00",
                text=f"Text {i}"
            )
            cues.append(cue)
            test_session.add(cue)
        test_session.flush()

        mock_ai = Mock()
        mock_ai.query.return_value = {
            "chapters": [
                {"title": "第一章", "summary": "摘要1", "start_time": 0.0, "end_time": 300.0},
                {"title": "第二章", "summary": "摘要2", "start_time": 300.0, "end_time": 600.0}
            ]
        }

        service = SegmentationService(test_session, mock_ai)

        # Act
        chapters = service.analyze_and_segment(episode.id)

        # Assert - refresh and verify associations
        test_session.refresh(cues[0])
        test_session.refresh(cues[5])

        # cues[0] (0-60s) -> chapter 1 (0-300s)
        assert cues[0].chapter_id == chapters[0].id

        # cues[5] (300-360s) -> chapter 2 (300-600s)
        assert cues[5].chapter_id == chapters[1].id

    def test_analyze_and_segment_raises_on_episode_not_found(self, test_session):
        """Given: Non-existent episode_id
        When: Calling analyze_and_segment
        Then: Raises ValueError
        """
        # Arrange
        mock_ai = Mock()
        service = SegmentationService(test_session, mock_ai)

        # Act & Assert
        with pytest.raises(ValueError, match="Episode 不存在"):
            service.analyze_and_segment(99999)

    def test_analyze_and_segment_raises_on_not_transcribed(self, test_session):
        """Given: Episode with DOWNLOADED status
        When: Calling analyze_and_segment
        Then: Raises ValueError
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            workflow_status=WorkflowStatus.DOWNLOADED.value
        )
        test_session.add(episode)
        test_session.flush()

        mock_ai = Mock()
        service = SegmentationService(test_session, mock_ai)

        # Act & Assert
        with pytest.raises(ValueError, match="Episode 未转录"):
            service.analyze_and_segment(episode.id)
