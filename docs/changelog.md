# Changelog

记录项目的重要变更和更新。

---

## 2026-02-12

### Fix - 营销文案兜底改用章节小结

**问题:** 兜底逻辑使用 `episode.ai_summary`，但该字段在数据库中常为空；日志显示 AI 已生成内容，但 Obsidian 文件仍为 fallback。

**修改文件:**
- `backend/app/services/marketing_service.py` - 新增 `_get_chapter_summaries()`，兜底内容改为所有章节 `summary` 拼接；无章节或全空则用 `episode.title`
- `backend/tests/unit/services/test_marketing_fallback.py` - 更新用例以适配章节小结兜底逻辑

---

### Feat - 按场景配置 Temperature

**修改文件:**
- `backend/config.yaml` - 新增 `ai.temperature` 配置块
- `backend/app/config.py` - 新增 4 个 temperature 常量
- `backend/app/services/segmentation_service.py` - 传入 `AI_TEMPERATURE_SEGMENTATION`
- `backend/app/services/subtitle_proofreading_service.py` - 传入 `AI_TEMPERATURE_PROOFREADING`
- `backend/app/services/translation_service.py` - 用 `AI_TEMPERATURE_TRANSLATION` 替代硬编码 0.3
- `backend/app/services/marketing_service.py` - 用 `AI_TEMPERATURE_MARKETING` 替代硬编码 0.7/0.8

**参考:** `docs/phase-planning/temperature-config-code-review.md`

**配置说明:**
- `segmentation: 0` - 章节划分需确定性
- `proofreading: 0` - 字幕校对需准确
- `translation: 0.3` - PRD 已规定
- `marketing: 0.8` - 营销文案需一定创意

---

## 2026-02-08

### Fixed - TranslationService 边界情况修复

**修改文件:**
- `app/services/translation_service.py` - 修复边界情况处理
- `app/services/ai/schemas/translation_schema.py` - 添加空白字符验证
- `tests/unit/services/test_translation_service_edge_cases.py` - 新增边界情况测试 (14 个测试)

**问题来源:**
- 基于 [translation-alignment-code-review.md](phase-planning/translation-alignment-code-review.md) 代码审查文档

**修复内容:**

1. **None 值处理** (High Priority)
   - 检测 AI 返回 content=None 情况
   - 抛出明确错误信息："AI 返回了空响应 (content=None)"
   - 防止 AttributeError 崩溃

2. **空白翻译验证** (High Priority)
   - Schema 层：添加 `validate_not_blank` 验证器
   - Service 层：`_create_translation` 方法验证非空
   - 防止空白字符串被保存为翻译内容

3. **翻译长度截断** (Medium Priority)
   - 限制最大翻译长度为 10,000 字符
   - 超长翻译自动截断并记录警告日志

4. **错位重复 cue_id 检查** (High Priority)
   - 检测错位修复时是否产生重复 cue_id
   - 拒绝可能存在双重错位的批次
   - 抛出 ValueError："修复错位时发现重复 cue_id"

5. **重试优化** (Medium Priority)
   - 只重试失败的条目，避免重复翻译已成功的内容
   - 记录已成功的 cue_id，重试时跳过
   - 改进日志显示进度

6. **fallback 数据丢失保护** (Medium Priority)
   - 移除 `rollback()` 调用
   - 依赖 `_create_translation` 的 UPDATE 逻辑
   - 确保部分保存的数据不会丢失

7. **异常状态残留保护** (Medium Priority)
   - `_call_ai_for_batch` 异常时执行 `rollback()`
   - 清理未提交的数据，避免状态不一致

8. **Prompt 格式优化** (Low Priority)
   - JSON 使用紧凑格式 `separators=(',', ':')`
   - 减少 prompt 长度，降低 API 调用成本

**测试覆盖:**
- 14 个边界情况测试全部通过
- 测试覆盖：None 值处理、空字符串验证、长度截断、重复检测、重试优化、异常清理

