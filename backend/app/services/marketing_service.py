"""
Marketing Service - 小红书风格营销文案生成服务

负责为 Episode 生成小红书风格的营销文案，包括：
1. 金句提取
2. 标题生成
3. 话题标签生成
4. 完整文案生成
5. 文案持久化
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from sqlalchemy.orm import Session
from openai import OpenAI

from app.models import Episode, MarketingPost, TranscriptCue, AudioSegment
from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL, AI_QUERY_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass
class MarketingCopy:
    """营销文案结果"""
    title: str
    content: str
    hashtags: List[str]
    key_quotes: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class MarketingService:
    """
    营销文案生成服务 (小红书风格)

    负责：
    1. 为 Episode 生成小红书风格营销文案
    2. 提取核心观点和金句
    3. 生成吸引人的标题和话题标签
    """

    def __init__(self, db: Session, llm_service: Optional[Any] = None):
        """
        初始化服务

        Args:
            db: 数据库会话
            llm_service: LLM 服务（用于文案生成）
        """
        self.db = db
        self.llm_service = llm_service

    # ========================================================================
    # 金句提取
    # ========================================================================

    def extract_key_quotes(
        self,
        episode_id: int,
        max_quotes: int = 5
    ) -> List[str]:
        """
        提取关键金句

        Args:
            episode_id: Episode ID
            max_quotes: 最多提取金句数量

        Returns:
            List[str]: 金句列表

        Raises:
            ValueError: Episode 不存在
        """
        logger.debug(f"提取金句: episode_id={episode_id}, max_quotes={max_quotes}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        quotes = []

        # 从 ai_summary 中提取句子
        if episode.ai_summary:
            # 按句号、问号、感叹号分割
            sentences = re.split(r'[。！？.!?]', episode.ai_summary)
            # 过滤空句子，但允许较短的句子（降低阈值从10到2）
            sentences = [s.strip() for s in sentences if len(s.strip()) > 2]
            quotes.extend(sentences[:max_quotes])

        # 如果摘要中的句子不够，从 TranscriptCue 中提取
        if len(quotes) < max_quotes:
            remaining = max_quotes - len(quotes)
            cues = self.db.query(TranscriptCue).join(
                AudioSegment, TranscriptCue.segment_id == AudioSegment.id
            ).filter(
                AudioSegment.episode_id == episode_id
            ).order_by(TranscriptCue.start_time).limit(remaining * 2).all()

            # 选择较长的字幕作为金句
            for cue in cues:
                if len(cue.text) > 5 and len(quotes) < max_quotes:
                    quotes.append(cue.text)

        return quotes[:max_quotes]

    # ========================================================================
    # 标题生成
    # ========================================================================

    def generate_titles(
        self,
        episode_id: int,
        count: int = 5
    ) -> List[str]:
        """
        生成吸引人的标题

        Args:
            episode_id: Episode ID
            count: 生成标题数量

        Returns:
            List[str]: 标题列表

        Raises:
            ValueError: Episode 不存在
        """
        logger.debug(f"生成标题: episode_id={episode_id}, count={count}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 调用 LLM 生成标题
        return self._call_llm_for_titles(episode, count)

    def _call_llm_for_titles(self, episode: Episode, count: int) -> List[str]:
        """
        调用 LLM 生成标题

        Args:
            episode: Episode 对象
            count: 生成数量

        Returns:
            List[str]: 标题列表
        """
        # 如果有配置 API Key，使用真实 AI 服务
        if MOONSHOT_API_KEY and MOONSHOT_API_KEY != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=MOONSHOT_API_KEY,
                    base_url=MOONSHOT_BASE_URL
                )

                system_prompt = """你是一位专业的小红书营销文案专家。
请根据播客内容生成吸引人的小红书标题。

要求：
1. 生成 {count} 个不同的标题
2. 每个标题要包含 emoji 表情
3. 标题要吸引眼球，符合小红书风格
4. 标题长度控制在 30 字以内
5. 直接返回标题列表，每行一个，不要有其他内容

输出格式：
标题1
标题2
标题3
...""".format(count=count)

                user_prompt = f"""播客标题：{episode.title}
播客摘要：{episode.ai_summary or '暂无摘要'}

