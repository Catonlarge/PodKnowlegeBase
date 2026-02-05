"""
Unit tests for DownloadService.

These tests use mocking to avoid actual network calls.
"""
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.download_service import DownloadService
from app.models import Episode
from app.enums.workflow_status import WorkflowStatus


class TestDownloadServiceInit:
    """Test DownloadService initialization."""

    @patch('app.services.download_service.Path')
    def test_init_creates_storage_directory(self, mock_path, test_session):
        """Given: A test session
        When: Initializing DownloadService
        Then: Creates storage directory if not exists
        """
        # Arrange
        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj
        mock_path_obj.__truediv__ = MagicMock(return_value=mock_path_obj)

        # Act
        service = DownloadService(test_session)

        # Assert
        mock_path_obj.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestDownloadServiceCheckDuplicate:
    """Test duplicate detection."""

    def test_check_duplicate_returns_existing_episode(self, test_session):
        """Given: Episode with file_hash exists in database
        When: Calling _check_duplicate
        Then: Returns the existing Episode
        """
        # Arrange
        episode = Episode(
            title="Existing Episode",
            source_url="https://example.com/audio.mp3",
            file_hash="abc123",
            duration=300.0,
            workflow_status=WorkflowStatus.DOWNLOADED.value
        )
        test_session.add(episode)
        test_session.flush()

        service = DownloadService(test_session)

        # Act
        result = service._check_duplicate("abc123")

        # Assert
        assert result is not None
        assert result.id == episode.id
        assert result.file_hash == "abc123"

    def test_check_duplicate_returns_none_when_not_found(self, test_session):
        """Given: No Episode with the file_hash
        When: Calling _check_duplicate
        Then: Returns None
        """
        # Arrange
        service = DownloadService(test_session)

        # Act
        result = service._check_duplicate("nonexistent_hash")

        # Assert
        assert result is None


class TestDownloadServiceExtractMetadata:
    """Test metadata extraction with yt-dlp."""

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    def test_extract_metadata_returns_dict(self, test_session):
        """Given: yt-dlp is available
        When: Calling _extract_metadata
        Then: Returns metadata dictionary with title and duration
        """
        # Arrange
        service = DownloadService(test_session)

        # Mock yt-dlp context manager properly
        mock_info = {
            'title': 'Test Audio',
            'duration': 300,
            'thumbnail': 'https://example.com/thumb.jpg',
            'description': 'Test description'
        }

        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_info
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            # Act
            metadata = service._extract_metadata(
                "https://www.youtube.com/watch?v=test123",
                "/tmp/test.mp3"
            )

            # Assert
            assert metadata["title"] == "Test Audio"
            assert metadata["duration"] == 300
            assert metadata["thumbnail"] == "https://example.com/thumb.jpg"


