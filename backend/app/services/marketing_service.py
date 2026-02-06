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
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from loguru import logger
from sqlalchemy.orm import Session
from openai import OpenAI

from app.models import Episode, MarketingPost, TranscriptCue, AudioSegment, Chapter, Translation
from app.config import get_marketing_llm_config, AI_QUERY_TIMEOUT


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
            llm_service: LLM 服务（用于文案生成，已废弃，保留兼容性）
        """
        self.db = db
        self.llm_service = llm_service
        # 获取营销服务专用的 LLM 配置（支持从 config.yaml 动态切换 provider）
        self._llm_config = get_marketing_llm_config()

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
        # 使用营销服务专用的 LLM 配置（支持动态切换 provider）
        api_key = self._llm_config["api_key"]
        if api_key and api_key != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url=self._llm_config["base_url"]
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
                        model=self._llm_config["model"],
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
        # 使用营销服务专用的 LLM 配置（支持动态切换 provider）
        api_key = self._llm_config["api_key"]
        if api_key and api_key != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url=self._llm_config["base_url"]
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
                        model=self._llm_config["model"],
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

    def _get_full_transcripts(self, episode_id: int, language_code: str = "zh") -> str:
        """
        获取 Episode 的完整字幕内容（英文+中文翻译）

        Args:
            episode_id: Episode ID
            language_code: 翻译语言代码

        Returns:
            str: 完整字幕文本
        """
        # 获取所有字幕，按时间排序
        cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).order_by(TranscriptCue.start_time).all()

        if not cues:
            return "暂无字幕内容"

        # 构建字幕文本
        transcripts_parts = []
        for cue in cues:
            # 获取翻译
            translation = cue.get_translation(language_code)
            translation_text = translation if translation else ""

            # 格式化：[时间] 说话人: 英文内容 -> 中文翻译
            part = f"[{cue.start_time:.1f}s] {cue.speaker}: {cue.text}"
            if translation_text:
                part += f"\n翻译: {translation_text}"
            transcripts_parts.append(part)

        return "\n\n".join(transcripts_parts)

    def generate_xiaohongshu_copy(
        self,
        episode_id: int,
        language: str = "zh"
    ) -> MarketingCopy:
        """
        生成小红书风格文案（单版本，已废弃，请使用 generate_xiaohongshu_copy_multi_angle）

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

    def generate_xiaohongshu_copy_multi_angle(
        self,
        episode_id: int,
        language: str = "zh"
    ) -> List[MarketingCopy]:
        """
        生成小红书风格文案（多版本 - 3个不同角度）

        LLM 自己决定角度，一次调用生成3个版本，并传递完整字幕内容

        Args:
            episode_id: Episode ID
            language: 语言代码

        Returns:
            List[MarketingCopy]: 3个不同角度的文案对象

        Raises:
            ValueError: Episode 不存在或数据不完整
        """
        logger.info(f"生成小红书多角度文案: episode_id={episode_id}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 1. 提取金句
        key_quotes = self.extract_key_quotes(episode_id, max_quotes=3)

        # 2. 获取完整字幕内容
        transcripts_text = self._get_full_transcripts(episode_id, language)

        # 3. 一次调用生成3个角度的文案
        angle_copies = self._call_llm_for_multi_angle_content(
            episode, key_quotes, transcripts_text
        )

        return angle_copies

    def _call_llm_for_multi_angle_content(
        self,
        episode: Episode,
        key_quotes: List[str],
        transcripts_text: str
    ) -> List[MarketingCopy]:
        """
        调用 LLM 生成3个不同角度的小红书风格文案

        Args:
            episode: Episode 对象
            key_quotes: 金句列表
            transcripts_text: 完整字幕内容

        Returns:
            List[MarketingCopy]: 3个不同角度的文案对象
        """
        # 使用营销服务专用的 LLM 配置
        api_key = self._llm_config["api_key"]
        if api_key and api_key != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url=self._llm_config["base_url"]
                )

                # 格式化金句引用
                quotes_text = ""
                if key_quotes:
                    quotes_text = "\n".join([f"• {quote[:100]}..." if len(quote) > 100 else f"• {quote}" for quote in key_quotes[:3]])

                system_prompt = """你是一位专业的小红书营销文案专家。
请根据播客完整字幕内容，生成 3 个不同角度的营销文案版本。

【核心原则】每个角度都必须基于完整的字幕内容，而不是按章节拆分】

【重要约束】
1. 必须严格基于字幕内容生成，不得编造字幕中没有的信息
2. 只能提炼、重组、润色字幕中的内容
3. 每个角度都从完整内容出发，选择不同的切入点，而不是只选取部分章节
4. 所有数据、案例、观点必须来自字幕原文
5. 【禁止按章节拆分角度】比如不能是"角度1讲第一章，角度2讲第二章"，这是错误的

【正确的角度示例】
- 如果内容包含法律、写作、心理三个方面，则三个角度可以是：
  * 角度1（产品向）：产品经理是怎么思考的
  * 角度2（个人学习向）：怎么用AI越狱
  * 角度3（职场向/商业向）：怎么拓展第二产品
  每个角度都引用完整内容中的相关部分，而不是只截取某一章

【任务】
分析上述字幕内容，定义 3 个不同的内容角度，然后为每个角度生成：
1. 角度名称（4-8字，简洁明了）
2. 该角度对应的标题（包含emoji，30字以内）
3. 该角度的正文内容（300-500字）
4. 该角度的标签（5个，以#开头）

【正文要求】
- 开头简洁有力，直接点题
- 使用适量 emoji 表情点缀
- 内容分段清晰，使用项目符号
- 突出"干货"和"价值"
- 结尾要有 CTA（点赞收藏关注）
- 不要使用 Markdown 格式（不要有 ## 标题等）

【输出格式】（请严格按此格式输出）
---
【角度1】<角度名称>
标题：<标题>
正文：
<正文内容>
标签：<标签1> <标签2> <标签3> <标签4> <标签5>

---
【角度2】<角度名称>
标题：<标题>
正文：
<正文内容>
标签：<标签1> <标签2> <标签3> <标签4> <标签5>

---
【角度3】<角度名称>
标题：<标题>
正文：
<正文内容>
标签：<标签1> <标签2> <标签3> <标签4> <标签5>

---

请生成 3 个不同角度的营销文案："""

                # DEBUG: 验证字幕内容是否完整传递
                logger.info(f"Episode {episode.id} 字幕统计: 总行数={len(transcripts_text.split(chr(10)))}, 总字符数={len(transcripts_text)}")
                logger.info(f"字幕内容前300字符预览: {transcripts_text[:300]}...")

                user_prompt = f"""播客标题：{episode.title}
播客摘要：{episode.ai_summary or '暂无摘要'}

核心金句：
{quotes_text if quotes_text else '暂无'}

完整字幕内容：
{transcripts_text}

请根据以上完整字幕内容生成 3 个不同角度的营销文案："""

                logger.info(f"发送给 LLM 的 prompt 总长度: {len(system_prompt) + len(user_prompt)} 字符")

                executor = ThreadPoolExecutor(max_workers=1)

                def call_ai():
                    completion = client.chat.completions.create(
                        model=self._llm_config["model"],
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.8,
                    )
                    return completion.choices[0].message.content

                try:
                    future = executor.submit(call_ai)
                    response_text = future.result(timeout=AI_QUERY_TIMEOUT * 2)  # 增加超时时间
                    executor.shutdown(wait=False)

                    # 解析3个角度的文案
                    return self._parse_multi_angle_response(response_text, episode.id)

                except FutureTimeoutError:
                    logger.error("AI 多角度文案生成超时，使用备用方案")
                    executor.shutdown(wait=False)
                except Exception as e:
                    logger.error(f"AI 多角度文案生成失败: {e}，使用备用方案")

            except Exception as e:
                logger.error(f"AI 多角度文案生成初始化失败: {e}，使用备用方案")

        # 备用方案：返回3个通用版本
        return self._generate_fallback_multi_angle_copy(episode, key_quotes)

    def _parse_multi_angle_response(self, response_text: str, episode_id: int) -> List[MarketingCopy]:
        """
        解析 LLM 返回的多角度文案响应

        Args:
            response_text: LLM 返回的原始文本
            episode_id: Episode ID

        Returns:
            List[MarketingCopy]: 解析后的文案对象列表
        """
        angle_copies = []

        # DEBUG: 输出原始响应
        logger.debug(f"LLM 原始响应长度: {len(response_text)}")
        logger.debug(f"LLM 原始响应前500字符: {response_text[:500]}")

        # 按分隔符分割（支持多种格式：---, —, === 等）
        # 先尝试使用不同的分隔符
        for separator_pattern in [r'---+', r'—{3,}', r'===+', r'\n---\n', r'\n—{3,}\n']:
            angle_blocks = re.split(separator_pattern, response_text)
            valid_blocks = [b for b in angle_blocks if b.strip() and self._has_angle_marker(b)]
            logger.debug(f"分隔符 {separator_pattern}: 总块数={len(angle_blocks)}, 有效块数={len(valid_blocks)}")
            if len(valid_blocks) >= 2:
                logger.debug(f"使用分隔符: {separator_pattern}")
                break

        for block in angle_blocks:
            if not block.strip():
                continue

            # 提取角度名称
            angle_match = re.search(r'【角度[123]】(.+?)(?:\n|$)', block)
            if not angle_match:
                angle_match = re.search(r'角度[123][:：](.+?)(?:\n|$)', block)

            angle_name = angle_match.group(1).strip() if angle_match else f"角度{len(angle_copies) + 1}"

            # 提取标题
            title_match = re.search(r'标题[：:](.+?)(?:\n|$)', block)
            title = title_match.group(1).strip() if title_match else f"文案{len(angle_copies) + 1}"

            # 提取标签
            tags_match = re.search(r'标签[：:](.+?)(?:\n|$)', block)
            hashtags = []
            if tags_match:
                hashtags = re.findall(r'#[\w\u4e00-\u9fff]+', tags_match.group(1))
            if not hashtags:
                hashtags = ["#播客推荐", "#内容分享"]

            # 提取正文
            content_match = re.search(r'正文[：:]\s*\n(.+)', block, re.DOTALL)
            if content_match:
                content = content_match.group(1).strip()
            else:
                # 如果没有"正文："标记，尝试提取其他内容
                lines = block.split('\n')
                content_lines = []
                for line in lines:
                    line = line.strip()
                    # 跳过角度名、标题、标签行
                    if any(line.startswith(prefix) for prefix in ['【角度', '角度', '标题', '标签']):
                        continue
                    if line:
                        content_lines.append(line)
                content = '\n'.join(content_lines).strip() if content_lines else "内容生成中..."

            # 移除可能的 trailing separators
            content = re.split(r'[\n—-]{3,}\s*\n*', content)[0].strip()

            # 只有当内容有效时才添加
            if content and len(content) > 10 and content != "内容生成中...":
                angle_copies.append(MarketingCopy(
                    title=title,
                    content=content,
                    hashtags=hashtags,
                    key_quotes=[],
                    metadata={
                        "episode_id": episode_id,
                        "platform": "xiaohongshu",
                        "angle_tag": angle_name
                    }
                ))

        # 确保有3个版本
        while len(angle_copies) < 3:
            angle_copies.append(MarketingCopy(
                title=f"🎧 文案版本{len(angle_copies) + 1}",
                content="感谢观看，欢迎点赞收藏关注！",
                hashtags=["#播客推荐", "#内容分享"],
                key_quotes=[],
                metadata={
                    "episode_id": episode_id,
                    "platform": "xiaohongshu",
                    "angle_tag": f"版本{len(angle_copies) + 1}"
                }
            ))

        return angle_copies[:3]

    def _has_angle_marker(self, text: str) -> bool:
        """检查文本是否包含角度标记"""
        return bool(re.search(r'【角度[123]】|角度[123][:：]', text))

    def _generate_fallback_multi_angle_copy(
        self,
        episode: Episode,
        key_quotes: List[str]
    ) -> List[MarketingCopy]:
        """
        生成备用多角度文案（当 LLM 调用失败时）

        Args:
            episode: Episode 对象
            key_quotes: 金句列表

        Returns:
            List[MarketingCopy]: 3个备用文案对象
        """
        fallback_angles = [
            ("干货分享", f"分享一个关于{episode.title}的实用方法，亲测有效！\n\n✅ 核心观点\n这个话题真的很有意思，让我深思了很久。\n\n✅ 实践建议\n特别是在实际应用中，你会发现很多细节值得注意。\n\n💡 重点提示\n{key_quotes[0] if key_quotes else '记得多思考，多实践！'}\n\n建议收藏起来慢慢看，有问题评论区见！"),
            ("情感共鸣", f"听完这期{episode.title}，我感触很深...\n\n有时候我们需要的不是答案，而是提出问题的勇气。\n\n{key_quotes[1] if len(key_quotes) > 1 else key_quotes[0] if key_quotes else '分享给你，希望能给你一些启发'}\n\n点赞收藏关注，分享更多暖心内容！"),
            ("趣味科普", f"你知道吗？{episode.title}还有这些冷知识！\n\n🔥 趣味事实1\n可能会让你大吃一惊！\n\n🔥 趣味事实2\n原来还可以这样理解！\n\n评论区告诉我你还想知道什么？\n点赞收藏关注，下期更精彩！")
        ]

        copies = []
        for angle_name, content in fallback_angles:
            copies.append(MarketingCopy(
                title=f"🎧 {episode.title}",
                content=content,
                hashtags=["#播客推荐", "#内容分享"],
                key_quotes=key_quotes,
                metadata={
                    "episode_id": episode.id,
                    "platform": "xiaohongshu",
                    "angle_tag": angle_name
                }
            ))

        return copies

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
        # 获取完整的字幕内容（英文+中文翻译）
        transcripts_text = self._get_full_transcripts(episode.id)

        # 使用营销服务专用的 LLM 配置（支持动态切换 provider）
        api_key = self._llm_config["api_key"]
        if api_key and api_key != "your_api_key_here":
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url=self._llm_config["base_url"]
                )

                # 格式化金句引用
                quotes_text = ""
                if key_quotes:
                    quotes_text = "\n".join([f"• {quote[:100]}..." if len(quote) > 100 else f"• {quote}" for quote in key_quotes[:3]])

                system_prompt = """你是一位专业的小红书营销文案专家。
请根据播客完整字幕内容生成小红书风格的文章正文。

要求：
1. 开头简洁有力，直接点题，营造共鸣
2. 使用适量 emoji 表情点缀（✅、💡、🔥、✨等），不要过度
3. 内容分段清晰，使用项目符号
4. 突出"干货"和"价值"
5. 结尾要有 CTA（点赞收藏关注）
6. 字数控制在 300-500 字
7. 不要使用 Markdown 格式（不要有 ## 标题等）
8. **必须基于完整的字幕内容生成，不得偏离原意**

风格参考：
分享一个提升英语学习效率的方法，亲测有效！

✅ 核心观点1
详细说明...

✅ 核心观点2
详细说明...

💡 重点提示
金句引用...

建议收藏起来慢慢看，有问题评论区见！

点赞收藏关注，分享更多实用内容！"""

                user_prompt = f"""播客标题：{episode.title}
播客摘要：{episode.ai_summary or '暂无摘要'}

核心金句：
{quotes_text if quotes_text else '暂无'}

完整字幕内容：
{transcripts_text}

请根据以上完整字幕内容生成小红书风格的文章正文："""

                executor = ThreadPoolExecutor(max_workers=1)

                def call_ai():
                    completion = client.chat.completions.create(
                        model=self._llm_config["model"],
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
        content = f"""分享一个提升英语学习效率的方法，亲测有效！

关于 {episode.title}，有一些实用的心得想和大家分享...

✅ 核心观点1
这个话题真的很有意思，让我深思了很久。

✅ 核心观点2
特别是在实际应用中，你会发现很多细节值得注意。

💡 重点提示
{key_quotes[0] if key_quotes else '记得多思考，多实践！'}

建议收藏起来慢慢看，有问题评论区见！

点赞收藏关注，分享更多实用内容！"""

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