**影响范围:**
- `translation_service.py:619` - None 值处理
- `translation_service.py:421-466` - 空字符串验证和长度截断
- `translation_service.py:1040-1045` - 错位重复检测
- `translation_service.py:253-314` - 重试优化
- `translation_service.py:246-249` - fallback 数据丢失保护
- `translation_service.py:959-961` - 异常状态残留保护
- `translation_service.py:910` - Prompt 格式优化
- `translation_schema.py:28-35` - Schema 空白字符验证

---

## 2026-02-07

### Refactor - AI 服务迁移到 StructuredLLM 系统

**修改文件:**
- `app/services/subtitle_proofreading_service.py` - 迁移到 StructuredLLM
- `app/services/segmentation_service.py` - 迁移到 StructuredLLM
- `tests/unit/services/test_subtitle_proofreading_service.py` - 更新测试适配新 API

**功能特性:**
1. **SubtitleProofreadingService 迁移**
   - 移除 dataclass `CorrectionSuggestion`，使用 Pydantic 模型
   - 使用 `StructuredLLM` 替代直接 OpenAI API 调用
   - 添加 `ProofreadingValidator` 业务验证器
   - 添加 `@ai_retry` 装饰器实现自动重试
   - 支持多提供商 (moonshot, zhipu, gemini)

2. **SegmentationService 迁移**
   - 移除 JSON 解析逻辑，使用 Pydantic `SegmentationResponse`
   - 使用 `StructuredLLM` 替代直接 OpenAI API 调用
   - 添加 `SegmentationValidator` 业务验证器
   - 添加 `@ai_retry` 装饰器实现自动重试
   - 支持多提供商 (moonshot, zhipu, gemini)

**测试结果:**
- SubtitleProofreadingService: 13/13 tests passing
- SegmentationService: 9/9 tests passing

**待完成 (P2 优先级):**
- TranslationService 迁移到 StructuredLLM
- MarketingService 迁移到 StructuredLLM

---

## 2026-02-07

### Added - AI 结构化输出系统 (Provider 适配器模式)

**新增文件:**
- `app/services/ai/structured_llm.py` - 统一结构化输出包装器
- `app/services/ai/structured_output_config.py` - Provider 配置
- `app/services/ai/providers/base_provider.py` - Provider 适配器基类
- `app/services/ai/providers/moonshot_provider.py` - Moonshot (Kimi) 适配器
- `app/services/ai/providers/zhipu_provider.py` - Zhipu (GLM) 适配器
- `app/services/ai/providers/gemini_provider.py` - Gemini 适配器
- `app/services/ai/providers/__init__.py` - Provider 注册表和工厂函数
- `app/services/ai/retry.py` - AI 调用重试装饰器
- `app/services/ai/schemas/proofreading_schema.py` - 校对服务 Pydantic 模型
- `app/services/ai/schemas/segmentation_schema.py` - 章节分析 Pydantic 模型
- `app/services/ai/schemas/marketing_schema.py` - 营销文案 Pydantic 模型
- `app/services/ai/schemas/translation_schema.py` - 翻译服务 Pydantic 模型
- `app/services/ai/schemas/__init__.py` - Schema 模块导出
- `app/services/ai/validators/proofreading_validator.py` - 校对业务验证器
- `app/services/ai/validators/segmentation_validator.py` - 章节分析业务验证器
- `app/services/ai/validators/__init__.py` - 验证器模块导出
- `scripts/test_provider_json_mode.py` - Provider JSON Mode 测试脚本
- `scripts/test_langchain_structured_output.py` - LangChain 适配器测试脚本
- `scripts/test_structured_output_integration.py` - 完整系统集成测试

**修改文件:**
- `requirements.txt` - 添加 LangChain 相关依赖

**功能特性:**
1. **Provider 适配器模式**
   - 抽象基类 `BaseProviderAdapter` 定义统一接口
   - 每个提供商有独立的适配器实现
   - 工厂模式 + 注册表支持动态扩展新提供商
   - 当前支持: Moonshot (Kimi), Zhipu (GLM), Gemini

