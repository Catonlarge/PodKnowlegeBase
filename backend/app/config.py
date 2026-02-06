"""
EnglishPod-KnowledgeBase Configuration Module

This module implements a hierarchical configuration system:
1. API Keys are retrieved from Windows environment variables (NOT from .env files)
2. Other settings are loaded from config.yaml file

Environment Variables (Required):
    - GEMINI_API_KEY: Google Gemini API key
    - MOONSHOT_API_KEY: Moonshot Kimi API key
    - ZHIPU_API_KEY: Zhipu AI GLM API key
    - HF_TOKEN: HuggingFace token for WhisperX diarization

Usage in Windows PowerShell:
    # Temporary (current session only):
    $env:GEMINI_API_KEY="your_key_here"

    # Permanent:
    setx GEMINI_API_KEY "your_key_here"
"""
import os
from pathlib import Path
from typing import Optional

import yaml


# ==================== Path Configuration ====================
# Get the project root directory (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"


# ==================== Load YAML Configuration ====================
def _load_yaml_config():
    """Load configuration from config.yaml file."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_PATH}\n"
            "Please create config.yaml in the backend directory."
        )

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Load config at module import time
_config = _load_yaml_config()


def get_config(key: str, default=None):
    """
    Get configuration value by dot-notation key.

    Args:
        key: Dot-separated key path (e.g., 'ai.moonshot.model')
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    keys = key.split(".")
    value = _config

    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default

    return value if value is not None else default


# ==================== API Keys from Environment Variables ====================
def _get_env_key(key: str, required: bool = True) -> Optional[str]:
    """
    Get API key from environment variable.

    Args:
        key: Environment variable name
        required: If True, raises error when key is not set

    Returns:
        API key value or None

    Raises:
        ValueError: If required key is not set
    """
    value = os.environ.get(key)
    if required and not value:
        raise ValueError(
            f"Required environment variable '{key}' is not set.\n"
            f"Please set it in Windows:\n"
            f"  setx {key} \"your_key_here\""
        )
    return value


# ==================== Public Configuration Constants ====================

# Application Settings
APP_NAME = get_config("app.name", "EnglishPod-KnowledgeBase")
APP_VERSION = get_config("app.version", "1.0.0")
DEBUG = get_config("app.debug", True)

# Database Settings
DATABASE_PATH = str(BASE_DIR / get_config("database.path", "./data/episodes.db"))
DATABASE_ECHO = get_config("database.echo", False)

# Obsidian Integration
OBSIDIAN_VAULT_PATH = get_config("obsidian.vault_path", "")
OBSIDIAN_NOTES_SUBDIR = get_config("obsidian.notes_subdir", "Episodes")
OBSIDIAN_MARKETING_SUBDIR = get_config("obsidian.marketing_subdir", "Marketing")

# ==================== AI Service Configuration ====================

# Moonshot Kimi (Primary AI Service)
MOONSHOT_API_KEY = _get_env_key("MOONSHOT_API_KEY", required=True)
MOONSHOT_BASE_URL = get_config("ai.moonshot.base_url", "https://api.moonshot.cn/v1")
MOONSHOT_MODEL = get_config("ai.moonshot.model", "kimi-k2-turbo-preview")

