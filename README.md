# EnglishPod3 Enhanced

<div align="center">

**Local-First AI-Powered English Learning Content Automation Tool**

[PRD](docs/prd.md) • [数据库设计](docs/database-design.md) • [技术栈](docs/技术栈.md) • [项目结构](docs/项目目录设计.md)

</div>

---

## 简介

EnglishPod3 Enhanced 是一个**本地优先**的英语学习内容自动化工具。它能够：

- 从 YouTube URL 自动下载音频
- 使用 WhisperX 进行高精度字幕转录
- 通过 LLM 进行字幕校对、语义分章、中英翻译
- 生成 Obsidian 可视化文档供人工审核
- 发布到 Notion 等平台

### 核心特点

| 特性 | 说明 |
|------|------|
| **本地优先** | 所有数据存储在本地 SQLite 数据库 |
| **断点续传** | 支持中断后从任意阶段恢复 |
| **用户掌控** | CLI 显式触发，无后台轮询 |
| **可视化审核** | Obsidian Markdown 作为 UI |
| **多平台发布** | 默认 Notion，可选飞书/IMA |

---

## 快速开始

### 1. 环境配置

```bash
# 克隆项目
cd D:\programming_enviroment\EnglishPod-knowledgeBase

# 激活虚拟环境 (PowerShell)
D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1

# 安装依赖（首次运行）
pip install -r requirements.txt
```

### 2. 配置 API 密钥

**重要**: 系统已改用 Windows 环境变量存储 API 密钥（不再使用 `.env` 文件）。

在 PowerShell 中设置环境变量：

```powershell
# 必需：Moonshot Kimi kimi-k2-0905-preview (主要 LLM - 字幕校对、分章、翻译)
setx MOONSHOT_API_KEY "sk-xxx"

# 必需：Zhipu GLM glm-4-plus (备用 LLM)
setx ZHIPU_API_KEY "xxx"

# 必需：Google Gemini gemini-2.5-flash (备用 LLM)
setx GEMINI_API_KEY "xxx"

# 必需：HuggingFace Token (WhisperX 说话人分离)
setx HF_TOKEN "hf_xxx"

# 必需：Notion API (发布到 Notion)
setx NOTION_API_KEY "secret_xxx"
```

**配置文件**: 其他设置在 `backend/config.yaml` 中（模型选择、路径等）：

```yaml
ai:
  moonshot:
    base_url: "https://api.moonshot.cn/v1"
    model: "kimi-k2-0905-preview"  # 主要 LLM
  zhipu:
    model: "glm-4-plus"              # 备用 LLM
  gemini:
    model: "gemini-2.5-flash"        # 备用 LLM
```

---

## 完整使用流程

系统采用**三阶段工作流**，从 URL 到发布全程 CLI 可控。

### 阶段一：生产阶段 (URL → Obsidian 文档)

```bash
# 激活虚拟环境
D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1

# 运行主工作流
python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

**终端输出示例：**

```
EnglishPod3 Enhanced - 主工作流
URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ

执行步骤: download_episode
[████████████] 100% 下载完成

执行步骤: transcribe_episode
[████████░░░] 85% 转录中 (WhisperX VRAM: 4.2GB)

执行步骤: proofread_episode
[████████████] 100% 校对完成 (修正 12 处)

执行步骤: segment_episode
[████████████] 100% 分章完成 (5 个章节)

执行步骤: translate_episode
[████████░░░] 75% 翻译中

执行步骤: generate_obsidian_doc
[████████████] 100% 文档生成完成

成功! Episode ID: 42
状态: 待审核
```

**断点续传：**

如果任务中断（如网络错误），重新运行相同 URL 会自动从断点恢复：

```bash
# 自动恢复，从头开始
python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ

