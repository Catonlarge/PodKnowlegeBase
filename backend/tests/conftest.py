"""
Pytest Configuration Fixtures

Sets up test environment variables before running tests.
"""
import os
import sys
import pytest


# Set test environment variables BEFORE importing app modules
# This ensures the config module can load successfully
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key_for_testing")
os.environ.setdefault("MOONSHOT_API_KEY", "test_moonshot_key_for_testing")
os.environ.setdefault("ZHIPU_API_KEY", "test_zhipu_key_for_testing")
os.environ.setdefault("HF_TOKEN", "test_hf_token_for_testing")


@pytest.fixture(scope="session")
def test_api_keys():
    """
    Provide test API keys for tests that need them.
    Returns a dictionary with all required keys.
    """
    return {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "test_gemini_key"),
        "MOONSHOT_API_KEY": os.environ.get("MOONSHOT_API_KEY", "test_moonshot_key"),
        "ZHIPU_API_KEY": os.environ.get("ZHIPU_API_KEY", "test_zhipu_key"),
        "HF_TOKEN": os.environ.get("HF_TOKEN", "test_hf_token"),
    }
