# EnglishPod3 Enhanced

<div align="center">

**Local-First AI-Powered English Learning Content Automation Tool**

[操作手册](docs/操作手册.md) • [PRD](docs/prd.md) • [数据库设计](docs/database-design.md) • [技术栈](docs/技术栈.md)

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

**虚拟环境**：`backend/venv-kb`（以下命令均需在激活后执行）

```powershell
# 进入 backend 目录
cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend

# 激活虚拟环境 venv-kb (PowerShell)
venv-kb\Scripts\Activate.ps1

# 安装依赖（首次运行）
pip install -r requirements.txt
```

### 2. 配置 API 密钥

**重要**: 系统使用 Windows 环境变量存储 API 密钥（不使用 `.env` 文件）。

在 PowerShell 中设置环境变量：

```powershell
# 必需：Moonshot Kimi (主要 LLM - 字幕校对、分章、翻译、营销文案)
setx MOONSHOT_API_KEY "sk-xxx"

# 必需：Zhipu GLM (备用 LLM)
setx ZHIPU_API_KEY "xxx"

# 必需：Google Gemini (备用 LLM)
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
    model: "kimi-k2-turbo-preview"   # 主要 LLM
  zhipu:
    model: "glm-4.7-flash"           # 备用 LLM
  gemini:
    model: "gemini-2.5-flash"        # 备用 LLM
  marketing:
    provider: "moonshot"             # 营销文案生成使用的 LLM
```

---

## 完整使用流程

系统采用**三阶段工作流**，从 URL 到发布全程 CLI 可控。

### 阶段一：生产阶段 (URL → Obsidian 文档)

```powershell
# 进入 backend 目录并激活 venv-kb
cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend
venv-kb\Scripts\Activate.ps1

# 运行主工作流（PowerShell 下 URL 含 & 时需用双引号包裹）
python scripts/run.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
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

如果任务中断（如网络错误），重新运行相同 URL 会自动从断点恢复。以下命令需在 `backend` 目录下执行：

```powershell
# 自动恢复
python scripts/run.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 强制重新开始（忽略断点）
python scripts/run.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --restart

# 强制重新切分（清除旧章节并重新调用 AI）
python scripts/run.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --force-resegment
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
status: approved    # 从 pending_review 改为 approved，同步后变为 APPROVED(7)
---
```

5. **保存文档**

---

### 阶段三：发布阶段 (发布到 Notion)

#### 步骤 1：同步审核状态

```powershell
# 扫描 Obsidian 文档，将 status: approved 的文档同步到数据库（更新为 APPROVED 状态）
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

将同步 1 个已审核通过的 Episode 到数据库（状态更新为 APPROVED）
确认继续? (y/n): y

同步到数据库...
成功同步 1 个 Episode
```

#### 步骤 2：发布到平台

```powershell
# 发布指定 Episode 到 Notion（需先完成步骤 1，Episode 状态为 APPROVED）
python scripts/publish.py --id 42
```

**终端输出示例：**

```
EnglishPod3 Enhanced - 发布工作流
Episode ID: 42

步骤 1/2: 生成营销文案...
  生成 5 条营销文案

步骤 2/2: 分发到各平台...
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

以下命令需在 `backend/` 目录下、**已激活 venv-kb** 后执行。

### run.py - 主工作流

```powershell
cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend
python scripts/run.py "<URL>" [--restart] [--force-resegment]
```

| 参数 | 说明 |
|------|------|
| `URL` | YouTube 视频 URL（必需）。PowerShell 下若 URL 含 `&`（如 `&t=14s`）需用双引号包裹 |
| `--restart` | 强制重新开始，忽略断点续传（可选） |
| `--force-resegment` | 强制重新切分，清除旧章节并重新调用 AI（可选） |
| `--cookies-from-browser` | 使用浏览器 Cookie（如 `chrome`）（可选，可能因 YouTube 轮换失效） |
| `--cookies` | 使用 cookies 文件（Netscape 格式，推荐，更可靠） |

### sync_review_status.py - 同步审核状态

**工作目录**：`backend/`。

```powershell
cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend
python scripts/sync_review_status.py
```

扫描 `obsidian/episodes/` 目录，将 `status: approved` 的文档同步到数据库（更新为 APPROVED 状态，并回填用户对翻译的修改）。

### publish.py - 发布工作流

**工作目录**：`backend/`。

```powershell
cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend
python scripts/publish.py --id <EPISODE_ID> [--force-remarketing]
```

| 参数 | 说明 |
|------|------|
| `--id` | Episode ID（必需） |
| `--force-remarketing` | 强制重新生成营销文案（可选） |

### test_complete_workflow.py - 完整流程测试（开发用）

从本地音频文件测试全流程（跳过 URL 下载），支持断点续传、强制重译等：

```powershell
python scripts/test_complete_workflow.py --episode-id <ID> --test-db
python scripts/test_complete_workflow.py --episode-id <ID> --test-db --resume-translation   # 断点续传翻译
python scripts/test_complete_workflow.py --episode-id <ID> --test-db --force-remarketing   # 强制重新生成营销文案
```

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
│  READY_FOR_REVIEW(6) ← 生成 Obsidian 文档                        │
│   ↓  用户在 Obsidian 中审核，修改 status: approved               │
│  APPROVED(7)         ← sync_review_status.py 同步审核状态        │
│   ↓                                                             │
│  PUBLISHED(8)        ← publish.py 发布到 Notion                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**断点续传机制：**

任何阶段中断后，重新运行会自动从当前状态继续。例如：

