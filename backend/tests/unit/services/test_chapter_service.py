"""
单元测试：ChapterService
"""

import pytest

from app.services.chapter_service import ChapterService
from app.models import Chapter, Episode


class TestChapterServiceGetDisplayTitle:
    """测试 ChapterService.get_display_title 方法"""

    @pytest.fixture
    def sample_episode(self):
        return Episode(
            id=1,
            title="Test Episode",
            file_hash="abc123",
            duration=600.0
        )

    def test_returns_original_title(self, sample_episode):
        """
        Given: Chapter with non-empty title
        When: get_display_title() is called
        Then: Returns original title
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="Opening",
            start_time=0.0,
            end_time=60.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Opening"

    def test_falls_back_to_time_range(self, sample_episode):
        """
        Given: Chapter with empty title
        When: get_display_title() is called
        Then: Returns "Chapter {index+1} (HH:MM-HH:MM)"
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=2,
            title="",
            start_time=125.5,
            end_time=310.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Chapter 3 (02:05-05:10)"

    def test_falls_back_to_simple_index(self, sample_episode):
        """
        Given: Chapter with empty title, time range is 0-0
        When: get_display_title() is called
        Then: Returns "Chapter {index+1}"
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="",
            start_time=0.0,
            end_time=0.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Chapter 1"

    def test_handles_whitespace_only_title(self, sample_episode):
        """
        Given: Chapter with whitespace-only title
        When: get_display_title() is called
        Then: Falls back to time range
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="   ",
            start_time=30.0,
            end_time=90.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Chapter 1 (00:30-01:30)"

    def test_time_formatting_with_seconds(self, sample_episode):
        """
        Given: Chapter with specific start/end times
        When: get_display_title() is called
        Then: Time is formatted as MM:SS
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="",
            start_time=65.5,
            end_time=125.8
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Chapter 1 (01:05-02:05)"

    def test_time_formatting_hours_minutes(self, sample_episode):
        """
        Given: Chapter with long duration (hours)
        When: get_display_title() is called
        Then: Time is formatted correctly (overflow minutes)
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="",
            start_time=3665.0,  # 61 minutes 5 seconds
            end_time=7325.0    # 122 minutes 5 seconds
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Chapter 1 (61:05-122:05)"

    def test_title_is_sanitized(self, sample_episode):
        """
        Given: Chapter with title containing newlines
        When: get_display_title() is called
        Then: Title is cleaned
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="Multi\nLine   Title",
            start_time=0.0,
            end_time=60.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Multi Line Title"

    def test_long_title_is_truncated(self, sample_episode):
        """
        Given: Chapter with title exceeding max length
        When: get_display_title() is called
        Then: Title is truncated with ellipsis
        """
        # Arrange
        long_title = "A" * 150
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title=long_title,
            start_time=0.0,
            end_time=60.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert len(result) <= 100
        assert result.endswith("...")

    def test_chapter_with_start_time_only(self, sample_episode):
        """
        Given: Chapter with only start_time > 0, end_time = 0
        When: get_display_title() is called
        Then: Returns time range format
        """
        # Arrange
        chapter = Chapter(
            episode_id=1,
            chapter_index=0,
            title="",
            start_time=30.0,
            end_time=0.0
        )

        # Act
        result = ChapterService.get_display_title(chapter, sample_episode)

        # Assert
        assert result == "Chapter 1 (00:30-00:00)"
