"""
Unit tests for AIService.

These tests use mocking to avoid actual API calls.
"""
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.ai.ai_service import AIService


class TestAIServiceInit:
    """Test AIService initialization."""

    @patch('app.services.ai.ai_service.OpenAI')
    @patch('app.services.ai.ai_service.genai')
    def test_init_moonshot_provider(self, mock_genai, mock_openai):
        """Given: MOONSHOT_API_KEY is set
        When: Initializing AIService with provider="moonshot"
        Then: Creates OpenAI client with Moonshot config
        """
        # Arrange
        with patch('app.services.ai.ai_service.MOONSHOT_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                # Act
                service = AIService(provider="moonshot")

                # Assert
                mock_openai.assert_called_once()
                assert service.provider == "moonshot"

    @patch('app.services.ai.ai_service.OpenAI')
    @patch('app.services.ai.ai_service.genai')
    def test_init_gemini_provider(self, mock_genai, mock_openai):
        """Given: GEMINI_API_KEY is set
        When: Initializing AIService with provider="gemini"
        Then: Creates Gemini client
        """
        # Arrange
        with patch('app.services.ai.ai_service.GEMINI_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                # Act
                service = AIService(provider="gemini")

                # Assert
                mock_genai.Client.assert_called_once()
                assert service.provider == "gemini"

    @patch('app.services.ai.ai_service.OpenAI')
    @patch('app.services.ai.ai_service.genai')
    def test_init_mock_mode(self, mock_genai, mock_openai):
        """Given: USE_AI_MOCK = True
        When: Initializing AIService
        Then: Sets use_mock=True without creating client
        """
        # Arrange
        with patch('app.services.ai.ai_service.USE_AI_MOCK', True):
            # Act
            service = AIService(provider="moonshot")

            # Assert
            assert service.use_mock is True
            mock_openai.assert_not_called()


class TestAServiceMockQuery:
    """Test mock query functionality."""

    def test_mock_query_word(self):
        """Given: USE_AI_MOCK=True and single word input
        When: Calling query
        Then: Returns mock word response
        """
        # Arrange
        with patch('app.services.ai.ai_service.USE_AI_MOCK', True):
            service = AIService(provider="moonshot")

            # Act
            result = service.query("hello")

            # Assert
            assert result["type"] == "word"
            assert "phonetic" in result["content"]
            assert "Mock" in result["content"]["definition"]

    def test_mock_query_phrase(self):
        """Given: USE_AI_MOCK=True and phrase input
        When: Calling query
        Then: Returns mock phrase response
        """
        # Arrange
        with patch('app.services.ai.ai_service.USE_AI_MOCK', True):
            service = AIService(provider="moonshot")

            # Act
            result = service.query("good morning")

            # Assert
            assert result["type"] == "phrase"
            assert "phonetic" in result["content"]
            assert "Mock" in result["content"]["definition"]

    def test_mock_query_sentence(self):
        """Given: USE_AI_MOCK=True and sentence input
        When: Calling query
        Then: Returns mock sentence response
        """
        # Arrange
        with patch('app.services.ai.ai_service.USE_AI_MOCK', True):
            service = AIService(provider="moonshot")

            # Act - Use more than 5 words to trigger sentence type
            result = service.query("Hello, how are you doing today?")

            # Assert
            assert result["type"] == "sentence"
            assert "translation" in result["content"]
            assert "Mock" in result["content"]["translation"]


class TestAServiceQuery:
    """Test actual query functionality with mocked clients."""

    @patch('app.services.ai.ai_service.OpenAI')
    @patch('app.services.ai.ai_service.genai')
    def test_query_moonshot_calls_openai(self, mock_genai, mock_openai):
        """Given: AIService with moonshot provider
        When: Calling query
        Then: Calls OpenAI chat.completions.create
        """
        # Arrange
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=Mock(content='{"type": "word", "content": {"phonetic": "/həˈloʊ/", "definition": "你好", "explanation": "问候语"}}'))]
        mock_client.chat.completions.create.return_value = mock_completion

        with patch('app.services.ai.ai_service.MOONSHOT_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                service = AIService(provider="moonshot")
                service.client = mock_client

                # Act
                result = service.query("hello")

                # Assert
                mock_client.chat.completions.create.assert_called_once()
                assert result["type"] == "word"

    @patch('app.services.ai.ai_service.genai')
    def test_query_gemini_calls_genai(self, mock_genai):
        """Given: AIService with gemini provider
        When: Calling query
        Then: Calls genai.Client.models.generate_content
        """
        # Arrange
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = '{"type": "word", "content": {"phonetic": "/həˈloʊ/", "definition": "你好", "explanation": "问候语"}}'
        mock_client.models.generate_content.return_value = mock_response

        with patch('app.services.ai.ai_service.GEMINI_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                service = AIService(provider="gemini")
                service.client = mock_client

                # Act
                result = service.query("hello")

                # Assert
                mock_client.models.generate_content.assert_called_once()
                assert result["type"] == "word"

    def test_query_raises_when_client_not_initialized(self):
        """Given: AIService without client (missing API key)
        When: Calling query
        Then: Raises ValueError
        """
        # Arrange
        with patch('app.services.ai.ai_service.MOONSHOT_API_KEY', None):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                service = AIService(provider="moonshot")

                # Act & Assert
                with pytest.raises(ValueError, match="AI Client not initialized"):
                    service.query("hello")


class TestAServiceJsonParsing:
    """Test JSON parsing in query response."""

    @patch('app.services.ai.ai_service.OpenAI')
    def test_query_strips_json_markdown_markers(self, mock_openai):
        """Given: AI response wrapped in markdown code blocks
        When: Calling query
        Then: Strips ```json and ``` markers
        """
        # Arrange
        mock_client = Mock()
        mock_completion = Mock()
        mock_response = '```json\n{"type": "word", "content": {"phonetic": "/test/", "definition": "测试"}}\n```'
        mock_completion.choices = [Mock(message=Mock(content=mock_response))]
        mock_client.chat.completions.create.return_value = mock_completion

        with patch('app.services.ai.ai_service.MOONSHOT_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                service = AIService(provider="moonshot")
                service.client = mock_client

                # Act
                result = service.query("test")

                # Assert
                assert result["type"] == "word"
                assert result["content"]["definition"] == "测试"

    @patch('app.services.ai.ai_service.OpenAI')
    def test_query_raises_on_invalid_json(self, mock_openai):
        """Given: AI response with invalid JSON
        When: Calling query
        Then: Raises ValueError
        """
        # Arrange
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=Mock(content='This is not JSON'))]
        mock_client.chat.completions.create.return_value = mock_completion

        with patch('app.services.ai.ai_service.MOONSHOT_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                service = AIService(provider="moonshot")
                service.client = mock_client

                # Act & Assert
                with pytest.raises(ValueError, match="Invalid JSON"):
                    service.query("test")

    @patch('app.services.ai.ai_service.OpenAI')
    def test_query_raises_on_missing_fields(self, mock_openai):
        """Given: AI response with valid JSON but missing required fields
        When: Calling query
        Then: Raises ValueError
        """
        # Arrange
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=Mock(content='{"wrong": "structure"}'))]
        mock_client.chat.completions.create.return_value = mock_completion

        with patch('app.services.ai.ai_service.MOONSHOT_API_KEY', 'test_key'):
            with patch('app.services.ai.ai_service.USE_AI_MOCK', False):
                service = AIService(provider="moonshot")
                service.client = mock_client

                # Act & Assert
                with pytest.raises(ValueError, match="Missing 'type' or 'content'"):
                    service.query("test")