# Zhipu GLM (Secondary AI Service)
ZHIPU_API_KEY = _get_env_key("ZHIPU_API_KEY", required=True)
ZHIPU_BASE_URL = get_config("ai.zhipu.base_url", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_MODEL = get_config("ai.zhipu.model", "glm-4-plus")

# Gemini (Google)
GEMINI_API_KEY = _get_env_key("GEMINI_API_KEY", required=True)
GEMINI_MODEL = get_config("ai.gemini.model", "gemini-2.5-flash")

# Common AI Settings
AI_QUERY_TIMEOUT = get_config("ai.query_timeout", 60)
USE_AI_MOCK = get_config("ai.use_mock", False)

# ==================== Marketing Service LLM Configuration ====================
# Marketing service LLM provider selection (zhipu, moonshot, gemini)
# Modify in config.yaml to switch provider
MARKETING_LLM_PROVIDER = get_config("ai.marketing.provider", "zhipu")

# ==================== Audio Processing Configuration ====================

# Whisper Settings
WHISPER_MODEL = get_config("audio.whisper_model", "base")
WHISPER_DEVICE = get_config("audio.whisper_device", "cuda")
SEGMENT_DURATION = get_config("audio.segment_duration", 180)
DEFAULT_LANGUAGE = get_config("audio.default_language", "en-US")

# Audio Storage
AUDIO_STORAGE_PATH = str(BASE_DIR / get_config("audio.storage_path", "./data/audios"))
AUDIO_TEMP_DIR = str(BASE_DIR / get_config("audio.temp_dir", "./data/temp"))
MAX_FILE_SIZE = get_config("audio.max_file_size", 1024 * 1024 * 1024)

# ==================== Logging Configuration ====================
LOG_LEVEL = get_config("logging.level", "INFO")
LOG_FILE = str(BASE_DIR / get_config("logging.file", "./logs/app.log"))
LOG_ROTATION = get_config("logging.rotation", "10 MB")
LOG_RETENTION = get_config("logging.retention", "7 days")

# ==================== API Server Configuration ====================
API_HOST = get_config("api.host", "127.0.0.1")
API_PORT = get_config("api.port", 8000)
CORS_ORIGINS = get_config("api.cors_origins", ["http://localhost:5173"])

# ==================== HuggingFace Token ====================
# Required for WhisperX speaker diarization
HF_TOKEN = _get_env_key("HF_TOKEN", required=True)

# ==================== Notion Integration ====================
# API Key from environment variable (required for publishing content)
NOTION_API_KEY = _get_env_key("NOTION_API_KEY", required=False)

# Notion configuration from config.yaml
NOTION_PARENT_PAGE_ID = get_config("notion.parent_page_id", "")
NOTION_API_VERSION = get_config("notion.api_version", "2022-06-28")
NOTION_API_BASE_URL = get_config("notion.api_base_url", "https://api.notion.com/v1")


# ==================== Utility Functions ====================
def get_marketing_llm_config() -> dict:
    """
    Get marketing service LLM configuration based on provider setting.

    Returns:
        dict: Contains 'api_key', 'base_url', 'model' for the selected provider

    Raises:
        ValueError: If provider is not supported or API key is not set
    """
    provider = MARKETING_LLM_PROVIDER.lower()

    if provider == "zhipu":
        return {
            "api_key": ZHIPU_API_KEY,
            "base_url": ZHIPU_BASE_URL,
            "model": ZHIPU_MODEL
        }
    elif provider == "moonshot":
        return {
            "api_key": MOONSHOT_API_KEY,
            "base_url": MOONSHOT_BASE_URL,
            "model": MOONSHOT_MODEL
        }
    elif provider == "gemini":
        return {
            "api_key": GEMINI_API_KEY,
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "model": GEMINI_MODEL
        }
    else:
        raise ValueError(
            f"Unsupported marketing LLM provider: {provider}. "
            f"Supported providers: zhipu, moonshot, gemini"
        )


def reload_config():
    """Reload configuration from config.yaml file."""
    global _config
    _config = _load_yaml_config()


def print_config_summary():
    """Print a summary of current configuration (without exposing API keys)."""
    print(f"\n{'='*60}")
    print(f"Application: {APP_NAME} v{APP_VERSION}")
    print(f"Debug Mode: {DEBUG}")
    print(f"{'='*60}")
    print(f"\n[Database]")
    print(f"  Path: {DATABASE_PATH}")
    print(f"  Echo Queries: {DATABASE_ECHO}")

    print(f"\n[AI Services]")
    print(f"  Moonshot Model: {MOONSHOT_MODEL}")
    print(f"  Moonshot API Key: {'*** Set ***' if MOONSHOT_API_KEY else 'NOT SET'}")
    print(f"  Zhipu Model: {ZHIPU_MODEL}")
    print(f"  Zhipu API Key: {'*** Set ***' if ZHIPU_API_KEY else 'NOT SET'}")
    print(f"  Gemini Model: {GEMINI_MODEL}")
    print(f"  Gemini API Key: {'*** Set ***' if GEMINI_API_KEY else 'NOT SET'}")
    print(f"  Mock Mode: {USE_AI_MOCK}")

    print(f"\n[Audio Processing]")
    print(f"  Whisper Model: {WHISPER_MODEL}")
    print(f"  Whisper Device: {WHISPER_DEVICE}")
    print(f"  Storage Path: {AUDIO_STORAGE_PATH}")

    print(f"\n[API Server]")
    print(f"  Host: {API_HOST}")
    print(f"  Port: {API_PORT}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Test configuration loading
    print_config_summary()