- 中断时状态为 `SEGMENTED(4)`，重启后直接执行 `translate_episode`
- 使用 `--restart` 参数可强制从头开始
- 使用 `--force-resegment` 参数可仅重新执行章节切分（清除旧章节）

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
│   │   ├── run.py               # 主工作流（URL → Obsidian）
│   │   ├── sync_review_status.py # 同步审核状态
│   │   ├── publish.py           # 发布到 Notion
│   │   └── test_complete_workflow.py  # 完整流程测试（本地音频）
│   ├── tests\                   # 单元/集成测试
│   ├── obsidian\                # Obsidian 文档输出
│   │   ├── episodes\            # 字幕文档
│   │   └── marketing\           # 营销文案
│   ├── data\                    # 本地数据
│   │   ├── audios\              # 音频文件
│   │   └── episodes.db          # SQLite 数据库
│   └── venv-kb\                 # Python 虚拟环境
└── docs\                        # 项目文档
```

---

## 常见问题

### Q: 如何查看所有 Episode 的状态？

```powershell
# 进入 backend 目录后启动 Python REPL
cd backend
python
```

```python
from app.database import get_session
from app.models import Episode
from app.enums.workflow_status import WorkflowStatus

with get_session() as db:
    episodes = db.query(Episode).order_by(Episode.id.desc()).limit(10).all()
    for ep in episodes:
        status_label = WorkflowStatus(ep.workflow_status).label
        print(f"ID: {ep.id} | Title: {ep.title[:40]} | Status: {status_label}")
```

### Q: Notion 发布失败怎么办？

检查环境变量 `NOTION_API_KEY` 和 `NOTION_DATABASE_ID` 是否正确配置。发布前需确保 Episode 状态为 APPROVED（先运行 `sync_review_status.py`）：

```powershell
# 测试 Notion 连接
python scripts/publish.py --id <episode_id>
```

错误信息会显示具体原因。

### Q: 如何重新处理某个 Episode？

```powershell
# 强制重新开始（URL 含 & 时用双引号包裹）
python scripts/run.py "<原始_URL>" --restart
```

### Q: PowerShell 报错「不允许使用与号(&)」？

URL 中含 `&`（如 `&t=14s` 时间戳）时，PowerShell 会将其解析为特殊字符。用双引号包裹整个 URL 即可：`python scripts/run.py "https://...&t=14s"`。

### Q: 报错「No such file or directory」找不到 scripts/run.py？

脚本位于 `backend/scripts/`，需先在 `backend` 目录下执行：

```powershell
cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend
python scripts/run.py "https://www.youtube.com/watch?v=xxx&t=14s"
```

### Q: 下载报错「Sign in to confirm you're not a bot」？

项目已集成 **yt-dlp-invidious** 插件，YouTube 被拦截时会**自动切换**到 Invidious 实例下载，多数情况下无需额外配置。若仍失败，可尝试：

**方式 A：cookies 文件**

1. 安装 Chrome 扩展 [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. 打开**无痕窗口**，登录 YouTube，访问 `https://www.youtube.com/robots.txt`（仅此标签）
3. 用扩展导出 `youtube.com` 的 cookies 到 `backend/data/cookies.txt`
4. **立即关闭无痕窗口**（否则 cookie 会被轮换失效）
5. 运行：

```powershell
python scripts/run.py "https://www.youtube.com/watch?v=xxx" --cookies backend/data/cookies.txt
```

**方式 B：浏览器 Cookie（可能因轮换失效）**

```powershell
python scripts/run.py "https://www.youtube.com/watch?v=xxx" --cookies-from-browser chrome
```

需确保 Chrome 已登录 YouTube。部分用户报告 Firefox 比 Edge 更可靠。

### Q: Obsidian 文档可以手动编辑吗？

可以。在 Obsidian 中修改翻译内容后，运行 `sync_review_status.py` 时会：
1. 检测并回填到数据库（`translations.is_edited = TRUE`）
2. 发布时体现到 Notion 内容中

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
│  Download │ Transcription │ SubtitleProofreading │ Segmentation │
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
setx MOONSHOT_API_KEY "sk-xxx"      # Moonshot Kimi kimi-k2-turbo-preview (主要)
setx ZHIPU_API_KEY "xxx"            # Zhipu GLM glm-4.7-flash (备用)
setx GEMINI_API_KEY "xxx"           # Google Gemini gemini-2.5-flash (备用)

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
    model: "kimi-k2-turbo-preview"
  zhipu:
    model: "glm-4.7-flash"
  gemini:
    model: "gemini-2.5-flash"
  marketing:
    provider: "moonshot"

database:
  path: "./data/episodes.db"

obsidian:
  vault_path: "D:/programming_enviroment/EnglishPod-knowledgeBase/obsidian"
  notes_subdir: "episodes"
  marketing_subdir: "marketing"

notion:
  parent_page_id: "2ff27d357f368046aba9d3a7cc21f05c"
```

---

## 文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| **操作手册** | [docs/操作手册.md](docs/操作手册.md) | 日常操作指南 |
| PRD | [docs/prd.md](docs/prd.md) | 产品需求文档 |
| 数据库设计 | [docs/database-design.md](docs/database-design.md) | 数据库 Schema |
| 技术栈 | [docs/技术栈.md](docs/技术栈.md) | 技术选型说明 |
| 项目结构 | [docs/项目目录设计.md](docs/项目目录设计.md) | 目录结构设计 |
| 开发配置 | [docs/开发配置.md](docs/开发配置.md) | 开发环境配置 |
| 开发计划 | [docs/开发计划.md](docs/开发计划.md) | 开发计划 |

---

## License

MIT
