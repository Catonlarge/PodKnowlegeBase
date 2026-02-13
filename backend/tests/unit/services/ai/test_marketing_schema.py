"""
Unit Tests for Marketing Schema

This module tests the Pydantic schemas for marketing content generation.
Tests follow BDD naming convention and avoid conditional logic.
"""
import pytest
from pydantic import ValidationError

from app.services.ai.schemas.marketing_schema import (
    MarketingAngle,
    MultiAngleMarketingResponse
)


class TestMarketingAngle:
    """测试 MarketingAngle 模型"""

    def test_valid_marketing_angle_with_minimal_data_passes_validation(self):
        """
        Given: 包含最小有效数据的 MarketingAngle
        When: 创建模型实例
        Then: 验证通过，字段正确赋值
        """
        angle = MarketingAngle(
            angle_name="干货分享",
            title="🎯 实用学习方法",
            content="a" * 200,  # 最小长度
            hashtags=["#学习方法", "#干货", "#知识分享"]
        )

        assert angle.angle_name == "干货分享"
        assert angle.title == "🎯 实用学习方法"
        assert len(angle.content) == 200
        assert len(angle.hashtags) == 3

    def test_valid_marketing_angle_with_maximal_data_passes_validation(self):
        """
        Given: 包含最大有效数据的 MarketingAngle
        When: 创建模型实例
        Then: 验证通过
        """
        angle = MarketingAngle(
            angle_name="a" * 20,  # 最大长度
            title="a" * 30,  # 最大长度
            content="a" * 800,  # 最大长度
            hashtags=["#标签" + str(i) for i in range(10)]  # 最大数量
        )

        assert len(angle.angle_name) == 20
        assert len(angle.title) == 30
        assert len(angle.content) == 800
        assert len(angle.hashtags) == 10

    def test_marketing_angle_with_short_angle_name_raises_validation_error(self):
        """
        Given: angle_name 长度小于 2
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MarketingAngle(
                angle_name="a",
                title="标题",
                content="a" * 200,
                hashtags=["#标签"]
            )

    def test_marketing_angle_with_long_angle_name_raises_validation_error(self):
        """
        Given: angle_name 长度大于 20
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MarketingAngle(
                angle_name="a" * 21,
                title="标题",
                content="a" * 200,
                hashtags=["#标签"]
            )

    def test_marketing_angle_with_short_title_raises_validation_error(self):
        """
        Given: title 长度小于 5
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MarketingAngle(
                angle_name="角度",
                title="a" * 4,
                content="a" * 200,
                hashtags=["#标签"]
            )

    def test_marketing_angle_with_short_content_raises_validation_error(self):
        """
        Given: content 长度小于 200
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MarketingAngle(
                angle_name="角度",
                title="标题标题",
                content="a" * 199,
                hashtags=["#标签"]
            )

    def test_marketing_angle_with_long_content_gets_truncated(self):
        """
        Given: content 长度大于 800（LLM 常超限）
        When: 创建模型实例
        Then: 自动截断为 800 字符，验证通过
        """
        angle = MarketingAngle(
            angle_name="角度",
            title="标题标题1",
            content="a" * 801,
            hashtags=["#标签1", "#标签2", "#标签3"]
        )
        assert len(angle.content) == 800
        assert angle.content.endswith('...')

    def test_marketing_angle_with_few_hashtags_raises_validation_error(self):
        """
        Given: hashtags 数量小于 3
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MarketingAngle(
                angle_name="角度",
                title="标题标题",
                content="a" * 200,
                hashtags=["#标签1", "#标签2"]
            )

    def test_marketing_angle_with_many_hashtags_raises_validation_error(self):
        """
        Given: hashtags 数量大于 10
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MarketingAngle(
                angle_name="角度",
                title="标题标题",
                content="a" * 200,
                hashtags=["#标签" + str(i) for i in range(11)]
            )

    def test_marketing_angle_with_hashtag_not_starting_with_hash_raises_validation_error(self):
        """
        Given: hashtag 不以 # 开头
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="标签必须以#开头"):
            MarketingAngle(
                angle_name="角度",
                title="标题标题",
                content="a" * 200,
                hashtags=["#标签1", "标签2", "#标签3"]
            )

    def test_marketing_angle_with_long_hashtag_raises_validation_error(self):
        """
        Given: hashtag 长度大于 20
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="标签过长"):
            MarketingAngle(
                angle_name="角度",
                title="标题标题",
                content="a" * 200,
                hashtags=["#标签1", "#标签2", "#" + "a" * 20]
            )

    def test_marketing_angle_with_oversized_title_raises_validation_error(self):
        """
        Given: title 长度大于 60
        When: 创建模型实例
        Then: 抛出 ValidationError (不应被截断)
        """
        with pytest.raises(ValidationError) as exc_info:
            MarketingAngle(
                angle_name="角度",
                title="A" * 61,
                content="a" * 200,
                hashtags=["#标签1", "#标签2", "#标签3"]
            )
        assert "at most 60" in str(exc_info.value) or "60 characters" in str(exc_info.value)

    def test_marketing_angle_with_title_exactly_30_chars_passes(self):
        """
        Given: title 长度恰好为 30 字符
        When: 创建模型实例
        Then: 验证通过
        """
        title_30 = "A" * 30
        angle = MarketingAngle(
            angle_name="角度",
            title=title_30,
            content="a" * 200,
            hashtags=["#标签1", "#标签2", "#标签3"]
        )
        assert len(angle.title) == 30

    def test_marketing_angle_with_space_separated_hashtags_in_single_string_passes(self):
        """
        Given: LLM 返回 ["#a #b #c"] 单字符串（空格分隔）
        When: 创建模型实例
        Then: 解析为 3 个独立标签
        """
        angle = MarketingAngle(
            angle_name="角度",
            title="标题标题1",
            content="a" * 200,
            hashtags=["#AI安全 #Anthropic招聘 #超智能"]
        )
        assert angle.hashtags == ["#AI安全", "#Anthropic招聘", "#超智能"]

    def test_marketing_angle_with_concatenated_hashtags_no_separator_passes(self):
        """
        Given: LLM 返回 ["#a#b#c"] 无分隔符
        When: 创建模型实例
        Then: 通过 regex findall 解析为 3 个独立标签
        """
        angle = MarketingAngle(
            angle_name="角度",
            title="标题标题1",
            content="a" * 200,
            hashtags=["#标签1#标签2#标签3"]
        )
        assert angle.hashtags == ["#标签1", "#标签2", "#标签3"]


