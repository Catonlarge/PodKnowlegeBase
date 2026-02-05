"""
Unit tests for file_utils module.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from app.utils.file_utils import (
    calculate_md5_sync,
    calculate_md5_async,
    get_audio_duration,
    is_valid_audio_header,
    validate_audio_file,
    get_file_extension,
    format_file_size,
    ALLOWED_EXTENSIONS,
)


class TestCalculateMd5:
    """Test MD5 calculation functions."""

    def test_calculate_md5_sync_returns_correct_hash(self):
        """Given: A test file with known content
        When: Calling calculate_md5_sync
        Then: Returns correct MD5 hash
        """
        # Arrange
        test_content = b"Hello, World!"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Act
            result = calculate_md5_sync(temp_path)

            # Assert
            expected_hash = "65a8e27d8879283831b664bd8b7f0ad4"  # MD5 of "Hello, World!"
            assert result == expected_hash
        finally:
            os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_calculate_md5_async_returns_correct_hash(self):
        """Given: A test file with known content
        When: Calling calculate_md5_async
        Then: Returns correct MD5 hash
        """
        # Arrange
        test_content = b"Async MD5 Test"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Act
            result = await calculate_md5_async(temp_path)

            # Assert
            expected_hash = "566cbedbd88d1833d6e31f413838d5e8"  # MD5 of "Async MD5 Test"
            assert result == expected_hash
        finally:
            os.remove(temp_path)

    def test_calculate_md5_sync_raises_on_nonexistent_file(self):
        """Given: A non-existent file path
        When: Calling calculate_md5_sync
        Then: Raises FileNotFoundError
        """
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            calculate_md5_sync("/nonexistent/path/to/file.txt")


class TestGetAudioDuration:
    """Test audio duration retrieval."""

    def test_get_audio_duration_raises_on_nonexistent_file(self):
        """Given: A non-existent audio file path
        When: Calling get_audio_duration
        Then: Raises FileNotFoundError
        """
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            get_audio_duration("/nonexistent/audio.mp3")

    def test_get_audio_duration_raises_on_text_file(self):
        """Given: A text file pretending to be audio
        When: Calling get_audio_duration
        Then: Raises RuntimeError
        """
        # Arrange
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mp3', delete=False) as f:
            f.write("This is not an audio file")
            temp_path = f.name

        try:
            # Act & Assert
            with pytest.raises(RuntimeError):
                get_audio_duration(temp_path)
        finally:
            os.remove(temp_path)


class TestIsValidAudioHeader:
    """Test audio header validation."""

    def test_is_valid_audio_header_detects_text_file(self):
        """Given: A text file with HTML content
        When: Calling is_valid_audio_header
        Then: Returns False
        """
        # Arrange
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mp3', delete=False) as f:
            f.write("<!DOCTYPE html><html>This is HTML</html>")
            temp_path = f.name

        try:
            # Act
            result = is_valid_audio_header(temp_path)

            # Assert
            assert result is False
        finally:
            os.remove(temp_path)

    def test_is_valid_audio_header_detects_json_file(self):
        """Given: A JSON file
        When: Calling is_valid_audio_header
        Then: Returns False
        """
        # Arrange
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mp3', delete=False) as f:
            f.write('{"error": "fake audio file"}')
            temp_path = f.name

        try:
            # Act
            result = is_valid_audio_header(temp_path)

            # Assert
            assert result is False
        finally:
            os.remove(temp_path)

    def test_is_valid_audio_header_detects_empty_file(self):
        """Given: An empty file
        When: Calling is_valid_audio_header
        Then: Returns False
        """
        # Arrange
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            # Act
            result = is_valid_audio_header(temp_path)

            # Assert
            assert result is False
        finally:
            os.remove(temp_path)

    def test_is_valid_audio_header_accepts_binary_file(self):
        """Given: A binary file with non-printable characters
        When: Calling is_valid_audio_header
        Then: Returns True (passes basic check)
        """
        # Arrange
        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write binary content with high ratio of non-printable characters
            binary_content = bytes([0xFF, 0xFE, 0xFD, 0xFC] * 20)
            f.write(binary_content)
            temp_path = f.name

        try:
            # Act
            result = is_valid_audio_header(temp_path)

            # Assert
            # Should pass as potential binary audio file
            assert result is True
        finally:
            os.remove(temp_path)


class TestValidateAudioFile:
    """Test audio file validation."""

    def test_validate_audio_file_accepts_mp3(self):
        """Given: An .mp3 filename with valid size
        When: Calling validate_audio_file
        Then: Returns (True, "")
        """
        # Arrange
        filename = "test_audio.mp3"
        file_size = 1024 * 1024  # 1 MB

        # Act
        is_valid, error_msg = validate_audio_file(filename, file_size)

        # Assert
        assert is_valid is True
        assert error_msg == ""

    def test_validate_audio_file_accepts_wav(self):
        """Given: A .wav filename with valid size
        When: Calling validate_audio_file
        Then: Returns (True, "")
        """
        # Arrange
        filename = "test_audio.wav"
        file_size = 5 * 1024 * 1024  # 5 MB

        # Act
        is_valid, error_msg = validate_audio_file(filename, file_size)

        # Assert
        assert is_valid is True
        assert error_msg == ""

    def test_validate_audio_file_rejects_exe(self):
        """Given: A .exe filename
        When: Calling validate_audio_file
        Then: Returns (False, error message with .exe)
        """
        # Arrange
        filename = "malicious.exe"
        file_size = 1024

        # Act
        is_valid, error_msg = validate_audio_file(filename, file_size)

        # Assert
        assert is_valid is False
        assert ".exe" in error_msg
        assert "不支持的文件格式" in error_msg

    def test_validate_audio_file_rejects_large_file(self):
        """Given: A file exceeding MAX_FILE_SIZE
        When: Calling validate_audio_file
        Then: Returns (False, error message about size)
        """
        # Arrange
        filename = "huge_audio.mp3"
        file_size = 2 * 1024 * 1024 * 1024  # 2 GB (assuming MAX_FILE_SIZE is 1 GB)

        # Act
        is_valid, error_msg = validate_audio_file(filename, file_size)

        # Assert
        assert is_valid is False
        assert "超过限制" in error_msg or "文件大小" in error_msg

    def test_validate_audio_file_rejects_zero_size(self):
        """Given: A file with zero size
        When: Calling validate_audio_file
        Then: Returns (False, error message about invalid size)
        """
        # Arrange
        filename = "empty.mp3"
        file_size = 0

        # Act
        is_valid, error_msg = validate_audio_file(filename, file_size)

        # Assert
        assert is_valid is False
        assert "无效" in error_msg

    def test_validate_audio_file_rejects_negative_size(self):
        """Given: A file with negative size
        When: Calling validate_audio_file
        Then: Returns (False, error message about invalid size)
        """
        # Arrange
        filename = "negative.mp3"
        file_size = -100

        # Act
        is_valid, error_msg = validate_audio_file(filename, file_size)

        # Assert
        assert is_valid is False
        assert "无效" in error_msg


class TestGetFileExtension:
    """Test file extension extraction."""

    def test_get_file_extension_returns_lowercase_with_dot(self):
        """Given: A filename with extension
        When: Calling get_file_extension
        Then: Returns lowercase extension with dot
        """
        # Arrange & Act
        result1 = get_file_extension("test.MP3")
        result2 = get_file_extension("audio.WAV")
        result3 = get_file_extension("document.pdf")

        # Assert
        assert result1 == ".mp3"
        assert result2 == ".wav"
        assert result3 == ".pdf"

    def test_get_file_extension_handles_no_extension(self):
        """Given: A filename without extension
        When: Calling get_file_extension
        Then: Returns empty string
        """
        # Arrange & Act
        result = get_file_extension("no_extension_file")

        # Assert
        assert result == ""


class TestFormatFileSize:
    """Test file size formatting."""

    def test_format_file_size_bytes(self):
        """Given: A size in bytes (< 1 KB)
        When: Calling format_file_size
        Then: Returns format in bytes
        """
        # Arrange & Act
        result = format_file_size(512)

        # Assert
        assert result == "512 B"

    def test_format_file_size_kilobytes(self):
        """Given: A size in kilobytes (< 1 MB)
        When: Calling format_file_size
        Then: Returns format in KB
        """
        # Arrange & Act
        result = format_file_size(5 * 1024)

        # Assert
        assert result == "5.00 KB"

    def test_format_file_size_megabytes(self):
        """Given: A size in megabytes (< 1 GB)
        When: Calling format_file_size
        Then: Returns format in MB
        """
        # Arrange & Act
        result = format_file_size(10 * 1024 * 1024)

        # Assert
        assert result == "10.00 MB"

    def test_format_file_size_gigabytes(self):
        """Given: A size in gigabytes
        When: Calling format_file_size
        Then: Returns format in GB
        """
        # Arrange & Act
        result = format_file_size(2 * 1024 * 1024 * 1024)

        # Assert
        assert result == "2.00 GB"


class TestAllowedExtensions:
    """Test ALLOWED_EXTENSIONS constant."""

    def test_allowed_extensions_contains_common_formats(self):
        """Given: The ALLOWED_EXTENSIONS constant
        When: Checking for common audio formats
        Then: Contains mp3, wav, m4a, flac, ogg, aac
        """
        # Assert
        assert ".mp3" in ALLOWED_EXTENSIONS
        assert ".wav" in ALLOWED_EXTENSIONS
        assert ".m4a" in ALLOWED_EXTENSIONS
        assert ".flac" in ALLOWED_EXTENSIONS
        assert ".ogg" in ALLOWED_EXTENSIONS
        assert ".aac" in ALLOWED_EXTENSIONS