# 强制重新开始（忽略断点）
python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ --restart
```

**生成的 Obsidian 文档位置：**

```
obsidian/episodes/42-视频标题.md
```

---

### 阶段二：审核阶段 (Obsidian 中审核修改)

1. **打开 Obsidian**，载入 `obsidian/` 目录

2. **审核内容**，检查：
   - 翻译准确性
   - 章节划分合理性
   - AI 摘要质量

3. **直接在表格中修改**任何不满意的内容

4. **标记审核通过**：

```yaml
---
task_id: 42
url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
status: approved    # 从 pending_review 改为 approved
---
```

5. **保存文档**

---

### 阶段三：发布阶段 (发布到 Notion)

#### 步骤 1：同步审核状态

```bash
# 扫描 Obsidian 文档，同步 status: approved 的文档到数据库
python scripts/sync_review_status.py
```

**终端输出示例：**

```
审核状态同步脚本
Obsidian → Database

扫描 Obsidian 文档...
Obsidian 文档审核状态
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
┃ Episode ┃ Status   ┃ File               ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ 42       │ approved │ 42-视频标题.md      │
│ 43       │ pending  │ 43-另一个视频.md    │
└──────────┴──────────┴────────────────────┘

统计:
  待审核 (pending_review): 1
  已通过 (approved): 1

将同步 1 个已审核通过的 Episode 到数据库
确认继续? (y/n): y

同步到数据库...
成功同步 1 个 Episode
```

#### 步骤 2：发布到平台

```bash
# 发布指定 Episode 到 Notion
python scripts/publish.py --id 42
```

**终端输出示例：**

```
EnglishPod3 Enhanced - 发布工作流
Episode ID: 42

步骤 1/3: 解析 Obsidian 文档...
  检测到 5 处修改

步骤 2/3: 生成营销文案...
  生成 5 条营销文案

步骤 3/3: 分发到各平台...
  发布到 notion...
    成功: notion
  发布到 feishu...
    警告: 飞书未配置，跳过
  发布到 ima...
    警告: IMA 未配置，跳过

发布成功! Episode ID: 42
状态: 已发布
```

**发布的 Notion 页面包含：**

| 内容块 | 说明 |
|--------|------|
| 章节导航 | 跳转表格 |
| 全文概览 | AI 生成的 200 字中文摘要 |
| 中英对照 | 时间轴 | 英文原文 | 中文翻译 |
| 全中文纯享 | 拼接后的通顺段落 |
| 营销文案 | 小红书标题 x 5 + 正文 |

---

## CLI 命令详解

### run.py - 主工作流

```bash
python scripts/run.py <URL> [--restart]
```

| 参数 | 说明 |
|------|------|
| `URL` | YouTube 视频 URL（必需） |
| `--restart` | 强制重新开始，忽略断点续传（可选） |

### sync_review_status.py - 同步审核状态

```bash
python scripts/sync_review_status.py
```

扫描 `obsidian/episodes/` 目录，将 `status: approved` 的文档同步到数据库。

### publish.py - 发布工作流

```bash
python scripts/publish.py --id <EPISODE_ID>
```

| 参数 | 说明 |
|------|------|
| `--id` | Episode ID（必需） |

---

## 工作流状态机

```
┌─────────────────────────────────────────────────────────────────┐
│                      EnglishPod3 工作流                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  INIT(0)                                                        │
│   ↓                                                             │
│  DOWNLOADED(1)      ← yt-dlp 下载音频                            │
│   ↓                                                             │
│  TRANSCRIBED(2)      ← WhisperX 转录字幕                         │
│   ↓                                                             │
│  PROOFREAD(3)        ← LLM 校对字幕（专有名词、拼写）            │
│   ↓                                                             │
│  SEGMENTED(4)        ← LLM 语义分章                              │
│   ↓                                                             │
│  TRANSLATED(5)       ← LLM 逐句翻译                              │
│   ↓                                                             │
│  READY_FOR_REVIEW(6) ← 生成 Obsidian 文档                       │
│   ↓  用户在 Obsidian 中审核，修改 status: approved              │
│  PUBLISHED(7)        ← 发布到 Notion                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**断点续传机制：**

任何阶段中断后，重新运行会自动从当前状态继续。例如：

- 中断时状态为 `SEGMENTED(4)`，重启后直接执行 `translate_episode`
- 使用 `--restart` 参数可强制从头开始

---

## 目录结构