2. **StructuredLLM 统一包装器**
   - 自动检测 Provider 能力 (native vs json_mode)
   - 一致的调用接口 across 所有提供商
   - Pydantic 验证失败抛出异常，触发上游重试逻辑

3. **重试装饰器 (`@ai_retry`)**
   - 指数退避重试策略
   - 可配置最大重试次数、初始延迟、退避因子
   - 结构化日志记录便于调试

4. **Pydantic Schema 模型**
   - 所有 4 个 AI 服务都有严格的 Schema 定义
   - 字段类型约束 (长度、范围、格式)
   - 自定义验证器 (如唯一性、时间范围)

5. **业务逻辑验证器**
   - 校对服务: cue_id 范围检查、置信度警告
   - 章节分析: 时间范围检查、重叠检测

**架构设计:**
- **无 `prompt_only` 兜底** - 依赖验证失败 → 重试 → 降级策略
- **JSON Mode** (Kimi/Zhipu): `response_format={"type": "json_object"}` + Pydantic
- **Native Mode** (Gemini): `with_structured_output()` 自动验证

**测试验证:**
- Kimi JSON Mode 测试: 通过
- Zhipu JSON Mode 测试: 通过
- Gemini Native Mode 测试: 通过
- 业务验证器测试: 完成
- 重试装饰器测试: 完成

**扩展新 Provider 步骤:**
1. 创建适配器类继承 `BaseProviderAdapter`
2. 使用 `register_provider()` 注册
3. 更新 `PROVIDER_CONFIGS` 添加配置
4. 添加环境变量中的 API Key

---

## 2026-02-06

### Refactor - 营销服务 LLM 配置解耦

**修改文件:**
- `app/config.py` - 添加 `MARKETING_LLM_PROVIDER` 配置和 `get_marketing_llm_config()` 辅助函数
- `app/services/marketing_service.py` - 重构 LLM 调用，使用解耦配置
- `config.yaml` - 添加 `ai.marketing.provider` 配置项（默认: zhipu）

**功能特性:**
1. **营销服务 LLM Provider 解耦**
   - 营销服务现在可以通过 `config.yaml` 动态切换 LLM 提供商
   - 支持的提供商: zhipu (智谱 GLM), moonshot (Kimi), gemini
   - 默认使用 Zhipu GLM (glm-4-plus) 用于营销文案生成

2. **配置方式**
   - 修改 `config.yaml` 中的 `ai.marketing.provider` 即可切换
   - API Key 从环境变量动态获取，不硬编码

3. **向后兼容**
   - 保持 `MarketingService.__init__()` 签名不变
   - 所有现有调用无需修改

**测试验证:**
- 所有单元测试通过 (14/14 passed)

---

## 2026-02-06

### Added - Phase 6 API 层实现 (REST API)

**新增文件:**
- `app/main.py` - FastAPI 主入口，配置 CORS 和全局异常处理
- `app/schemas/episode.py` - Episode Pydantic 模型 (Create, Update, Response, ListResponse)
- `app/schemas/transcript.py` - TranscriptCue Pydantic 模型
- `app/schemas/translation.py` - Translation Pydantic 模型
- `app/schemas/chapter.py` - Chapter Pydantic 模型
- `app/schemas/marketing.py` - MarketingPost Pydantic 模型
- `app/schemas/publication.py` - PublicationRecord Pydantic 模型
- `app/api/episodes.py` - Episodes API 路由 (CRUD + 工作流触发)
- `app/api/transcripts.py` - Transcripts API 路由 (字幕查询)
- `app/api/translations.py` - Translations API 路由 (翻译修正)
- `app/api/chapters.py` - Chapters API 路由 (章节查询)
- `app/api/marketing.py` - Marketing API 路由 (营销文案生成)
- `app/api/publications.py` - Publications API 路由 (发布状态)

**功能特性:**
1. **Episodes API** - Episode CRUD 操作
   - POST `/api/v1/episodes` - 创建 Episode（自动去重）
   - GET `/api/v1/episodes` - 获取列表（分页、状态过滤）
   - GET `/api/v1/episodes/{id}` - 获取详情
   - PATCH `/api/v1/episodes/{id}` - 更新 Episode
   - DELETE `/api/v1/episodes/{id}` - 删除 Episode
   - POST `/api/v1/episodes/{id}/run` - 触发主工作流（后台执行）
   - POST `/api/v1/episodes/{id}/publish` - 触发发布流程（后台执行）

