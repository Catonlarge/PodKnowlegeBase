# 设计方案：EnglishPod3 Enhanced 代码复用方案

| 文档版本 | V1.0 |
| --- | --- |
| **状态** | 待审核 |
| **日期** | 2026-02-04 |
| **核心理念** | 复用 PodFlow 数据库骨架 + 新增 CLI/Obsidian/Markdown 渲染层 |

---

## 1. 项目概述

### 1.1 项目定位

**EnglishPod3 Enhanced** 是一个基于 **PodFlow** 数据库架构扩展的英语学习内容自动化工作流系统。两个项目的关系：

| 项目 | 定位 | Git仓库 |
| --- | --- | --- |
| **PodFlow** | 本地播客学习工具（Web UI） | `learning-EnglishPod3` |
| **EnglishPod3 Enhanced** | CLI驱动的自动化内容生产流水线 | `EnglishPod3-Enhanced` (新) |

### 1.2 复用原则

- **代码复制，非引用**：将 PodFlow 可复用模块复制到新项目
- **独立演进**：两个项目独立维护，不共享代码
- **架构分离**：PodFlow 保留 Web UI，EnglishPod3 Enhanced 纯 CLI

---

## 2. PodFlow 可复用模块分析

### 2.1 数据库层（高度复用）

#### 复用模块：`backend/app/models.py`

| 可复用内容 | 复用方式 | 修改说明 |
| --- | --- | --- |
| `Episode` 模型 | 直接复制 | 扩展 `status` 字段为 7 状态枚举 |
| `TranscriptCue` 模型 | 直接复制 | 新增 `translation` 字段 |
| `AudioSegment` 模型 | 直接复制 | 无需修改 |
| 数据库连接配置 | 直接复制 | 复用 `get_db()` 和 `init_db()` |

#### 状态机扩展

```python
# 新增状态枚举（扩展现有的转录状态）
class WorkflowStatus(Enum):
    INIT = 0              # 已入库
    DOWNLOADED = 1        # 本地文件就绪
    TRANSCRIBED = 2       # WhisperX 转录完成
    SEGMENTED = 3         # 语义章节切分完成
    TRANSLATED = 4        # 逐句翻译完成
    READY_FOR_REVIEW = 5  # Obsidian 文档已生成
    PUBLISHED = 6         # 已分发
```

### 2.2 服务层（中度复用）

#### 复用模块：`backend/app/services/`

| 服务模块 | 复用程度 | 复用方式 |
| --- | --- | --- |
| `whisper_service.py` | 完全复用 | 直接复制 |
| `transcription_service.py` | 部分复用 | 复用转录逻辑，移除 Web API 依赖 |
| `ai_service.py` | 高度复用 | 复用基础架构，新增语义分析接口 |

### 2.3 工具层（完全复用）

#### 复用模块：`backend/app/utils/`

| 工具模块 | 复用方式 |
| --- | --- |
| `file_utils.py` | 直接复制 |
| 环境配置 `.env` 管理模式 | 直接复制 |

---

## 3. 新项目架构设计

### 3.1 目录结构