```
D:\programming_enviroment\EnglishPod-knowledgeBase\
├── backend\
│   ├── app\
│   │   ├── models\              # SQLAlchemy 数据模型
│   │   ├── services\            # 业务逻辑服务
│   │   ├── workflows\           # 工作流编排
│   │   └── enums\               # 枚举定义
│   ├── scripts\                 # CLI 入口脚本
│   │   ├── run.py               # 主工作流
│   │   ├── sync_review_status.py
│   │   └── publish.py
│   ├── tests\                   # 测试
│   ├── obsidian\                # Obsidian 文档输出
│   │   └── episodes\            # 字幕文档
│   ├── data\                    # 本地数据
│   │   ├── audio\               # 音频文件
│   │   └── knowledge_base.db    # SQLite 数据库
│   └── venv-kb\                 # Python 虚拟环境
└── docs\                        # 项目文档
```

---

## 常见问题

### Q: 如何查看所有 Episode 的状态？

```bash
# 进入 Python REPL
python
```

```python
from app.database import get_session
from app.models import Episode
from app.enums.workflow_status import WorkflowStatus

db = get_session()
episodes = db.query(Episode).order_by(Episode.id.desc()).limit(10).all()

for ep in episodes:
    print(f"ID: {ep.id} | Title: {ep.title[:40]} | Status: {ep.workflow_status.label}")
```

### Q: Notion 发布失败怎么办？

检查 `.env` 中的 `NOTION_API_KEY` 和 `NOTION_DATABASE_ID` 是否正确：

```bash
# 测试 Notion 连接
python scripts/publish.py --id <episode_id>
```

错误信息会显示具体原因。

### Q: 如何重新处理某个 Episode？

```bash
# 强制重新开始
python scripts/run.py <原始_URL> --restart
```

### Q: Obsidian 文档可以手动编辑吗？

可以。任何修改都会在发布时被检测并：
1. 回填到数据库（`translations.is_edited = TRUE`）
2. 体现到 Notion 发布内容中

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI 触发层                            │
│     run.py │ sync_review_status.py │ publish.py             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      工作流编排层                            │
│           WorkflowRunner │ WorkflowPublisher                │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                       服务层                                 │
│  Download │ Transcription │ Proofreading │ Segmentation     │
│  Translation │ Obsidian │ Marketing │ NotionPublisher       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                       数据层                                 │
│     SQLAlchemy ORM │ SQLite │ WhisperX │ OpenAI API         │
└─────────────────────────────────────────────────────────────┘
```

---

## 配置文件

### 环境变量 (Windows)

所有 API 密钥通过 Windows 环境变量配置（PowerShell）：

```powershell
# 必需：LLM 服务（三选一或全部配置）
setx MOONSHOT_API_KEY "sk-xxx"      # Moonshot Kimi kimi-k2-0905-preview (主要)
setx ZHIPU_API_KEY "xxx"             # Zhipu GLM glm-4-plus (备用)
setx GEMINI_API_KEY "xxx"            # Google Gemini gemini-2.5-flash (备用)

# 必需：WhisperX 说话人分离
setx HF_TOKEN "hf_xxx"

# 必需：Notion 发布
setx NOTION_API_KEY "secret_xxx"
```

### backend/config.yaml

其他配置在 YAML 文件中：

```yaml
ai:
  moonshot:
    model: "kimi-k2-0905-preview"
  zhipu:
    model: "glm-4-plus"
  gemini:
    model: "gemini-2.5-flash"

database:
  path: "./data/episodes.db"

obsidian:
  vault_path: "D:/programming_enviroment/EnglishPod-knowledgeBase/obsidian"
  notes_subdir: "episodes"

notion:
  parent_page_id: "2ff27d357f368046aba9d3a7cc21f05c"
```

---

## 文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| PRD | [docs/prd.md](docs/prd.md) | 产品需求文档 |
| 数据库设计 | [docs/database-design.md](docs/database-design.md) | 数据库 Schema |
| 技术栈 | [docs/技术栈.md](docs/技术栈.md) | 技术选型说明 |
| 项目结构 | [docs/项目目录设计.md](docs/项目目录设计.md) | 目录结构设计 |
| 开发配置 | [docs/开发配置.md](docs/开发配置.md) | 开发环境配置 |
| 开发计划 | [docs/开发计划.md](docs/开发计划.md) | 开发计划 |

---

## License

MIT