请根据以上内容生成 {count} 个小红书标题："""

                executor = ThreadPoolExecutor(max_workers=1)

                def call_ai():
                    completion = client.chat.completions.create(
                        model=MOONSHOT_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.8,
                    )
                    return completion.choices[0].message.content

                try:
                    future = executor.submit(call_ai)
                    response_text = future.result(timeout=AI_QUERY_TIMEOUT)
                    executor.shutdown(wait=False)

                    # 解析返回的标题列表
                    titles = [line.strip() for line in response_text.split('\n') if line.strip()]
                    return titles[:count]

                except FutureTimeoutError:
                    logger.error("AI 标题生成超时，使用备用方案")
                    executor.shutdown(wait=False)
                except Exception as e:
                    logger.error(f"AI 标题生成失败: {e}，使用备用方案")

            except Exception as e:
                logger.error(f"AI 标题生成初始化失败: {e}，使用备用方案")

        # 备用方案：返回模拟数据
        titles = [
            f"🎯 {episode.title}",
            f"💡 关于{episode.title}的思考",
            f"🔥 {episode.title}深度解析",
            f"✨ {episode.title}分享",
            f"📚 {episode.title}干货"
        ]
        return titles[:count]

    # ========================================================================
    # 话题标签生成
    # ========================================================================

    def generate_hashtags(
        self,
        episode_id: int,
        max_tags: int = 10
    ) -> List[str]:
        """
        生成话题标签

        Args:
            episode_id: Episode ID
            max_tags: 最多生成标签数量

        Returns:
            List[str]: 话题标签列表（带 # 前缀）

        Raises:
            ValueError: Episode 不存在
        """
        logger.debug(f"生成标签: episode_id={episode_id}, max_tags={max_tags}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 调用 LLM 生成标签
        return self._call_llm_for_hashtags(episode, max_tags)

    def _call_llm_for_hashtags(self, episode: Episode, max_tags: int) -> List[str]:
        """
        调用 LLM 生成标签

        Args:
            episode: Episode 对象
            max_tags: 最多生成数量

        Returns:
            List[str]: 标签列表
        """
        # 如果有配置 API Key，使用真实 AI 服务
        if MOONSHOT_API_KEY and MOONSHOT_API_KEY != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=MOONSHOT_API_KEY,
                    base_url=MOONSHOT_BASE_URL
                )

                system_prompt = f"""你是一位专业的小红书营销文案专家。
请根据播客内容生成相关的话题标签。

要求：
1. 生成 {max_tags} 个相关标签
2. 每个标签必须以 # 开头
3. 标签要与内容相关，符合小红书热门话题
4. 标签用空格分隔，不要有换行
5. 不要有其他解释文字