```
englishpod3-enhanced/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI入口（仅用于健康检查）
│   │   ├── config.py               # [复用] 配置管理
│   │   ├── models.py               # [复用+扩展] 数据库模型
│   │   │
│   │   ├── services/               # 服务层
│   │   │   ├── whisper_service.py          # [复用] Whisper转录
│   │   │   ├── transcription_service.py    # [复用+修改] 转录服务
│   │   │   ├── ai_service.py               # [复用+扩展] AI服务
│   │   │   ├── semantic_service.py         # [新增] 语义章节切分
│   │   │   ├── translation_service.py      # [新增] 逐句翻译
│   │   │   ├── markdown_service.py         # [新增] Markdown渲染
│   │   │   ├── publish_service.py          # [新增] 发布分发
│   │   │   └── download_service.py         # [新增] 视频下载
│   │   │
│   │   ├── utils/                  # 工具层
│   │   │   ├── file_utils.py               # [复用] 文件处理
│   │   │   ├── time_utils.py               # [新增] 时间格式化
│   │   │   └── markdown_parser.py          # [新增] Markdown解析
│   │   │
│   │   └── workflow/               # [新增] 工作流编排
│   │       ├── state_machine.py            # 状态机
│   │       └── orchestrator.py             # 流程编排
│   │
│   ├── scripts/                    # CLI脚本
│   │   ├── run.py                          # 主流程脚本
│   │   ├── publish.py                      # 发布脚本
│   │   └── resume.py                       # 断点续传脚本
│   │
│   ├── data/                       # 数据目录
│   │   ├── englishpod3.db                 # SQLite数据库
│   │   ├── downloads/                     # 下载的视频/音频
│   │   └── obsidian_vault/                # Obsidian文档输出
│   │
│   ├── tests/                      # 测试
│   ├── venv/
│   ├── .env
│   └── requirements.txt
│
└── docs/
    └── design-reuse-proposal.md
```

### 3.2 核心新增模块设计

#### 3.2.1 语义分析服务 (`semantic_service.py`)

**功能**：将英文 Transcript 转换为中文章节结构

```python
class SemanticService:
    """
    语义分析服务

    输入：完整的英文 Transcript（含时间戳）
    输出：中文章节划分 JSON
    """

    def analyze_chapters(self, transcript: List[TranscriptCue]) -> Dict:
        """
        分析英文原文的语义转折点，进行章节划分

        Prompt策略：
        - Input: 英文原文 + 时间戳
        - Instruction: "分析语义转折点，输出中文章节标题和摘要"
        - Output: JSON格式章节结构
        """
        pass
```

#### 3.2.2 翻译服务 (`translation_service.py`)

**功能**：逐句翻译，保持时间轴对齐

```python
class TranslationService:
    """
    翻译服务

    特性：
    - 逐句翻译，保持 Timeline | English | Chinese 对应
    - Patch Mode：AI仅返回修正内容，本地执行UPDATE
    """

    def translate_transcript(
        self,
        episode_id: int,
        batch_size: int = 50
    ) -> None:
        """
        批量翻译字幕，保存到 TranscriptCue.translation 字段
        """
        pass

    def patch_translation(
        self,
        cue_id: int,
        fixes: List[Dict]
    ) -> None:
        """
        Token优化：仅修正指定ID的翻译
        输入：[{"id": 105, "fix": "修正后的专有名词"}]
        """
        pass
```

#### 3.2.3 Markdown 渲染服务 (`markdown_service.py`)

**功能**：生成 Obsidian 交互式文档

```python
class MarkdownService:
    """
    Markdown渲染服务

    生成格式：
    - 头部：YAML Frontmatter + 全文概览 + 章节导航
    - 主体：章节化中英对照表格
    - 尾部：纯中文版 + 营销文案
    """

    def render_obsidian_doc(
        self,
        episode: Episode,
        output_path: Path
    ) -> None:
        """
        生成完整的 Obsidian Markdown 文档
        """
        pass

    def render_placeholder(
        self,
        progress: float,
        stage: str
    ) -> str:
        """
        生成处理中的占位内容
        """
        pass
```

#### 3.2.4 发布服务 (`publish_service.py`)

**功能**：解析 Markdown 并分发

```python
class PublishService:
    """
    发布服务

    流程：
    1. 解析 Obsidian Markdown 提取用户修改
    2. 回填数据库
    3. 分发至飞书/IMA
    """

    def parse_markdown(self, markdown_path: Path) -> Dict:
        """
        解析 Markdown 表格，提取修改后的翻译
        """
        pass

    def update_database(
        self,
        episode_id: int,
        parsed_data: Dict
    ) -> None:
        """
        回填数据库
        """
        pass

    def distribute_feishu(self, episode: Episode) -> str:
        """
        分发至飞书多维表格
        """
        pass

    def distribute_ima(self, episode: Episode) -> str:
        """
        分发至腾讯IMA
        """
        pass
```

