"""
从字幕文件直接生成营销文案并输出到 Obsidian

使用方法：
python scripts/generate_marketing_from_srt.py <字幕文件路径>

示例：
python scripts/generate_marketing_from_srt.py D:/path/to/subtitle.srt
"""
import os
import sys
import re
from pathlib import Path
from datetime import datetime

# 设置 UTF-8 编码输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from app.config import get_marketing_llm_config


def parse_srt(file_path: str) -> str:
    """
    解析 SRT 字幕文件，提取纯文本

    Args:
        file_path: SRT 文件路径

    Returns:
        str: 提取的文本内容
    """
    # 尝试不同编码读取文件
    content = None
    for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        raise ValueError(f"无法读取文件: {file_path}")

    # 移除序号和时间戳
    lines = content.split('\n')
    text_lines = []

    for line in lines:
        line = line.strip()
        # 跳过序号（纯数字）
        if line.isdigit():
            continue
        # 跳过时间戳 (格式: 00:00:00,000 --> 00:00:00,000)
        if '-->' in line:
            continue
        # 跳过空行
        if not line:
            continue
        # 去掉说话人标记，保留文本
        if line.startswith('[SPEAKER_'):
            # 去掉 [SPEAKER_XX] 前缀
            line = line.split(']', 1)[1].strip() if ']' in line else line

        text_lines.append(line)

    return ' '.join(text_lines)


def generate_summary_with_llm(transcript_text: str) -> str:
    """
    使用 LLM 生成摘要

    Args:
        transcript_text: 字幕文本

    Returns:
        str: 生成的摘要
    """
    llm_config = get_marketing_llm_config()
    client = OpenAI(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"]
    )

    # 截取前 2000 字符用于生成摘要
    text_for_summary = transcript_text[:2000]

    system_prompt = """你是一位专业的内容分析师。
请根据提供的字幕内容，生成一个简洁的摘要（100-200字）。

要求：
1. 准确概括内容主题
2. 提取核心观点
3. 语言简洁专业"""

    user_prompt = f"""请为以下字幕内容生成摘要：

{text_for_summary}

摘要："""

    try:
        response = client.chat.completions.create(
            model=llm_config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"生成摘要失败: {e}")
        # 返回默认摘要
        return "关于产品设计工具和设计流程的深度讨论，分享了对创新设计理念的见解。"


