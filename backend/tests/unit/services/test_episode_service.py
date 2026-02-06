"""
单元测试：EpisodeService
"""

import pytest

from app.services.episode_service import EpisodeService
from app.models import Episode


class TestEpisodeServiceGetDisplayTitle:
    """测试 EpisodeService.get_display_title 方法"""

    def test_returns_original_title(self):
        """
        Given: Episode with non-empty title
        When: get_display_title() is called
        Then: Returns original title
        """
        # Arrange
        episode = Episode(
            id=1,
            title="Business English",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "Business English"

    def test_falls_back_to_show_name(self):
        """
        Given: Episode with empty title but has show_name
        When: get_display_title() is called
        Then: Returns "{show_name} - Episode #{id}"
        """
        # Arrange
        episode = Episode(
            id=42,
            title="",
            show_name="EnglishPod",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "EnglishPod - Episode #42"

    def test_falls_back_to_audio_path(self):
        """
        Given: Episode with empty title and show_name, but has audio_path
        When: get_display_title() is called
        Then: Returns filename without extension
        """
        # Arrange
        episode = Episode(
            id=1,
            title="",
            show_name=None,
            audio_path="D:/audios/ep1024_introduction.mp3",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "ep1024_introduction"

    def test_falls_back_to_source_url_youtube(self):
        """
        Given: Episode with only YouTube source_url
        When: get_display_title() is called
        Then: Returns parsed YouTube video ID
        """
        # Arrange
        episode = Episode(
            id=1,
            title="",
            show_name=None,
            audio_path=None,
            source_url="https://youtube.com/watch?v=xyz123",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "YouTube Video xyz123"

    def test_falls_back_to_source_url_youtu_be(self):
        """
        Given: Episode with youtu.be short URL
        When: get_display_title() is called
        Then: Returns parsed YouTube video ID
        """
        # Arrange
        episode = Episode(
            id=1,
            title="",
            show_name=None,
            audio_path=None,
            source_url="https://youtu.be/abc456",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "YouTube Video abc456"

    def test_falls_back_to_source_url_bilibili(self):
        """
        Given: Episode with Bilibili source_url
        When: get_display_title() is called
        Then: Returns parsed Bilibili BV/av number
        """
        # Arrange
        episode = Episode(
            id=1,
            title="",
            show_name=None,
            audio_path=None,
            source_url="https://www.bilibili.com/video/BV1xx411c7mD",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "Bilibili BV1xx411c7mD"

    def test_falls_back_to_id(self):
        """
        Given: Episode with no other metadata
        When: get_display_title() is called
        Then: Returns "Episode #{id}"
        """
        # Arrange
        episode = Episode(
            id=999,
            title="",
            show_name=None,
            audio_path=None,
            source_url=None,
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "Episode #999"

    def test_handles_whitespace_only_title(self):
        """
        Given: Episode with whitespace-only title
        When: get_display_title() is called
        Then: Falls back to next available option
        """
        # Arrange
        episode = Episode(
            id=1,
            title="   ",
            show_name="TestShow",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "TestShow - Episode #1"

    def test_title_is_sanitized(self):
        """
        Given: Episode with title containing newlines and extra spaces
        When: get_display_title() is called
        Then: Title is cleaned (newlines removed, spaces collapsed)
        """
        # Arrange
        episode = Episode(
            id=1,
            title="Multi\nLine   Title",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "Multi Line Title"

    def test_long_title_is_truncated(self):
        """
        Given: Episode with title exceeding max length
        When: get_display_title() is called
        Then: Title is truncated with ellipsis
        """
        # Arrange
        long_title = "A" * 150
        episode = Episode(
            id=1,
            title=long_title,
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert len(result) <= 100
        assert result.endswith("...")

    def test_show_name_with_whitespace_is_sanitized(self):
        """
        Given: Episode with show_name containing extra whitespace
        When: get_display_title() is called
        Then: show_name is stripped
        """
        # Arrange
        episode = Episode(
            id=1,
            title="",
            show_name="  EnglishPod  ",
            file_hash="abc123",
            duration=600.0
        )

        # Act
        result = EpisodeService.get_display_title(episode)

        # Assert
        assert result == "EnglishPod - Episode #1"