2. **Transcripts API** - 字幕查询
   - GET `/api/v1/episodes/{id}/transcripts` - 获取字幕列表（中英对照）
   - GET `/api/v1/cues/{cue_id}` - 获取单条字幕
   - GET `/api/v1/cues/{cue_id}/effective-text` - 获取有效文本（修正后或原始）

3. **Translations API** - 翻译修正
   - GET `/api/v1/translations/{id}` - 获取翻译详情
   - PATCH `/api/v1/translations/{id}` - 修正翻译（自动设置 RLHF 标记）
   - POST `/api/v1/episodes/{id}/translations/batch-translate` - 批量翻译

4. **Chapters API** - 章节查询
   - GET `/api/v1/episodes/{id}/chapters` - 获取章节列表
   - GET `/api/v1/chapters/{id}` - 获取章节详情
   - GET `/api/v1/chapters/{id}/cues` - 获取章节字幕

5. **Marketing API** - 营销文案
   - GET `/api/v1/episodes/{id}/marketing-posts` - 获取营销文案列表
   - POST `/api/v1/episodes/{id}/marketing-posts/generate` - 生成营销文案
   - GET `/api/v1/marketing-posts/{id}` - 获取单条营销文案

6. **Publications API** - 发布状态
   - GET `/api/v1/episodes/{id}/publication-status` - 获取发布状态
   - GET `/api/v1/publications/{id}` - 获取发布记录
   - POST `/api/v1/publications/{id}/retry` - 重试发布

**技术细节:**
- 使用 Pydantic v2 进行请求/响应验证
- FastAPI BackgroundTasks 处理长时间运行任务
- 全局异常处理（数据库错误、值错误、通用错误）
- CORS 配置支持跨域访问
- Swagger UI 自动文档 (`/docs`)
- ReDoc 备选文档 (`/redoc`)

**API 端点统计:**
- Episodes: 7 个端点
- Transcripts: 3 个端点
- Translations: 3 个端点
- Chapters: 3 个端点
- Marketing: 3 个端点
- Publications: 3 个端点
- **总计: 22 个 API 端点**

**测试完成:**
- API 单元测试 (54 个测试)
- API 集成测试 (17 个测试, 8 个通过)

**待完成:**
- 修复剩余 9 个集成测试（session 隔离问题）

---

## 2026-02-06

### Added - 跨平台显示标题回退机制

**新增文件:**
- `app/utils/title_utils.py` - 跨平台标题清理工具
- `app/services/episode_service.py` - Episode 业务逻辑服务
- `app/services/chapter_service.py` - Chapter 业务逻辑服务
- `tests/unit/utils/test_title_utils.py` - 标题清理工具测试 (15 个测试)
- `tests/unit/services/test_episode_service.py` - EpisodeService 测试 (11 个测试)
- `tests/unit/services/test_chapter_service.py` - ChapterService 测试 (9 个测试)

**修改文件:**
- `app/models/episode.py` - 添加 `display_title` @property
- `app/models/chapter.py` - 添加 `display_title` 方法
- `app/services/publishers/notion.py` - 使用 `display_title` 发布到 Notion
- `app/services/obsidian_service.py` - 使用 `display_title` 生成 Obsidian Markdown

**功能特性:**
1. **跨平台兼容** - 标题在 Obsidian (Markdown) 和 Notion (API) 中正确显示
2. **智能回退策略**:
   - Episode: title → show_name → audio_path → source_url → id
   - Chapter: title → time_range → index → episode_title
3. **标题清理**:
   - 移除换行符和多余空格
   - 限制长度 (100 字符，超长截断 + "...")
   - 保留原始特殊字符（由各平台渲染时处理转义）