class TestMultiAngleMarketingResponse:
    """测试 MultiAngleMarketingResponse 模型"""

    def test_valid_response_with_exactly_three_angles_passes_validation(self):
        """
        Given: 包含正好 3 个角度的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = MultiAngleMarketingResponse(
            angles=[
                MarketingAngle(
                    angle_name="角度1",
                    title="标题标题1",
                    content="a" * 200,
                    hashtags=["#标签1", "#标签2", "#标签3"]
                ),
                MarketingAngle(
                    angle_name="角度2",
                    title="标题标题2",
                    content="b" * 200,
                    hashtags=["#标签4", "#标签5", "#标签6"]
                ),
                MarketingAngle(
                    angle_name="角度3",
                    title="标题标题3",
                    content="c" * 200,
                    hashtags=["#标签7", "#标签8", "#标签9"]
                ),
            ]
        )

        assert len(response.angles) == 3

    def test_response_with_less_than_three_angles_raises_validation_error(self):
        """
        Given: 包含少于 3 个角度的响应
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MultiAngleMarketingResponse(
                angles=[
                    MarketingAngle(
                        angle_name="角度1",
                        title="标题1",
                        content="a" * 200,
                        hashtags=["#标签1", "#标签2", "#标签3"]
                    ),
                    MarketingAngle(
                        angle_name="角度2",
                        title="标题2",
                        content="b" * 200,
                        hashtags=["#标签4", "#标签5", "#标签6"]
                    ),
                ]
            )

    def test_response_with_more_than_three_angles_raises_validation_error(self):
        """
        Given: 包含多于 3 个角度的响应
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            MultiAngleMarketingResponse(
                angles=[
                    MarketingAngle(
                        angle_name=f"角度{i}",
                        title=f"标题{i}",
                        content="a" * 200,
                        hashtags=["#标签1", "#标签2", "#标签3"]
                    )
                    for i in range(4)
                ]
            )

    def test_response_with_duplicate_angle_names_raises_validation_error(self):
        """
        Given: 包含重复角度名称的响应
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="角度名称必须唯一"):
            MultiAngleMarketingResponse(
                angles=[
                    MarketingAngle(
                        angle_name="重复角度",
                        title="标题标题1",
                        content="a" * 200,
                        hashtags=["#标签1", "#标签2", "#标签3"]
                    ),
                    MarketingAngle(
                        angle_name="重复角度",
                        title="标题标题2",
                        content="b" * 200,
                        hashtags=["#标签4", "#标签5", "#标签6"]
                    ),
                    MarketingAngle(
                        angle_name="角度3",
                        title="标题标题3",
                        content="c" * 200,
                        hashtags=["#标签7", "#标签8", "#标签9"]
                    ),
                ]
            )

    def test_response_json_serialization_deserialization(self):
        """
        Given: 有效的 MultiAngleMarketingResponse
        When: 序列化为 JSON 再反序列化
        Then: 数据保持一致
        """
        original = MultiAngleMarketingResponse(
            angles=[
                MarketingAngle(
                    angle_name="干货分享",
                    title="🎯 实用方法",
                    content="a" * 200,
                    hashtags=["#干货", "#分享", "#学习"]
                ),
                MarketingAngle(
                    angle_name="情感共鸣",
                    title="💭 深度思考",
                    content="b" * 200,
                    hashtags=["#情感", "#共鸣", "#成长"]
                ),
                MarketingAngle(
                    angle_name="趣味科普",
                    title="🔥 冷知识",
                    content="c" * 200,
                    hashtags=["#科普", "#知识", "#趣味"]
                ),
            ]
        )

        # 序列化
        json_str = original.model_dump_json()

        # 反序列化
        restored = MultiAngleMarketingResponse.model_validate_json(json_str)

        assert len(restored.angles) == 3
        assert restored.angles[0].angle_name == "干货分享"
        assert restored.angles[1].angle_name == "情感共鸣"
        assert restored.angles[2].angle_name == "趣味科普"
