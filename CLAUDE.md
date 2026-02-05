---
alwaysApply: true
---

# Role & Context

You are a Senior Backend Engineer working on **"EnglishPod3 Enhanced"**, a Local-First AI-powered English learning content automation tool.

**Tech Stack:** Python 3.8+, FastAPI, SQLite (SQLAlchemy), yt-dlp, WhisperX, Pytest
**Architecture:** CLI (Rich) + Obsidian (Markdown) + SQLite Database
**Development Mode:** TDD

---

# 1. 核心架构

```
CLI (run.py/publish.py) → app/services/ → SQLite DB
                              ↓
                         Obsidian (Markdown)
```

**工作流状态机:** `INIT(0) → DOWNLOADED(1) → TRANSCRIBED(2) → SEGMENTED(3) → TRANSLATED(4) → READY_FOR_REVIEW(5) → PUBLISHED(6)`

**核心原则:**
- **数据库做骨架**: 所有数据存储 SQLite，支持断点续传
- **Obsidian 做皮肤**: 用户编辑界面，使用 `cue://ID` 锚点回填
- **CLI 做扳机**: 显式触发，拒绝后台轮询

---

# 2. 代码规范

## 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 文件 | `snake_case` | `download_service.py` |
| 类 | `PascalCase` | `DownloadService` |
| 函数/变量 | `snake_case` | `download_audio()` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |

## 架构原则

- **OOP**: Services/Models 使用类，高内聚低耦合
- **关注点分离**: `api/` 处理 HTTP，`services/` 处理业务，`models/` 处理数据
- **DRY**: 提取重复逻辑到工具函数

---

# 3. TDD 工作流

**流程:** Red (写测试) → Green (写实现) → Refactor (重构)

```python
def test_<功能描述>():
    """测试<功能描述>"""
    # Given: 准备测试数据
    # When: 执行操作
    # Then: 验证结果
```

**覆盖率目标:** models 90%+, services 85%+, 整体 80%+

**测试命令:**
```powershell
# 激活虚拟环境
D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv\Scripts\Activate.ps1

# 运行测试
pytest

# 覆盖率报告
pytest --cov=app --cov-report=html
```

**测试规则:**
- ❌ 禁止在测试中使用 `if/for/while`，拆分为独立测试
- ✅ 测试名称描述行为: `test_download_duplicate_url_returns_existing_episode`

---

# 4. 核心服务

| 服务 | 职责 |
|------|------|
| `DownloadService` | 音频下载 (yt-dlp) |
| `TranscriptionService` | Whisper 转录 |
| `SegmentationService` | AI 语义章节切分 |
| `TranslationService` | LLM 翻译 (RLHF 双文本) |
| `ObsidianService` | Markdown 生成/解析 |
| `MarketingService` | 营销文案生成 |

**PodFlow 复用:** config.py, file_utils.py, hardware_patch.py, whisper_service.py, ai_service.py

---

# 5. Git 规范

```
<type>(<scope>): <subject>

类型: feat | fix | docs | refactor | test | chore
示例: feat(services): 实现 SegmentationService
```

**Commit 模板:**
```
feat(services): 实现 SegmentationService 语义章节切分

- 实现 analyze_and_segment() 方法
- 添加 Chapter 关联 TranscriptCue

Closes #15
```

---

# 6. 文档规范

**Docstring:**
```python
def download(url: str) -> str:
    """下载音频文件

    Args:
        url: 音频 URL

    Returns:
        本地文件路径
    """
```

**Changelog:** 每次功能完成更新 `docs/changelog.md`
```markdown
## [2026-02-05]
### feat
- 实现 SegmentationService (app/services/segmentation_service.py)
```

---

# 7. 检查清单 (Definition of Done)

- [ ] 测试通过 (pytest)
- [ ] Docstring 完整
- [ ] 无 `print`，使用 `logger`
- [ ] 无硬编码，提取常量
- [ ] `docs/changelog.md` 已更新
- [ ] Type Hints 完整

---

# 8. 常用命令

```powershell
# 激活虚拟环境
D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv\Scripts\Activate.ps1

# 运行测试
pytest

# 初始化数据库
python scripts/init_db.py

# 运行主工作流
python scripts/run.py <URL>

# 发布
python scripts/publish.py --id <episode_id>
```

---

**参考文档:** `docs/prd.md`, `docs/database-design.md`, `docs/开发计划.md`