输出格式：
#标签1 #标签2 #标签3 #标签4 #标签5 ..."""

                user_prompt = f"""播客标题：{episode.title}
播客摘要：{episode.ai_summary or '暂无摘要'}

请根据以上内容生成 {max_tags} 个相关标签："""

                executor = ThreadPoolExecutor(max_workers=1)

                def call_ai():
                    completion = client.chat.completions.create(
                        model=MOONSHOT_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.7,
                    )
                    return completion.choices[0].message.content

                try:
                    future = executor.submit(call_ai)
                    response_text = future.result(timeout=AI_QUERY_TIMEOUT)
                    executor.shutdown(wait=False)

                    # 解析返回的标签列表
                    # 查找所有以 # 开头的标签
                    hashtags = re.findall(r'#[\w\u4e00-\u9fff]+', response_text)
                    return hashtags[:max_tags]

                except FutureTimeoutError:
                    logger.error("AI 标签生成超时，使用备用方案")
                    executor.shutdown(wait=False)
                except Exception as e:
                    logger.error(f"AI 标签生成失败: {e}，使用备用方案")

            except Exception as e:
                logger.error(f"AI 标签生成初始化失败: {e}，使用备用方案")

        # 备用方案：返回通用标签
        tags = [
            "#学习干货",
            "#知识分享",
            "#深度思考",
            "#内容输出",
            "#个人成长",
            "#技能提升",
            "#认知升级",
            "#学习方法",
            "#干货收藏",
            "#知识管理"
        ]
        return tags[:max_tags]

    # ========================================================================
    # 小红书文案生成
    # ========================================================================

    def generate_xiaohongshu_copy(
        self,
        episode_id: int,
        language: str = "zh"
    ) -> MarketingCopy:
        """
        生成小红书风格文案

        Args:
            episode_id: Episode ID
            language: 语言代码

        Returns:
            MarketingCopy: 生成的文案对象

        Raises:
            ValueError: Episode 不存在或数据不完整
        """
        logger.info(f"生成小红书文案: episode_id={episode_id}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 1. 提取金句
        key_quotes = self.extract_key_quotes(episode_id, max_quotes=3)

        # 2. 生成标题
        titles = self.generate_titles(episode_id, count=1)
        title = titles[0] if titles else episode.title

        # 3. 生成标签
        hashtags = self.generate_hashtags(episode_id, max_tags=5)

        # 4. 生成正文内容
        content = self._call_llm_for_xiaohongshu_content(episode, key_quotes)

        return MarketingCopy(
            title=title,
            content=content,
            hashtags=hashtags,
            key_quotes=key_quotes,
            metadata={
                "episode_id": episode_id,
                "language": language,
                "platform": "xiaohongshu"
            }
        )

    def _call_llm_for_xiaohongshu_content(
        self,
        episode: Episode,
        key_quotes: List[str]
    ) -> str:
        """
        调用 LLM 生成小红书风格正文

        Args:
            episode: Episode 对象
            key_quotes: 金句列表

        Returns:
            str: 小红书风格正文
        """
        # 如果有配置 API Key，使用真实 AI 服务
        if MOONSHOT_API_KEY and MOONSHOT_API_KEY != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=MOONSHOT_API_KEY,
                    base_url=MOONSHOT_BASE_URL
                )

                # 格式化金句引用
                quotes_text = ""
                if key_quotes:
                    quotes_text = "\n".join([f"• {quote[:100]}..." if len(quote) > 100 else f"• {quote}" for quote in key_quotes[:3]])

                system_prompt = """你是一位专业的小红书营销文案专家。
请根据播客内容生成小红书风格的文章正文。

要求：
1. 使用"宝子们"开头，亲切自然的语气
2. 使用大量 emoji 表情（✅、💡、🔥、✨等）
3. 内容分段清晰，使用项目符号
4. 突出"干货"和"价值"
5. 结尾要有 CTA（点赞收藏关注）
6. 字数控制在 300-500 字
7. 不要使用 Markdown 格式（不要有 ## 标题等）

风格参考：
宝子们！今天分享一个超赞的发现！

✅ 核心观点1
详细说明...

✅ 核心观点2
详细说明...

💡 重点提示
金句引用...

真的太有用了！强烈推荐大家也去了解一下！

点赞收藏关注我，不错过更多干货！"""

                user_prompt = f"""播客标题：{episode.title}
播客摘要：{episode.ai_summary or '暂无摘要'}

核心金句：
{quotes_text if quotes_text else '暂无'}

请根据以上内容生成小红书风格的文章正文："""

                executor = ThreadPoolExecutor(max_workers=1)

                def call_ai():
                    completion = client.chat.completions.create(
                        model=MOONSHOT_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.8,
                    )
                    return completion.choices[0].message.content

                try:
                    future = executor.submit(call_ai)
                    response_text = future.result(timeout=AI_QUERY_TIMEOUT)
                    executor.shutdown(wait=False)
                    return response_text.strip()

                except FutureTimeoutError:
                    logger.error("AI 内容生成超时，使用备用方案")
                    executor.shutdown(wait=False)
                except Exception as e:
                    logger.error(f"AI 内容生成失败: {e}，使用备用方案")

            except Exception as e:
                logger.error(f"AI 内容生成初始化失败: {e}，使用备用方案")

        # 备用方案：返回模拟数据
        content = f"""宝子们！今天分享一个超赞的发现！

关于 {episode.title}，我有一些心得想和大家分享...

✅ 核心观点1
这个话题真的很有意思，让我深思了很久。

✅ 核心观点2
特别是在实际应用中，你会发现很多细节值得注意。

💡 重点提示
{key_quotes[0] if key_quotes else '记得多思考，多实践！'}

真的太有用了！强烈推荐大家也去了解一下！

点赞收藏关注我，不错过更多干货！"""

        return content

    # ========================================================================
    # 文案持久化
    # ========================================================================

    def save_marketing_copy(
        self,
        episode_id: int,
        copy: MarketingCopy,
        platform: str = "xhs",
        angle_tag: str = "default"
    ) -> MarketingPost:
        """
        保存营销文案到数据库

        Args:
            episode_id: Episode ID
            copy: 营销文案对象
            platform: 平台标识
            angle_tag: 策略标签

        Returns:
            MarketingPost: 创建的数据库记录
        """
        logger.info(f"保存营销文案: episode_id={episode_id}, platform={platform}")

        post = MarketingPost(
            episode_id=episode_id,
            platform=platform,
            angle_tag=angle_tag,
            title=copy.title,
            content=copy.content,
            status="pending"
        )

        self.db.add(post)
        self.db.flush()

        logger.info(f"营销文案已保存: id={post.id}")
        return post

    def load_marketing_copy(self, post_id: int) -> Optional[MarketingPost]:
        """
        从数据库加载营销文案

        Args:
            post_id: 文案 ID

        Returns:
            Optional[MarketingPost]: 文案对象，不存在返回 None
        """
        return self.db.query(MarketingPost).filter(MarketingPost.id == post_id).first()
