"""
Unit tests for WhisperService.

Note: These tests require WhisperX models to be loaded.
Most tests use mocking to avoid heavy dependencies.
"""
import os
import tempfile
from unittest.mock import Mock, MagicMock, patch

import pytest

from app.services.whisper.whisper_service import WhisperService


class TestWhisperServiceLoadModels:
    """Test WhisperService model loading."""

    @patch('app.services.whisper.whisper_service.whisperx')
    @patch('app.services.whisper.whisper_service.torch')
    def test_load_models_sets_cuda_device_when_available(self, mock_torch, mock_whisperx):
        """Given: CUDA is available
        When: Calling load_models
        Then: Sets _device to "cuda" and _compute_type to "float16"
        """
        # Arrange
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_name.return_value = "NVIDIA RTX 5070"
        mock_model = Mock()
        mock_whisperx.load_model.return_value = mock_model

        WhisperService._models_loaded = False

        # Act
        WhisperService.load_models(model_name="base")

        # Assert
        assert WhisperService._device == "cuda"
        assert WhisperService._compute_type == "float16"
        assert WhisperService._models_loaded is True

    @patch('app.services.whisper.whisper_service.whisperx')
    @patch('app.services.whisper.whisper_service.torch')
    def test_load_models_sets_cpu_when_cuda_unavailable(self, mock_torch, mock_whisperx):
        """Given: CUDA is not available
        When: Calling load_models
        Then: Sets _device to "cpu" and _compute_type to "int8"
        """
        # Arrange
        mock_torch.cuda.is_available.return_value = False
        mock_model = Mock()
        mock_whisperx.load_model.return_value = mock_model

        WhisperService._models_loaded = False

        # Act
        WhisperService.load_models(model_name="base")

        # Assert
        assert WhisperService._device == "cpu"
        assert WhisperService._compute_type == "int8"

    @patch('app.services.whisper.whisper_service.whisperx')
    def test_load_models_skips_when_already_loaded(self, mock_whisperx):
        """Given: Models already loaded
        When: Calling load_models again
        Then: Skips loading and returns early
        """
        # Arrange
        WhisperService._models_loaded = True

        # Act
        WhisperService.load_models()

        # Assert
        mock_whisperx.load_model.assert_not_called()


class TestWhisperServiceGetInstance:
    """Test WhisperService singleton pattern."""

    @patch('app.services.whisper.whisper_service.whisperx')
    def test_get_instance_returns_same_instance(self, mock_whisperx):
        """Given: Models are loaded
        When: Calling get_instance multiple times
        Then: Returns the same instance
        """
        # Arrange
        WhisperService._models_loaded = True
        WhisperService._instance = None

        # Act
        instance1 = WhisperService.get_instance()
        instance2 = WhisperService.get_instance()

        # Assert
        assert instance1 is instance2

    def test_get_instance_raises_when_models_not_loaded(self):
        """Given: Models not loaded
        When: Calling get_instance
        Then: Raises RuntimeError
        """
        # Arrange - Reset both class variables
        WhisperService._models_loaded = False
        WhisperService._instance = None

        # Act & Assert
        with pytest.raises(RuntimeError, match="模型未加载"):
            WhisperService.get_instance()


class TestWhisperServiceTranscribeSegment:
    """Test segment transcription."""

    @patch('app.services.whisper.whisper_service.whisperx')
    def test_transcribe_segment_raises_on_nonexistent_file(self, mock_whisperx):
        """Given: A non-existent audio file path
        When: Calling transcribe_segment
        Then: Raises FileNotFoundError
        """
        # Arrange
        WhisperService._models_loaded = True
        service = object.__new__(WhisperService)
        service._gpu_lock = MagicMock()
        service._diarize_model = None

        # Act & Assert
        with pytest.raises(FileNotFoundError):
            service.transcribe_segment("/nonexistent/audio.wav")


class TestWhisperServiceFormatResult:
    """Test result formatting."""

    def test_format_result_to_cues_converts_whisperx_format(self):
        """Given: WhisperX result with segments
        When: Calling _format_result_to_cues
        Then: Returns list of cue dictionaries
        """
        # Arrange
        WhisperService._models_loaded = True
        service = object.__new__(WhisperService)

        whisperx_result = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.5,
                    "speaker": "SPEAKER_00",
                    "text": "Hello world"
                },
                {
                    "start": 3.5,
                    "end": 7.0,
                    "speaker": "SPEAKER_01",
                    "text": "How are you?"
                }
            ]
        }

        # Act
        cues = service._format_result_to_cues(whisperx_result)

        # Assert
        assert len(cues) == 2
        assert cues[0]["start"] == 0.0
        assert cues[0]["end"] == 3.5
        assert cues[0]["speaker"] == "SPEAKER_00"
        assert cues[0]["text"] == "Hello world"

    def test_format_result_to_cues_filters_empty_text(self):
        """Given: WhisperX result with empty text segments
        When: Calling _format_result_to_cues
        Then: Filters out segments with empty text
        """
        # Arrange
        WhisperService._models_loaded = True
        service = object.__new__(WhisperService)

        whisperx_result = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.5,
                    "speaker": "SPEAKER_00",
                    "text": "Hello"
                },
                {
                    "start": 3.5,
                    "end": 7.0,
                    "speaker": "SPEAKER_01",
                    "text": "   "  # Whitespace only
                },
                {
                    "start": 7.0,
                    "end": 10.0,
                    "speaker": "SPEAKER_00",
                    "text": ""  # Empty
                }
            ]
        }

        # Act
        cues = service._format_result_to_cues(whisperx_result)

        # Assert
        assert len(cues) == 1
        assert cues[0]["text"] == "Hello"


class TestWhisperServiceDeviceInfo:
    """Test device information methods."""

    @patch('app.services.whisper.whisper_service.torch')
    @patch('app.services.whisper.whisper_service.psutil')
    def test_get_device_info_returns_correct_info(self, mock_psutil, mock_torch):
        """Given: WhisperService with loaded models
        When: Calling get_device_info
        Then: Returns dictionary with device information
        """
        # Arrange
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.current_device.return_value = 0
        mock_torch.cuda.get_device_properties.return_value.total_memory = 8 * 1024**3
        mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 3 * 1024**3

        mock_mem = Mock()
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 8 * 1024**3
        mock_mem.used = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem

        WhisperService._device = "cuda"
        WhisperService._compute_type = "float16"
        WhisperService._models_loaded = True
        WhisperService._diarize_model = None
        WhisperService._align_model = None

        # Act
        info = WhisperService.get_device_info()

        # Assert
        assert info["device"] == "cuda"
        assert info["compute_type"] == "float16"
        assert info["asr_model_loaded"] is True
        assert info["cuda_available"] is True