class TestDownloadServiceDownloadWithRetry:
    """Test download with exponential backoff retry."""

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    @patch('app.services.download_service.os.path.exists')
    @patch('app.services.download_service.os.rename')
    def test_download_with_retry_succeeds_on_first_attempt(
        self, mock_rename, mock_exists, test_session
    ):
        """Given: Network is working
        When: Calling _download_with_retry
        Then: Downloads successfully without retry
        """
        # Arrange
        service = DownloadService(test_session)
        mock_exists.return_value = True  # Simulate file exists

        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.download.return_value = None  # Success
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp_path = tmp.name

            try:
                # Act
                result = service._download_with_retry(
                    "https://example.com/audio.mp3",
                    tmp_path,
                    max_retries=3,
                    base_delay=0.1
                )

                # Assert
                assert result is True
                assert mock_ydl_instance.download.call_count == 1
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    @patch('app.services.download_service.os.path.exists')
    @patch('app.services.download_service.os.rename')
    def test_download_with_retry_succeeds_on_second_attempt(
        self, mock_rename, mock_exists, test_session
    ):
        """Given: First download fails, second succeeds
        When: Calling _download_with_retry
        Then: Retries once and succeeds
        """
        # Arrange
        service = DownloadService(test_session)
        mock_exists.return_value = True

        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        # First call fails, second succeeds
        mock_ydl_instance.download.side_effect = [Exception("Network error"), None]
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp_path = tmp.name

            try:
                # Act
                result = service._download_with_retry(
                    "https://example.com/audio.mp3",
                    tmp_path,
                    max_retries=3,
                    base_delay=0.05
                )

                # Assert
                assert result is True
                assert mock_ydl_instance.download.call_count == 2
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    @patch('app.services.download_service.os.path.exists')
    @patch('app.services.download_service.os.rename')
    def test_download_with_retry_fails_after_max_retries(
        self, mock_rename, mock_exists, test_session
    ):
        """Given: All download attempts fail
        When: Calling _download_with_retry
        Then: Raises RuntimeError after max_retries
        """
        # Arrange
        service = DownloadService(test_session)

        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.download.side_effect = Exception("Persistent error")
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp_path = tmp.name

            try:
                # Act & Assert
                with pytest.raises(RuntimeError, match="下载失败"):
                    service._download_with_retry(
                        "https://example.com/audio.mp3",
                        tmp_path,
                        max_retries=3,
                        base_delay=0.01
                    )

                assert mock_ydl_instance.download.call_count == 3
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


class TestDownloadServiceDownloadWithMetadata:
    """Test download and Episode creation."""

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    @patch('app.services.download_service.get_audio_duration')
    @patch('app.services.download_service.calculate_md5_sync')
    def test_download_with_metadata_creates_episode(
        self, mock_md5, mock_duration, test_session
    ):
        """Given: Valid URL and yt-dlp available
        When: Calling download_with_metadata
        Then: Creates Episode with all fields populated
        """
        # Arrange
        url = "https://www.youtube.com/watch?v=test123"
        mock_duration.return_value = 300.0
        mock_md5.return_value = "abc123def456"

        service = DownloadService(test_session)

        # Mock yt-dlp for metadata extraction
        mock_info = {
            'title': 'Test Episode Title',
            'duration': 300,
            'thumbnail': 'https://example.com/thumb.jpg',
            'description': 'Test description'
        }

        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_info
        mock_ydl_instance.download.return_value = None
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        # Mock file operations
        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            with patch('app.services.download_service.os.path.exists', return_value=True):
                # Create temp file to simulate downloaded file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    temp_path = tmp.name

                try:
                    # Mock the storage path to use our temp file
                    with patch.object(service, 'storage_path', Path(temp_path).parent):
                        with patch.object(service, '_generate_filename', return_value=Path(temp_path).name):
                            # Act
                            episode = service.download_with_metadata(url)

                            # Assert
                            assert episode.id is not None
                            assert episode.source_url == url
                            assert episode.title == "Test Episode Title"
                            assert episode.duration == 300.0
                            assert episode.file_hash == "abc123def456"
                            assert episode.audio_path is not None
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    @patch('app.services.download_service.calculate_md5_sync')
    def test_download_with_metadata_returns_existing_on_duplicate(
        self, mock_md5, test_session
    ):
        """Given: URL already downloaded (same file_hash)
        When: Calling download_with_metadata again
        Then: Returns existing Episode without re-downloading
        """
        # Arrange
        url = "https://www.youtube.com/watch?v=test123"
        file_hash = "abc123def456"
        mock_md5.return_value = file_hash

        # Create existing Episode
        existing = Episode(
            title="Existing Episode",
            source_url=url,
            file_hash=file_hash,
            duration=300.0,
            audio_path="/fake/path.mp3"
        )
        test_session.add(existing)
        test_session.flush()

        service = DownloadService(test_session)

        # Mock metadata extraction
        mock_info = {'title': 'Test', 'duration': 300, 'thumbnail': None, 'description': ''}
        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_info
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            with patch('app.services.download_service.os.path.exists', return_value=True):
                with patch('app.services.download_service.os.remove'):
                    # Act
                    episode = service.download_with_metadata(url)

                    # Assert - Should return existing episode
                    assert episode.id == existing.id
                    assert episode.title == "Existing Episode"