#### 3.2.5 下载服务 (`download_service.py`)

**功能**：使用 yt-dlp 下载视频/音频

```python
class DownloadService:
    """
    下载服务

    支持：YouTube、Bilibili、播客RSS等
    """

    def download_media(self, url: str, output_dir: Path) -> Dict:
        """
        下载媒体文件

        返回：
        - file_path: 本地文件路径
        - duration: 时长
        - title: 标题
        """
        pass
```

#### 3.2.6 状态机 (`state_machine.py`)

**功能**：管理任务状态流转

```python
class StateMachine:
    """
    状态机

    特性：
    - 断点续传：根据当前状态决定执行下一步
    - 异常保护：失败时保存当前状态，不回滚
    """

    def get_current_state(self, episode_id: int) -> WorkflowStatus:
        """获取当前状态"""
        pass

    def transition_to(
        self,
        episode_id: int,
        target_state: WorkflowStatus
    ) -> None:
        """状态转移"""
        pass

    def resume_workflow(self, episode_id: int) -> None:
        """断点续传入口"""
        pass
```

---

## 4. CLI 脚本设计

### 4.1 主流程脚本 (`run.py`)

```bash
# 用法
python run.py --url "https://youtube.com/watch?v=xyz"

# 功能
1. 解析URL，下载媒体（状态：INIT → DOWNLOADED）
2. 调用 WhisperX 转录（状态：DOWNLOADED → TRANSCRIBED）
3. 调用 SemanticService 章节切分（状态：TRANSCRIBED → SEGMENTED）
4. 调用 TranslationService 翻译（状态：SEGMENTED → TRANSLATED）
5. 调用 MarkdownService 生成 Obsidian 文档（状态：TRANSLATED → READY_FOR_REVIEW）
```

**Rich Terminal UI 设计**：

```
┌─────────────────────────────────────────────────────────────┐
│  EnglishPod3 Enhanced - 任务处理中                          │
├─────────────────────────────────────────────────────────────┤
│  URL: https://youtube.com/watch?v=xyz                       │
│  任务ID: 1024                                               │
├─────────────────────────────────────────────────────────────┤
│  进度: [████████████░░░░░░░░] 60%                          │
│  阶段: Step 3/5 - 语义章节切分                              │
│                                                              │
│  📥 下载: ✅ 完成 (12MB/s)                                  │
│  🎤 转录: ✅ 完成 (WhisperX, 4.2GB VRAM)                   │
│  📝 切分: ⏳ 处理中 (AI语义分析...)                         │
│  🌐 翻译: ⏸️ 等待中                                         │
│  📄 文档: ⏸️ 等待中                                         │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 发布脚本 (`publish.py`)

```bash
# 用法
python publish.py --id 1024

# 功能
1. 解析 Obsidian Markdown 提取用户修改
2. 回填数据库（状态：READY_FOR_REVIEW → PUBLISHED）
3. 分发至飞书/IMA
```

### 4.3 断点续传脚本 (`resume.py`)

```bash
# 用法
python resume.py --id 1024

# 功能
- 检查数据库状态，从断点处恢复执行
- 例如：状态为 TRANSCRIBED 时，跳过下载和转录，直接执行语义切分
```

---

## 5. 数据流设计

### 5.1 完整数据流

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  URL输入    │ -> │  下载服务    │ -> │  本地文件   │
└─────────────┘    └──────────────┘    └─────────────┘
                                               │
                                               v
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Obsidian   │ <- │ Markdown渲染 │ <- │ WhisperX    │
│  文档输出   │    │              │    │  转录       │
└─────────────┘    └──────────────┘    └─────────────┘
                          ↑                     │
                          │                     v
                    ┌──────────────┐    ┌─────────────┐
                    │  章节切分    │ <- │ 英文字幕    │
                    │  (AI语义)   │    └─────────────┘
                    └──────────────┘            │
                          ↑                     |
                    ┌──────────────┐            |
                    │  翻译服务    │ <-----------
                    │  (逐句翻译) │
                    └──────────────┘
```