**测试覆盖:**
- 35 个单元测试全部通过
- 测试覆盖场景：原始标题、回退策略、跨平台兼容性、边界情况

---

## 2026-02-06

### Fixed - NotionPublisher 渲染和导航问题

**修改文件:**
- `app/services/publishers/notion.py`
- `tests/unit/services/test_notion_publisher.py`

**问题 1 - 章节导航 callout 加粗失效:**
- 原因：Notion API 不会解析单个 `text` 对象中 `content` 里的 markdown `**` 语法
- 修复：使用 `rich_text` 数组 + `annotations.bold` 属性实现正确的加粗渲染

**问题 2 - 章节导航 callout 背景颜色:**
- 原因：使用 `gray_background` 与 speaker 标题颜色不一致
- 修复：改为 `blue_background` 保持视觉一致性

**问题 3 - 字幕 callout 时间戳加粗失效:**
- 原因：同问题 1，markdown 语法不被解析
- 修复：时间戳使用独立的 `text` 对象 + `annotations.bold: true`

**问题 4 - 底部章节导航跳转重新打开页面:**
- 原因：`https://notion.so/{page_id}#{block_id}` 被当作外部链接
- 修复：使用 `https://www.notion.so/{clean_block_id}#` block 直接链接格式

**测试:**
- 更新现有测试以验证新的 `annotations.bold` 渲染方式
- 所有 27 个单元测试通过

---

## 2026-02-05

### Added - SubtitleProofreadingService (字幕校对服务)

**新增文件:**
- `app/models/transcript_correction.py` - 字幕修正记录模型
- `app/services/subtitle_proofreading_service.py` - 核心服务实现
- `tests/unit/models/test_transcript_correction.py` - 模型单元测试

**功能特性:**
1. **LLM 扫描校对** (`scan_and_correct`) - 使用 LLM 扫描 Whisper 转录结果，识别错误
2. **批次处理** - 支持批次处理大量字幕，避免 API 超时
3. **本地替换** - 在本地数据库应用修正，不保存完整重复文本
4. **断点续传** - 跳过已校对的字幕 (is_corrected=True)，支持中断恢复
5. **修正记录** - 保留修正历史，用于训练数据收集

**数据模型变更:**
- `TranscriptCorrection` (新增) - 存储字幕修正记录
  - cue_id, original_text, corrected_text, reason, confidence, ai_model, applied
- `TranscriptCue` 扩展 - 添加 `corrected_text` 和 `is_corrected` 字段
  - 新增 `effective_text` 属性：优先返回 corrected_text
- `Episode` 扩展 - 添加 `proofread_status` 和 `proofread_at` 字段

**工作流变更:**
- `WorkflowStatus` 枚举新增 `3: PROOFREAD` 状态
- 原状态 3-7 依次后移 (SEGMENTED: 3→4, ..., PUBLISHED: 6→7)

**使用示例:**
```python
from app.database import get_session
from app.services.subtitle_proofreading_service import SubtitleProofreadingService

with get_session() as db:
    service = SubtitleProofreadingService(db, llm_service=None)

    # 扫描并自动应用修正
    result = service.scan_and_correct(
        episode_id=1,
        batch_size=50,
        apply=True
    )

    print(f"总字幕数: {result.total_cues}")
    print(f"修正数量: {result.corrected_count}")
```

**状态:** 核心实现完成，待测试验证

---

### Planned - SubtitleProofreadingService (计划中)

**计划文档:**
- `docs/phase-planning/subtitle-proofreading-plan.md` - 详细开发计划

**功能特性 (计划中):**
1. **LLM 扫描校对** (`scan_and_correct`) - 使用 LLM 扫描 Whisper 转录结果，识别错误
2. **批次处理** - 支持批次处理大量字幕，避免 API 超时
3. **本地替换** - 在本地数据库应用修正，不保存完整重复文本
4. **断点续传** - 跳过已校对的字幕，支持中断恢复
5. **修正记录** - 保留修正历史，用于训练数据收集