def generate_marketing_content(title: str, summary: str, transcript_text: str) -> dict:
    """
    生成营销文案（包含3个不同角度的正文版本）

    Args:
        title: 标题
        summary: 内容摘要
        transcript_text: 字幕文本

    Returns:
        dict: 包含标题、内容、标签、3个角度正文版本的营销文案
    """
    llm_config = get_marketing_llm_config()
    client = OpenAI(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"]
    )

    # 1. 生成标题
    print("\n正在生成标题...")
    title_prompt = f"""你是一位专业的小红书营销文案专家。
请根据以下内容生成 3 个吸引人的小红书标题。

标题要求：
1. 每个标题要包含 emoji 表情
2. 标题要吸引眼球，符合小红书风格
3. 标题长度控制在 30 字以内
4. 直接返回标题列表，每行一个

内容标题：{title}
内容摘要：{summary}

请生成 3 个小红书标题："""

    titles_response = client.chat.completions.create(
        model=llm_config["model"],
        messages=[{"role": "user", "content": title_prompt}],
        temperature=0.8,
    )
    titles = [line.strip() for line in titles_response.choices[0].message.content.split('\n') if line.strip()][:3]

    # 2. 生成标签
    print("正在生成标签...")
    tag_prompt = f"""你是一位专业的小红书营销文案专家。
请根据以下内容生成 5 个相关话题标签。

标签要求：
1. 每个标签必须以 # 开头
2. 标签要与内容相关，符合小红书热门话题
3. 直接返回标签，空格分隔

内容标题：{title}
内容摘要：{summary}

请生成 5 个相关标签："""

    tags_response = client.chat.completions.create(
        model=llm_config["model"],
        messages=[{"role": "user", "content": tag_prompt}],
        temperature=0.7,
    )
    tags = re.findall(r'#[\w\u4e00-\u9fff]+', tags_response.choices[0].message.content)[:5]

    # 3. 生成3个不同角度的正文版本
    print("正在生成3个不同角度的正文版本...")

    angle_prompt = f"""你是一位专业的小红书营销文案专家。
请根据以下字幕内容，生成 3 个不同角度的营销文案版本。

【重要约束】
1. 必须严格基于字幕内容生成，不得编造字幕中没有的信息
2. 只能提炼、重组、润色字幕中的内容
3. 如果字幕中没有足够信息支撑某个角度，请基于现有内容转换表达方式
4. 所有数据、案例、观点必须来自字幕原文

【字幕原文】
{transcript_text}

【任务】
分析上述字幕内容，定义 3 个不同的内容角度，然后为每个角度生成：
1. 角度名称（4-8字，简洁明了）
2. 该角度对应的标题（包含emoji，30字以内）
3. 该角度的正文内容（300-500字）

【正文要求】
- 开头简洁有力，直接点题
- 使用适量 emoji 表情点缀
- 内容分段清晰，使用项目符号
- 突出"干货"和"价值"
- 结尾要有 CTA（点赞收藏关注）
- 不要使用 Markdown 格式

【输出格式】（请严格按此格式输出）
---
【角度1】<角度名称>
标题：<标题>
正文：
<正文内容>

---
【角度2】<角度名称>
标题：<标题>
正文：
<正文内容>

---
【角度3】<角度名称>
标题：<标题>
正文：
<正文内容>

---

请生成 3 个不同角度的营销文案："""

    angles_response = client.chat.completions.create(
        model=llm_config["model"],
        messages=[{"role": "user", "content": angle_prompt}],
        temperature=0.8,
    )
    angles_text = angles_response.choices[0].message.content.strip()

    # 解析3个角度的文案
    angle_versions = []
    angle_blocks = re.split(r'---+', angles_text)

    for block in angle_blocks:
        if not block.strip():
            continue

        # 提取角度名称
        angle_match = re.search(r'【角度[123]】(.+?)(?:\n|$)', block)
        if not angle_match:
            angle_match = re.search(r'角度[123][:：](.+?)(?:\n|$)', block)

        angle_name = angle_match.group(1).strip() if angle_match else "未知角度"

        # 提取标题
        title_match = re.search(r'标题[：:](.+?)(?:\n|$)', block)
        version_title = title_match.group(1).strip() if title_match else titles[0]

        # 提取正文（在"正文："之后的内容）
        content_match = re.search(r'正文[：:]\s*\n(.+)', block, re.DOTALL)
        if content_match:
            version_content = content_match.group(1).strip()
        else:
            # 如果没有"正文："标记，取角度名称后的所有内容
            lines = block.split('\n')
            content_start = -1
            for i, line in enumerate(lines):
                if '正文' in line or '内容' in line:
                    content_start = i + 1
                    break
            if content_start >= 0:
                version_content = '\n'.join(lines[content_start:]).strip()
            else:
                version_content = block.strip()

        angle_versions.append({
            "angle_name": angle_name,
            "title": version_title,
            "content": version_content
        })

    # 确保有3个版本
    while len(angle_versions) < 3:
        angle_versions.append({
            "angle_name": f"版本{len(angle_versions) + 1}",
            "title": titles[len(angle_versions) % len(titles)],
            "content": "内容生成中..."
        })

    return {
        "titles": titles,
        "tags": tags,
        "angles": angle_versions,
        "selected_title": titles[0] if titles else title
    }