### 5.2 数据库字段扩展

#### Episode 表扩展字段

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `source_url` | String | 原始URL（新增） |
| `workflow_status` | Integer | 工作流状态（0-6） |
| `chapter_data` | JSON | 章节切分结果 |

#### TranscriptCue 表扩展字段

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `translation` | Text | 中文翻译（新增） |
| `chapter_id` | Integer | 关联章节（新增） |

---

## 6. 实施路线图

### Phase 1: 数据库与状态机（Week 1）

- [ ] 复制 `models.py`，扩展状态枚举
- [ ] 实现 `StateMachine` 类
- [ ] 编写断点续传测试
- [ ] 验证状态流转正确性

### Phase 2: 核心服务（Week 2）

- [ ] 复制 `whisper_service.py`
- [ ] 实现 `DownloadService`（yt-dlp 集成）
- [ ] 实现 `SemanticService`（语义章节切分）
- [ ] 实现 `TranslationService`（逐句翻译）

### Phase 3: Markdown渲染（Week 3）

- [ ] 实现 `MarkdownService`
- [ ] 生成 Obsidian 文档模板
- [ ] 实现占位符动态更新
- [ ] 测试文档格式

### Phase 4: CLI脚本（Week 4）

- [ ] 实现 `run.py`（Rich Terminal UI）
- [ ] 实现 `publish.py`
- [ ] 实现 `resume.py`
- [ ] 完整流程测试

### Phase 5: 发布分发（Week 5）

- [ ] 集成飞书 OpenAPI
- [ ] 集成腾讯 IMA API
- [ ] Markdown 解析与回填
- [ ] 端到端测试

---

## 7. 技术依赖

### 新增依赖

```txt
# CLI 与终端UI
rich>=13.0.0           # Rich Terminal UI
click>=8.0.0           # CLI参数解析

# 视频下载
yt-dlp>=2023.0.0       # 媒体下载

# Markdown处理
python-frontmatter>=1.0.0  # YAML Frontmatter解析
markdownify>=0.11.0        # HTML转Markdown

# 发布API
feishu-sdk>=1.0.0      # 飞书SDK（如有）

# 复用自PodFlow
openai-whisper>=20230314
whisperx>=3.0.0
sqlalchemy>=2.0.0
openai>=1.0.0
google-generativeai>=0.3.0
```

---

## 8. 风险与应对

| 风险 | 影响 | 应对措施 |
| --- | --- | --- |
| WhisperX 转录时间长 | 用户体验差 | 实时进度条 + 断点续传 |
| AI API 成本高 | Token消耗大 | Patch Mode + 缓存 |
| yt-dlp 视频源失效 | 无法下载 | 错误提示 + 手动上传支持 |
| Markdown 格式污染 | 数据库被破坏 | 格式校验 + 回滚机制 |
| 飞书/IMA API变动 | 分发失败 | 抽象接口 + 降级处理 |

---

## 9. 测试策略

### 单元测试

- `StateMachine`：状态转移逻辑
- `SemanticService`：章节切分 Mock 测试
- `MarkdownService`：渲染输出验证

### 集成测试

- 完整流程：URL → Obsidian 文档
- 断点续传：模拟中断后恢复
- 发布流程：Markdown 解析 → 数据库回填

### 测试数据

准备一个短视频（5分钟以内）作为标准测试素材。

---

## 10. 待确认事项

1. **视频源支持范围**：YouTube、Bilibili、播客RSS，是否需要其他？
2. **AI模型选择**：语义分析和翻译使用什么模型？
3. **飞书/IMA权限**：是否已有API访问权限？
4. **Obsidian Vault路径**：固定目录还是用户配置？
5. **Token预算**：预期的月度 Token 消耗上限？

---

**文档结束** | 请审核后反馈修改意见