**数据模型 (计划中):**
- `TranscriptCorrection` - 新增模型，存储字幕修正记录
- `TranscriptCue` 扩展 - 添加 `corrected_text` 和 `is_corrected` 字段
- `Episode` 扩展 - 添加 `proofread_status` 和 `proofread_at` 字段

**工作流变更:**
- 新增状态: `3: PROOFREAD` (在 TRANSCRIBED 之后，SEGMENTED 之前)
- 原状态 3-6 依次后移

**预计工时:** 8 小时

---

### Added - MarketingService (小红书风格营销文案生成服务)

### Added - MarketingService (小红书风格营销文案生成服务)

**新增文件:**
- `app/services/marketing_service.py` - 核心服务实现
- `tests/unit/services/test_marketing_service.py` - 14 个单元测试
- `tests/integration/test_marketing_integration.py` - 5 个集成测试
- `scripts/test_marketing_with_real_data.py` - 真实数据测试脚本

**功能特性:**
1. **金句提取** (`extract_key_quotes`) - 从 Episode.ai_summary 和 TranscriptCue 中提取关键句
2. **标题生成** (`generate_titles`) - 使用 LLM 生成多个吸引人的标题（带 emoji）
3. **标签生成** (`generate_hashtags`) - 生成相关的话题标签（带 # 前缀）
4. **小红书文案生成** (`generate_xiaohongshu_copy`) - 生成完整的小红书风格营销文案
   - 包含 "宝子们" 亲切开头
   - 使用 emoji 和项目符号
   - 结尾包含 CTA（点赞收藏关注）
5. **文案持久化** (`save_marketing_copy` / `load_marketing_copy`) - 保存和加载营销文案

**数据模型:**
- 复用现有 `MarketingPost` 模型（`app/models/marketing_post.py`）
- 支持 `episode_id`、`chapter_id` 外键
- 支持 `platform`（平台）和 `angle_tag`（角度标签）字段

**测试结果:**
- 单元测试: 14/14 通过
- 集成测试: 5/5 通过
- 总计: 19 个测试全部通过

**使用示例:**
```python
from app.services.marketing_service import MarketingService

service = MarketingService(db, llm_service=None)

# 生成小红书文案
marketing_copy = service.generate_xiaohongshu_copy(episode_id)

# 保存到数据库
post = service.save_marketing_copy(
    episode_id=episode_id,
    copy=marketing_copy,
    platform="xhs",
    angle_tag="AI干货向"
)
```

---

## 2026-02-04

### Added - ObsidianService (Obsidian 文档生成和解析服务)

**新增文件:**
- `app/services/obsidian_service.py` - 核心服务实现
- `tests/unit/services/test_obsidian_service.py` - 24 个单元测试
- `tests/integration/test_obsidian_integration.py` - 7 个集成测试
- `scripts/test_obsidian_with_real_data.py` - 真实数据测试脚本

**功能特性:**
1. **Markdown 渲染** (`render_episode`) - 从数据库生成 Obsidian Markdown 文档
2. **文档保存** (`save_episode`) - 保存 Markdown 文件到 Obsidian Vault
3. **文档解析** (`parse_episode_from_markdown`) - 解析 Markdown 并检测翻译修改
4. **回填更新** (`parse_and_backfill_from_markdown`) - 回填用户编辑到数据库

**Cue 区块格式:**
```
[00:00](cue://1454)
**英文**: English text...
**中文**: 中文翻译...
```

**测试结果:**
- 单元测试: 24/24 通过
- 集成测试: 7/7 通过
- 总计: 31 个测试全部通过

---

## 更新日志格式说明

```markdown
## YYYY-MM-DD

### Type - Brief Description

**Files:**
- List of files modified or created

**Features:**
- Feature 1
- Feature 2

**Bug Fixes:**
- Bug fix 1
- Bug fix 2

**Tests:**
- Test results summary

**Breaking Changes:**
- Any breaking changes (if applicable)
```

### Type 类型说明
- **Added**: 新功能
- **Changed**: 功能变更
- **Deprecated**: 即将废弃的功能
- **Removed**: 已移除的功能
- **Fixed**: Bug 修复
- **Security**: 安全相关修复