def save_to_obsidian(marketing_data: dict, source_file: str, output_dir: str):
    """
    保存营销文案到 Obsidian（包含3个角度版本）

    Args:
        marketing_data: 营销文案数据（包含angles列表）
        source_file: 源文件路径
        output_dir: Obsidian 输出目录
    """
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"marketing_{timestamp}.md"
    output_path = Path(output_dir) / filename

    # 获取源文件信息
    source_name = Path(source_file).stem

    # 生成3个角度版本的Markdown内容
    angles_content = ""
    for i, angle in enumerate(marketing_data.get('angles', []), 1):
        angles_content += f"""
### 角度{i}：{angle['angle_name']}

**标题**
{angle['title']}

**正文**
{angle['content']}

---

"""

    # 生成完整的 Markdown 内容
    markdown_content = f"""# 营销文案 - {source_name}

> 来源文件: `{source_file}`
> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 状态: 待审核

---

## 备选标题（3个）

{chr(10).join(f"{i+1}. {title}" for i, title in enumerate(marketing_data['titles']))}

---

## 话题标签

{' '.join(marketing_data['tags'])}

---

## 正文版本（3个角度）

{angles_content}
## 数据库导入说明

**每个角度对应一条数据库记录：**

| 字段 | 值 |
|------|-----|
| platform | xhs |
| angle_tag | 见上方各角度名称 |
| title | 见上方各角度标题 |
| content | 见上方各角度正文 |
| status | pending |

---

## 审核说明

- [ ] 内容审核
- [ ] 标签优化
- [ ] 标题调整
- [ ] 发布准备

---

### 备注

请审核以上内容，选择最优角度版本用于发布。
"""

    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    print(f"\n营销文案已保存到: {output_path}")
    print(f"共生成 {len(marketing_data.get('angles', []))} 个角度版本")
    return output_path


def main():
    if len(sys.argv) < 2:
        print("使用方法: python generate_marketing_from_srt.py <字幕文件路径>")
        print("示例: python generate_marketing_from_srt.py D:/path/to/subtitle.srt")
        sys.exit(1)

    srt_file = sys.argv[1]

    if not Path(srt_file).exists():
        print(f"错误: 文件不存在 - {srt_file}")
        sys.exit(1)

    print("="*60)
    print("从字幕文件生成营销文案")
    print("="*60)
    print(f"\n输入文件: {srt_file}")

    # 解析字幕文件
    print("\n步骤 1: 解析字幕文件...")
    transcript_text = parse_srt(srt_file)
    print(f"提取文本长度: {len(transcript_text)} 字符")

    # 生成摘要
    print("\n步骤 2: 生成内容摘要...")
    summary = generate_summary_with_llm(transcript_text)
    print(f"摘要: {summary}")

    # 生成营销文案
    print("\n步骤 3: 生成营销文案...")
    title = Path(srt_file).stem.replace('_', ' ')
    marketing_data = generate_marketing_content(title, summary, transcript_text)

    # 显示结果
    print("\n" + "="*60)
    print("生成完成")
    print("="*60)
    print(f"\n备选标题:")
    for i, t in enumerate(marketing_data['titles'], 1):
        print(f"  {i}. {t}")
    print(f"\n话题标签:")
    print(f"  {' '.join(marketing_data['tags'])}")

    print(f"\n正文版本（{len(marketing_data.get('angles', []))}个角度）:")
    for i, angle in enumerate(marketing_data.get('angles', []), 1):
        print(f"\n  【角度{i}】{angle['angle_name']}")
        print(f"  标题: {angle['title']}")
        preview = angle['content'][:150] + "..." if len(angle['content']) > 150 else angle['content']
        print(f"  预览: {preview}")

    # 保存到 Obsidian
    print("\n步骤 4: 保存到 Obsidian...")
    obsidian_dir = "D:/programming_enviroment/EnglishPod-knowledgeBase/obsidian/marketing"
    output_path = save_to_obsidian(marketing_data, srt_file, obsidian_dir)

    print("\n完成！请在 Obsidian 中审核生成的营销文案。")


if __name__ == "__main__":
    main()