class TestDownloadServiceDownload:
    """Test basic download method."""

    @patch('app.services.download_service.YOUTUBE_DL_AVAILABLE', True)
    @patch('app.services.download_service.get_audio_duration')
    @patch('app.services.download_service.calculate_md5_sync')
    def test_download_returns_path_and_metadata(
        self, mock_md5, mock_duration, test_session
    ):
        """Given: Valid URL
        When: Calling download
        Then: Returns (local_path, metadata) tuple
        """
        # Arrange
        url = "https://www.youtube.com/watch?v=test123"
        mock_duration.return_value = 180.0
        mock_md5.return_value = "xyz789"

        service = DownloadService(test_session)

        # Mock yt-dlp
        mock_info = {
            'title': 'Test Audio',
            'duration': 180,
            'thumbnail': None,
            'description': ''
        }

        mock_ydl_class = MagicMock()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_info
        mock_ydl_instance.download.return_value = None
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

        with patch('app.services.download_service.yt_dlp.YoutubeDL', mock_ydl_class):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                temp_path = tmp.name

            try:
                with patch('app.services.download_service.os.path.exists', return_value=True):
                    with patch.object(service, 'storage_path', Path(temp_path).parent):
                        with patch.object(service, '_generate_filename', return_value=Path(temp_path).name):
                            # Act
                            local_path, metadata = service.download(url)

                            # Assert
                            assert metadata["title"] == "Test Audio"
                            assert metadata["duration"] == 180
                            assert metadata["file_hash"] == "xyz789"
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)


class TestDownloadServiceFilenameGeneration:
    """Test filename generation for downloaded files."""

    def test_generate_filename_from_url(self, test_session):
        """Given: YouTube URL
        When: Generating filename
        Then: Returns safe filename with .mp3 extension
        """
        # Arrange
        service = DownloadService(test_session)
        url = "https://www.youtube.com/watch?v=test123"

        # Act
        filename = service._generate_filename(url, "Test Episode Title")

        # Assert
        assert filename.endswith(".mp3")
        assert "test123" in filename or "Test_Episode_Title" in filename

    def test_generate_filename_sanitizes_special_chars(self, test_session):
        """Given: Title with special characters
        When: Generating filename
        Then: Removes/replaces unsafe characters
        """
        # Arrange
        service = DownloadService(test_session)

        # Act
        filename = service._generate_filename(
            "https://example.com/test",
            "Test: Episode/Title? <Special>Chars & \"Quotes\" [Brackets]"
        )

        # Assert - Should not contain special characters that are unsafe for filenames
        assert ":" not in filename
        assert "/" not in filename
        assert "?" not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert '"' not in filename
        assert "[" not in filename
        assert "]" not in filename

    def test_generate_filename_replaces_non_ascii_chars(self, test_session):
        """Given: Title with Chinese and special characters
        When: Generating filename
        Then: Replaces non-ASCII characters with underscores, preserves safe chars
        """
        # Arrange
        service = DownloadService(test_session)

        # Act
        filename = service._generate_filename(
            "https://example.com/test",
            "EnglishPod_Daily对话 Episode01：欢迎学习"
        )

        # Assert
        assert filename.endswith(".mp3")
        # Should replace Chinese characters with underscores
        assert "欢迎学习" not in filename
        # Should preserve safe ASCII characters (letters, numbers, hyphens, underscores)
        assert "EnglishPod" in filename
        assert "Daily" in filename
        assert "Episode01" in filename
        # Should only contain safe characters
        assert re.match(r'^[a-zA-Z0-9_\-\.]+$', filename.replace('.mp3', ''))
