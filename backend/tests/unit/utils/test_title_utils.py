"""
单元测试：title_utils 跨平台标题清理工具
"""

import pytest

from app.utils.title_utils import sanitize_title, DISPLAY_TITLE_MAX_LENGTH, DISPLAY_TITLE_ELLIPSIS


class TestSanitizeTitle:
    """测试 sanitize_title 函数"""

    def test_empty_string_returns_empty(self):
        """
        Given: 空字符串
        When: 调用 sanitize_title
        Then: 返回空字符串
        """
        # Arrange & Act
        result = sanitize_title("")

        # Assert
        assert result == ""

    def test_none_returns_empty(self):
        """
        Given: None 值
        When: 调用 sanitize_title
        Then: 返回空字符串
        """
        # Arrange & Act
        result = sanitize_title(None)

        # Assert
        assert result == ""

    def test_normal_title_unchanged(self):
        """
        Given: 正常标题
        When: 调用 sanitize_title
        Then: 返回原始标题
        """
        # Arrange
        title = "Business English Conversation"

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == title

    def test_newlines_replaced_with_space(self):
        """
        Given: 包含换行符的标题
        When: 调用 sanitize_title
        Then: 换行符被替换为空格
        """
        # Arrange
        title = "Multi\nLine\r\nTitle"

        # Act
        result = sanitize_title(title)

        # Assert
        assert "\n" not in result
        assert "\r" not in result
        assert result == "Multi Line Title"

    def test_leading_trailing_whitespace_stripped(self):
        """
        Given: 包含首尾空白的标题
        When: 调用 sanitize_title
        Then: 首尾空白被移除
        """
        # Arrange
        title = "  Hello World  "

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == "Hello World"

    def test_multiple_spaces_collapsed(self):
        """
        Given: 包含多个连续空格的标题
        When: 调用 sanitize_title
        Then: 多个空格合并为一个
        """
        # Arrange
        title = "Hello    World   Test"

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == "Hello World Test"

    def test_long_title_truncated(self):
        """
        Given: 超长标题（超过 DISPLAY_TITLE_MAX_LENGTH）
        When: 调用 sanitize_title
        Then: 标题被截断并添加省略号
        """
        # Arrange
        long_title = "A" * 150  # 超过 100 字符

        # Act
        result = sanitize_title(long_title)

        # Assert
        expected_length = DISPLAY_TITLE_MAX_LENGTH
        assert len(result) == expected_length
        assert result.endswith(DISPLAY_TITLE_ELLIPSIS)
        assert "..." in result
        assert result.count("A") == DISPLAY_TITLE_MAX_LENGTH - len(DISPLAY_TITLE_ELLIPSIS)

    def test_custom_max_length(self):
        """
        Given: 自定义最大长度
        When: 调用 sanitize_title
        Then: 使用自定义长度进行截断
        """
        # Arrange
        title = "A" * 50

        # Act
        result = sanitize_title(title, max_length=20)

        # Assert
        assert len(result) == 20
        assert result.endswith(DISPLAY_TITLE_ELLIPSIS)

    def test_title_with_markdown_special_chars_preserved(self):
        """
        Given: 包含 Markdown 特殊字符的标题
        When: 调用 sanitize_title
        Then: 特殊字符被保留（由各平台渲染时处理转义）
        """
        # Arrange
        title = "# Episode: What's [New] | 2024"

        # Act
        result = sanitize_title(title)

        # Assert
        assert "# Episode: What's [New] | 2024" in result

    def test_title_exactly_at_max_length_not_truncated(self):
        """
        Given: 标题长度正好等于最大长度
        When: 调用 sanitize_title
        Then: 标题不被截断
        """
        # Arrange
        title = "A" * DISPLAY_TITLE_MAX_LENGTH

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == title
        assert len(result) == DISPLAY_TITLE_MAX_LENGTH
        assert not result.endswith(DISPLAY_TITLE_ELLIPSIS)

    def test_title_one_char_over_max_length_truncated(self):
        """
        Given: 标题长度超过最大长度 1 个字符
        When: 调用 sanitize_title
        Then: 标题被截断并添加省略号
        """
        # Arrange
        title = "A" * (DISPLAY_TITLE_MAX_LENGTH + 1)

        # Act
        result = sanitize_title(title)

        # Assert
        assert len(result) == DISPLAY_TITLE_MAX_LENGTH
        assert result.endswith(DISPLAY_TITLE_ELLIPSIS)
        assert result.count("A") == DISPLAY_TITLE_MAX_LENGTH - len(DISPLAY_TITLE_ELLIPSIS)

    def test_chinese_title_preserved(self):
        """
        Given: 中文标题
        When: 调用 sanitize_title
        Then: 中文字符被正确保留
        """
        # Arrange
        title = "商务英语对话学习"

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == title

    def test_mixed_language_title_preserved(self):
        """
        Given: 中英文混合标题
        When: 调用 sanitize_title
        Then: 所有字符被正确保留
        """
        # Arrange
        title = "EnglishPod 商务英语 #001"

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == title

    def test_tabs_converted_to_spaces(self):
        """
        Given: 包含制表符的标题
        When: 调用 sanitize_title
        Then: 制表符被转换为空格
        """
        # Arrange
        title = "Hello\tWorld\tTest"

        # Act
        result = sanitize_title(title)

        # Assert
        assert "\t" not in result
        assert result == "Hello World Test"

    def test_title_with_only_whitespace_returns_empty(self):
        """
        Given: 只包含空白的标题
        When: 调用 sanitize_title
        Then: 返回空字符串
        """
        # Arrange
        title = "   \n\t   "

        # Act
        result = sanitize_title(title)

        # Assert
        assert result == ""
