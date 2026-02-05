"""
Configuration Module Tests

Tests the hierarchical configuration system without hardcoding API keys.
Uses pytest monkeypatch to set temporary environment variables.
"""
import os
from pathlib import Path
import pytest

from app.config import (
    get_config,
    reload_config,
    APP_NAME,
    APP_VERSION,
    MOONSHOT_MODEL,
    ZHIPU_MODEL,
    GEMINI_MODEL,
    WHISPER_DEVICE,
    BASE_DIR,
    CONFIG_PATH,
)


class TestConfigYAML:
    """Test YAML configuration loading."""

    def test_config_file_exists(self):
        """Test that config.yaml file exists."""
        assert CONFIG_PATH.exists(), f"Config file not found: {CONFIG_PATH}"

    def test_base_dir_exists(self):
        """Test that BASE_DIR is correctly set."""
        assert BASE_DIR.exists(), f"Base directory not found: {BASE_DIR}"
        assert (BASE_DIR / "app").exists(), "app directory not found in BASE_DIR"

    def test_get_config_app_name(self):
        """Test getting application name from config."""
        app_name = get_config("app.name")
        assert app_name is not None
        assert app_name == "EnglishPod-KnowledgeBase"

    def test_get_config_ai_models(self):
        """Test getting AI model names from config."""
        moonshot_model = get_config("ai.moonshot.model")
        zhipu_model = get_config("ai.zhipu.model")
        gemini_model = get_config("ai.gemini.model")

        assert moonshot_model == "moonshot-v1-8k"
        assert zhipu_model == "glm-4-plus"
        assert gemini_model == "gemini-2.5-flash"

    def test_get_config_audio_settings(self):
        """Test getting audio processing settings."""
        whisper_device = get_config("audio.whisper_device")
        whisper_model = get_config("audio.whisper_model")
        segment_duration = get_config("audio.segment_duration")

        assert whisper_device == "cuda"
        assert whisper_model == "base"
        assert segment_duration == 180

    def test_get_config_with_default(self):
        """Test get_config with default value for non-existent key."""
        value = get_config("non.existent.key", default="default_value")
        assert value == "default_value"

    def test_get_config_nested_missing_key(self):
        """Test get_config with missing nested key returns None."""
        value = get_config("ai.missing_service.model")
        assert value is None


class TestConfigConstants:
    """Test configuration constants exposed by the module."""

    def test_app_constants(self):
        """Test application configuration constants."""
        assert APP_NAME == "EnglishPod-KnowledgeBase"
        assert APP_VERSION is not None
        assert isinstance(APP_VERSION, str)

    def test_ai_model_constants(self):
        """Test AI model configuration constants."""
        assert MOONSHOT_MODEL == "moonshot-v1-8k"
        assert ZHIPU_MODEL == "glm-4-plus"
        assert GEMINI_MODEL == "gemini-2.5-flash"

    def test_audio_constants(self):
        """Test audio processing configuration constants."""
        assert WHISPER_DEVICE == "cuda"


class TestEnvironmentVariables:
    """Test environment variable loading for API keys."""

    def test_gemini_api_key_from_env(self, monkeypatch):
        """Test GEMINI_API_KEY is loaded from environment variable."""
        # Import fresh to pick up new environment variable
        monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key_12345")

        # Reload the config module to pick up the new environment variable
        import importlib
        import app.config
        importlib.reload(app.config)

        from app.config import GEMINI_API_KEY
        assert GEMINI_API_KEY == "test_gemini_key_12345"

    def test_moonshot_api_key_from_env(self, monkeypatch):
        """Test MOONSHOT_API_KEY is loaded from environment variable."""
        monkeypatch.setenv("MOONSHOT_API_KEY", "test_moonshot_key_67890")

        import importlib
        import app.config
        importlib.reload(app.config)

        from app.config import MOONSHOT_API_KEY
        assert MOONSHOT_API_KEY == "test_moonshot_key_67890"

    def test_zhipu_api_key_from_env(self, monkeypatch):
        """Test ZHIPU_API_KEY is loaded from environment variable."""
        monkeypatch.setenv("ZHIPU_API_KEY", "test_zhipu_key_abcde")

        import importlib
        import app.config
        importlib.reload(app.config)

        from app.config import ZHIPU_API_KEY
        assert ZHIPU_API_KEY == "test_zhipu_key_abcde"

    def test_hf_token_from_env(self, monkeypatch):
        """Test HF_TOKEN is loaded from environment variable."""
        monkeypatch.setenv("HF_TOKEN", "test_hf_token_xyz")

        import importlib
        import app.config
        importlib.reload(app.config)

        from app.config import HF_TOKEN
        assert HF_TOKEN == "test_hf_token_xyz"

    def test_missing_required_env_raises_error(self, monkeypatch):
        """Test that missing required environment variable raises ValueError."""
        # Remove all required environment variables
        for key in ["GEMINI_API_KEY", "MOONSHOT_API_KEY", "ZHIPU_API_KEY", "HF_TOKEN"]:
            monkeypatch.delenv(key, raising=False)

        import importlib
        import app.config

        # Reloading should raise an error for any missing required key
        # The error will be for the first missing key encountered during import
        with pytest.raises(ValueError, match="API_KEY|HF_TOKEN"):
            importlib.reload(app.config)


class TestConfigPaths:
    """Test path-related configuration."""

    def test_database_path(self):
        """Test database path is correctly resolved."""
        from app.config import DATABASE_PATH
        assert DATABASE_PATH is not None
        assert "episodes.db" in DATABASE_PATH

    def test_audio_storage_path(self):
        """Test audio storage path is correctly resolved."""
        from app.config import AUDIO_STORAGE_PATH
        assert AUDIO_STORAGE_PATH is not None
        assert "audios" in AUDIO_STORAGE_PATH

    def test_log_file_path(self):
        """Test log file path is correctly resolved."""
        from app.config import LOG_FILE
        assert LOG_FILE is not None
        assert "logs" in LOG_FILE


class TestConfigReload:
    """Test configuration reload functionality."""

    def test_reload_config(self):
        """Test that reload_config() function works."""
        # This test just verifies the function can be called without error
        # The actual reload would only pick up changes to config.yaml
        reload_config()
        # If we get here without exception, the test passes
        assert True