class TestAServiceGetModelName:
    """Test _get_model_name method."""

    def test_get_model_name_returns_moonshot_model(self):
        """Given: AIService with provider="moonshot"
        When: Calling _get_model_name
        Then: Returns MOONSHOT_MODEL
        """
        # Arrange
        with patch('app.services.ai.ai_service.MOONSHOT_MODEL', 'moonshot-v1-8k'):
            service = AIService(provider="moonshot")

            # Act
            model = service._get_model_name()

            # Assert
            assert model == 'moonshot-v1-8k'

    def test_get_model_name_returns_gemini_model(self):
        """Given: AIService with provider="gemini"
        When: Calling _get_model_name
        Then: Returns GEMINI_MODEL
        """
        # Arrange
        with patch('app.services.ai.ai_service.GEMINI_MODEL', 'gemini-2.0-flash'):
            service = AIService(provider="gemini")

            # Act
            model = service._get_model_name()

            # Assert
            assert model == 'gemini-2.0-flash'

    def test_get_model_name_returns_zhipu_model(self):
        """Given: AIService with provider="zhipu"
        When: Calling _get_model_name
        Then: Returns ZHIPU_MODEL
        """
        # Arrange
        with patch('app.services.ai.ai_service.ZHIPU_MODEL', 'glm-4-plus'):
            service = AIService(provider="zhipu")

            # Act
            model = service._get_model_name()

            # Assert
            assert model == 'glm-4-plus'
