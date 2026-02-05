# Pre-analysis: PodFlow 核心逻辑分析与数据库复用方案

| 文档版本 | V1.0 |
| --- | --- |
| **日期** | 2026-02-04 |
| **状态** | 待审核 |
| **目的** | 深度分析 PodFlow 核心逻辑，明确复用方案和数据库修改点 |

---

## 目录

1. [PodFlow 核心逻辑分析](#1-podflow-核心逻辑分析)
2. [数据库模型复用方案](#2-数据库模型复用方案)
3. [服务层复用方案](#3-服务层复用方案)
4. [状态机扩展设计](#4-状态机扩展设计)
5. [数据库字段变更清单](#5-数据库字段变更清单)

---

## 1. PodFlow 核心逻辑分析

### 1.1 虚拟分段机制 (Virtual Segmentation)

**核心设计理念**：不切割物理文件，只记录时间范围，按需提取音频片段。

#### AudioSegment 模型分析

```python
# 源文件: backend/app/models.py, 行 349-445

class AudioSegment(Base):
    """
    音频虚拟分段模型

    核心特性：
    1. 虚拟分段：只记录时间范围（start_time, end_time），不切割物理文件
    2. 临时文件管理：segment_path 字段记录临时文件路径，生命周期管理
    3. 重试机制：失败时保留临时文件，重试时直接使用
    4. 中断恢复：服务器重启后，可根据 segment_path 继续转录
    """
```

#### segment_path 生命周期

| 状态 | segment_path 值 | 说明 |
| --- | --- | --- |
| **pending** | `NULL` | 未提取音频 |
| **processing** | `/path/to/segment_xxx.wav` | FFmpeg 提取后的临时文件路径 |
| **completed** | `NULL` | 临时文件已删除 |
| **failed** | `/path/to/segment_xxx.wav` | 保留临时文件用于重试 |

#### 关键代码片段

```python
# 源文件: backend/app/services/transcription_service.py, 行 172-197

# Step 1: 检查是否已有临时文件（重试场景）
if segment.segment_path and os.path.exists(segment.segment_path):
    temp_path = segment.segment_path
    logger.info(f"使用已有临时文件: {temp_path} (重试场景)")
else:
    # Step 2: 使用 FFmpeg 提取片段
    temp_path = self.whisper_service.extract_segment_to_temp(
        audio_path=episode.audio_path,
        start_time=segment.start_time,
        duration=segment.end_time - segment.start_time
    )
    # 更新 segment_path（用于中断恢复）
    segment.segment_path = temp_path
    self.db.commit()
```

#### FFmpeg 提取逻辑

```python
# 源文件: backend/app/services/whisper_service.py, 行 325-377

def extract_segment_to_temp(
    self,
    audio_path: str,
    start_time: float,
    duration: float,
    output_dir: Optional[str] = None
) -> str:
    """
    使用 FFmpeg 提取音频片段到临时文件

    关键参数：
    - -ss: 开始时间
    - -t: 持续时长
    - -ar 16000: 采样率（Whisper 要求）
    - -ac 1: 单声道
    - -c:a pcm_s16le: PCM 编码（确保精确切割）
    """
    subprocess.run([
        "ffmpeg", "-y",
        "-i", audio_path,
        "-ss", str(start_time),
        "-t", str(duration),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        temp_path
    ], check=True)
```

---

### 1.2 异步转录流程 (Async Transcription)

#### TranscriptionService 核心方法

| 方法 | 功能 | 复用程度 |
| --- | --- | --- |
| `create_virtual_segments()` | 为 Episode 创建虚拟分段 | **完全复用** |
| `transcribe_virtual_segment()` | 转录单个分段，支持中断恢复 | **完全复用** |
| `save_cues_to_db()` | 保存字幕，计算绝对时间 | **需要修改**（新增 translation 字段） |
| `sync_episode_transcription_status()` | 同步 Episode 状态 | **需要扩展**（新增状态枚举） |
| `segment_and_transcribe()` | 完整流程：创建分段 + 按顺序转录 | **完全复用** |

#### 绝对时间计算逻辑

```python
# 源文件: backend/app/services/transcription_service.py, 行 271-332

def save_cues_to_db(self, cues: List[Dict], segment: AudioSegment) -> int:
    """
    保存字幕到数据库（无 cue_index 方案，使用绝对时间）

    计算绝对时间: start_time = segment.start_time + cue['start']
    不存储 cue_index，使用 start_time 排序
    """
    for cue in cues:
        # 计算绝对时间（相对于原始音频）
        absolute_start = segment.start_time + cue["start"]
        absolute_end = segment.start_time + cue["end"]

        transcript_cue = TranscriptCue(
            episode_id=segment.episode_id,
            segment_id=segment.id,
            start_time=absolute_start,  # 绝对时间
            end_time=absolute_end,      # 绝对时间
            speaker=cue.get("speaker", "Unknown"),
            text=cue.get("text", "").strip()
        )
```

**设计亮点**：
- 使用绝对时间（相对于原始音频），而非相对时间
- 查询时使用 `ORDER BY start_time ASC` 获得正确顺序
- 完全解决异步转录的关联问题

---

### 1.3 状态机设计 (State Machine)

#### AudioSegment 状态

| 状态 | 说明 |
| --- | --- |
| `pending` | 等待转录 |
| `processing` | 正在转录中 |
| `completed` | 转录完成 |
| `failed` | 转录失败 |

#### Episode 状态

| 状态 | 计算逻辑 |
| --- | --- |
| `pending` | 初始状态，无 Segment |
| `processing` | 有 processing 或 pending 的 Segment |
| `completed` | 所有 Segment 都是 completed |
| `partial_failed` | 有 completed 也有 failed，无 processing/pending |
| `failed` | 所有 Segment 都是 failed |

#### 状态同步逻辑

```python
# 源文件: backend/app/services/transcription_service.py, 行 334-410

def sync_episode_transcription_status(self, episode_id: int) -> None:
    """
    同步更新 Episode 的转录状态（基于所有 Segment 的状态）

    状态判断逻辑：
    - 所有 Segment 都 completed → Episode.status = "completed"
    - 有 completed 也有 failed，没有 processing/pending → Episode.status = "partial_failed"
    - 所有 Segment 都 failed → Episode.status = "failed"
    - 有 processing 或 pending → Episode.status = "processing"
    """
    completed_count = sum(1 for s in segments if s.status == "completed")
    failed_count = sum(1 for s in segments if s.status == "failed")
    processing_count = sum(1 for s in segments if s.status == "processing")
    pending_count = sum(1 for s in segments if s.status == "pending")
```

---

### 1.3 翻译断点续传设计（新增）

#### 需求背景

调用 LLM 逐段翻译时，可能因以下原因中断：
- 网络错误/超时
- API 限流（Rate Limit）
- Token 超限
- 服务端错误（5xx）

需要保证：
1. 记录哪些 cue 已翻译完成
2. 记录哪些 cue 翻译失败
3. 支持跳过已完成的 cue，只翻译未完成的
4. 支持失败重试，且有重试次数限制

#### TranscriptCue 翻译状态字段

| 字段名 | 类型 | 说明 | 示例值 |
| --- | --- | --- | --- |
| `translation_status` | String | 翻译状态 | `"pending"` / `"processing"` / `"completed"` / `"failed"` |
| `translation` | Text | 中文翻译 | `"你好世界"` / `NULL` |
| `translation_error` | Text | 错误信息 | `"API rate limit exceeded"` / `NULL` |
| `translation_retry_count` | Integer | 重试次数 | `0` / `1` / `2` |
| `translation_started_at` | DateTime | 翻译开始时间 | `2026-02-04 10:30:00` / `NULL` |
| `translation_completed_at` | DateTime | 翻译完成时间 | `2026-02-04 10:30:15` / `NULL` |

#### 翻译服务断点续传逻辑

```python
class TranslationService:
    """
    翻译服务（支持断点续传）

    设计理念：完全仿照 AudioSegment 的状态管理
    """

    def translate_episode(
        self,
        episode_id: int,
        batch_size: int = 50
    ) -> None:
        """
        批量翻译 Episode 的所有 TranscriptCue

        断点续传逻辑：
        1. 查询所有未完成的 cue（pending 或 failed）
        2. 按 batch_size 分批处理
        3. 每批处理前更新状态为 processing
        4. 调用 LLM API
        5. 成功则更新为 completed，失败则更新为 failed 并记录错误
        """
        # 查询未完成的 cue
        pending_cues = self.db.query(TranscriptCue).filter(
            TranscriptCue.episode_id == episode_id,
            TranscriptCue.translation_status.in_(["pending", "failed"])
        ).order_by(TranscriptCue.start_time).all()

        logger.info(
            f"[TranslationService] Episode {episode_id} "
            f"待翻译 cue 数量: {len(pending_cues)}"
        )

        # 分批处理
        for i in range(0, len(pending_cues), batch_size):
            batch = pending_cues[i:i + batch_size]

            try:
                # 批量调用 LLM
                translations = self._call_llm_batch(batch)

                # 更新状态
                for cue, translation in zip(batch, translations):
                    cue.translation = translation
                    cue.translation_status = "completed"
                    cue.translation_error = None
                    cue.translation_completed_at = datetime.utcnow()

                self.db.commit()

                logger.info(
                    f"[TranslationService] 批次 {i//batch_size + 1} 完成，"
                    f"翻译了 {len(batch)} 条 cue"
                )

            except Exception as e:
                # 批次失败，标记所有 cue 为 failed
                for cue in batch:
                    cue.translation_status = "failed"
                    cue.translation_error = str(e)
                    cue.translation_retry_count += 1

                self.db.commit()

                logger.error(
                    f"[TranslationService] 批次 {i//batch_size + 1} 失败: {e}"
                )

                # 根据错误类型决定是否继续
                if self._is_fatal_error(e):
                    break  # 致命错误，停止处理
                # 否则继续下一批次

    def _call_llm_batch(
        self,
        cues: List[TranscriptCue]
    ) -> List[str]:
        """
        调用 LLM API 批量翻译

        支持重试：指数退避策略
        """
        # 实现 LLM 调用逻辑
        pass

    def _is_fatal_error(self, error: Exception) -> bool:
        """
        判断是否为致命错误

        致命错误：API Key 无效、余额不足等
        非致命错误：网络超时、限流等
        """
        # 实现错误类型判断
        pass
```

#### 翻译批次状态同步

```python
def sync_translation_status(self, episode_id: int) -> None:
    """
    同步 Episode 的翻译状态（基于所有 TranscriptCue 的状态）

    类似 AudioSegment 的状态同步逻辑
    """
    cues = self.db.query(TranscriptCue).filter(
        TranscriptCue.episode_id == episode_id
    ).all()

    if not cues:
        return

    completed_count = sum(1 for c in cues if c.translation_status == "completed")
    failed_count = sum(1 for c in cues if c.translation_status == "failed")
    processing_count = sum(1 for c in cues if c.translation_status == "processing")
    pending_count = sum(1 for c in cues if c.translation_status == "pending")
    total_count = len(cues)

    # 计算翻译进度
    progress = round((completed_count / total_count) * 100, 2)

    logger.info(
        f"[TranslationService] Episode {episode_id} 翻译进度: {progress}% "
        f"(completed={completed_count}, failed={failed_count}, "
        f"processing={processing_count}, pending={pending_count})"
    )

    return progress
```

#### 重试策略

| 重试次数 | 行为 |
| --- | --- |
| 0 | 首次翻译 |
| 1-2 | 自动重试（指数退避：1s, 2s, 4s...） |
| ≥3 | 标记为永久失败，需要人工介入 |

---

### 1.4 WhisperX 服务 (WhisperService)

#### 单例模型管理

```python
# 源文件: backend/app/services/whisper_service.py, 行 46-89

class WhisperService:
    """
    WhisperX 转录服务（单例模式）

    管理 Whisper 和 Diarization 模型的生命周期。
    """

    # Whisper 模型状态 (常驻)
    _model = None
    _device = None
    _compute_type = None

    # Diarization 模型状态 (按需常驻，需手动释放)
    _diarize_model = None

    # Alignment 模型状态 (缓存，避免重复加载)
    _align_model = None
    _align_metadata = None
    _align_language = None

    # 线程锁 (保护 GPU 推理操作)
    _gpu_lock = threading.RLock()
```

#### 模型加载策略

| 模型 | 加载时机 | 释放时机 |
| --- | --- | --- |
| **Whisper ASR** | 应用启动时 | 常驻不释放 |
| **Alignment** | 首次需要时 | 缓存，相同语言复用 |
| **Diarization** | Episode 处理开始前 | Episode 处理结束后 |

---

## 2. 数据库模型复用方案

### 2.1 Episode 表复用

#### 现有字段（PodFlow）

| 字段名 | 类型 | 说明 | 复用 |
| --- | --- | --- | --- |
| `id` | Integer | 主键 | ✅ |
| `podcast_id` | Integer | 外键 → Podcast | ❌ 删除 |
| `title` | String | 单集标题 | ✅ |
| `original_filename` | String | 原始文件名 | ❌ 改为 `source_url` |
| `original_path` | String | 原始路径 | ❌ 删除 |
| `audio_path` | String | 本地存储路径 | ✅ |
| `file_hash` | String | MD5 hash | ✅ |
| `file_size` | Integer | 文件大小 | ✅ |
| `duration` | Float | 时长（秒） | ✅ |
| `transcription_status` | String | 转录状态 | ⚠️ 改为 `workflow_status` |
| `language` | String | 语言代码 | ✅ |
| `created_at` | DateTime | 创建时间 | ✅ |
| `updated_at` | DateTime | 更新时间 | ✅ |

#### 新增字段（EnglishPod3 Enhanced）

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `source_url` | String | 原始 URL（YouTube/Bilibili 等） |
| `workflow_status` | Integer | 工作流状态（0-6，见状态机设计） |

#### 修改字段

| 原字段名 | 新字段名 | 原类型 | 新类型 | 说明 |
| --- | --- | --- | --- | --- |
| `transcription_status` | `workflow_status` | String (枚举) | Integer (枚举) | 扩展为 7 状态枚举 |

#### 删除字段

| 字段名 | 原因 |
| --- | --- |
| `podcast_id` | 新项目不需要 Podcast 概念 |
| `original_path` | 用 `source_url` 替代 |

---

### 2.2 AudioSegment 表复用

#### 完全复用（无需修改）

| 字段名 | 类型 | 说明 | 复用 |
| --- | --- | --- | --- |
| `id` | Integer | 主键 | ✅ |
| `episode_id` | Integer | 外键 → Episode | ✅ |
| `segment_index` | Integer | 段序号（0, 1, 2...） | ✅ |
| `segment_id` | String | 分段 ID（如 "segment_001"） | ✅ |
| `segment_path` | String | 临时文件路径 | ✅ |
| `start_time` | Float | 在原音频中的开始时间 | ✅ |
| `end_time` | Float | 在原音频中的结束时间 | ✅ |
| `status` | String | 识别状态 | ✅ |
| `error_message` | Text | 错误信息 | ✅ |
| `retry_count` | Integer | 重试次数 | ✅ |
| `transcription_started_at` | DateTime | 开始转录时间 | ✅ |
| `recognized_at` | DateTime | 识别完成时间 | ✅ |
| `created_at` | DateTime | 创建时间 | ✅ |

**说明**：AudioSegment 表完全复用，无需任何修改。虚拟分段机制是核心，必须保留。

---

### 2.3 TranscriptCue 表扩展

#### 现有字段（PodFlow）

| 字段名 | 类型 | 说明 | 复用 |
| --- | --- | --- | --- |
| `id` | Integer | 主键 | ✅ |
| `episode_id` | Integer | 外键 → Episode | ✅ |
| `segment_id` | Integer | 外键 → AudioSegment | ✅ |
| `start_time` | Float | 绝对时间 | ✅ |
| `end_time` | Float | 绝对时间 | ✅ |
| `speaker` | String | 说话人标识 | ✅ |
| `text` | String | 英文字幕文本 | ✅ |
| `created_at` | DateTime | 创建时间 | ✅ |

#### 新增字段（EnglishPod3 Enhanced）

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `chapter_id` | Integer | 关联章节 ID（外键 → Chapter，见下文） |

#### 设计说明

**翻译功能已移至独立的 Translation 表**，支持多语言扩展：
- 查看 [Translation 表设计](#23-translation-表新增) 了解详情
- TranscriptCue 只保留英文字幕原文，翻译数据通过 1:N 关联获取

---

### 2.4 Translation 表（新增）

**说明**: 存储多语言翻译，支持无限扩展和断点续传

#### 字段列表

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `id` | Integer | 主键 |
| `cue_id` | Integer | 外键 → TranscriptCue |
| `language_code` | String(10) | 语言代码（'zh', 'ja', 'fr'...） |
| `text` | Text | 翻译文本 |
| `translation_status` | String | 翻译状态（pending/processing/completed/failed） |
| `translation_error` | Text | 错误信息 |
| `translation_retry_count` | Integer | 重试次数 |
| `translation_started_at` | DateTime | 翻译开始时间 |
| `translation_completed_at` | DateTime | 翻译完成时间 |

#### 翻译状态生命周期

| 状态 | text 值 | 说明 |
| --- | --- | --- |
| **pending** | `NULL` | 未翻译 |
| **processing** | `NULL` | 正在调用 LLM API |
| **completed** | `"翻译内容"` | 翻译成功 |
| **failed** | `NULL` | 翻译失败，错误记录在 `translation_error` |

#### 设计理念（仿 AudioSegment）

```python
# 参考 AudioSegment 的设计模式，Translation 的状态管理：

class Translation(Base):
    """
    翻译模型（支持多语言和断点续传）

    状态管理（仿 AudioSegment 设计）：
    1. translation_status: 记录当前翻译状态
    2. text: 存储翻译结果（completed 时有值）
    3. translation_error: 记录失败原因（failed 时有值）
    4. translation_retry_count: 记录重试次数
    5. translation_started_at/completed_at: 记录翻译时间戳

    多语言支持：
    - 通过 (cue_id, language_code) 唯一约束
    - 每条 Cue 可有多个语言的翻译记录
    """
```

---

### 2.5 Chapter 表（新增）

用于存储 AI 语义分析生成的中文章节结构。

```python
class Chapter(Base):
    """
    章节模型

    存储 AI 语义分析生成的中文章节划分结果。
    """
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)

    # 章节信息
    chapter_index = Column(Integer, nullable=False)  # 章节序号（0, 1, 2...）
    title = Column(String, nullable=False)           # 中文章节标题
    summary = Column(Text, nullable=True)            # 章节摘要（中文）
    start_time = Column(Float, nullable=False)       # 章节开始时间
    end_time = Column(Float, nullable=False)         # 章节结束时间

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    episode = relationship("Episode", back_populates="chapters")
    transcript_cues = relationship("TranscriptCue", back_populates="chapter")

    # 表级约束和索引
    __table_args__ = (
        UniqueConstraint('episode_id', 'chapter_index', name='_episode_chapter_uc'),
        Index('idx_episode_chapter', 'episode_id', 'chapter_index'),
    )
```

#### Episode 新增关系

```python
# 在 Episode 模型中新增
chapters = relationship("Chapter", back_populates="episode", cascade="all, delete-orphan")
```

---

### 2.6 不复用的表（PodFlow 特有）

| 表名 | 原因 |
| --- | --- |
| `Podcast` | 新项目不需要 Podcast 概念 |
| `Highlight` | Web UI 特有功能（划线笔记） |
| `Note` | Web UI 特有功能（笔记系统） |
| `AIQueryRecord` | Web UI 特有功能（AI 查询缓存） |

---

## 3. 服务层复用方案

### 3.1 完全复用（复制代码）

| 服务 | 文件路径 | 复用方式 |
| --- | --- | --- |
| `WhisperService` | `services/whisper_service.py` | 完全复制，无需修改 |
| `TranscriptionService.create_virtual_segments()` | `services/transcription_service.py` | 完全复制 |
| `TranscriptionService.transcribe_virtual_segment()` | `services/transcription_service.py` | 完全复制 |

### 3.2 部分复用（需要修改）

| 服务 | 修改点 |
| --- | --- |
| `TranscriptionService.save_cues_to_db()` | 新增 `translation` 字段处理 |
| `TranscriptionService.sync_episode_transcription_status()` | 扩展状态枚举（7 状态） |
| `AIService` | 复用基础架构，新增语义分析接口 |

### 3.3 不复用（PodFlow 特有）

| 服务 | 原因 |
| --- | --- |
| `api.py` | Web API 路由，新项目是 CLI |
| `tasks.py` | 后台任务，新项目是显式触发 |

---

## 4. 状态机扩展设计

### 4.1 新的 7 状态枚举

```python
from enum import IntEnum

class WorkflowStatus(IntEnum):
    """
    工作流状态枚举

    设计原则：
    1. 使用整数枚举（便于数据库存储和比较）
    2. 状态单调递增（便于断点续传判断）
    3. 每个状态对应明确的阶段
    """
    INIT = 0                # 已入库，URL 已记录
    DOWNLOADED = 1          # 本地文件就绪
    TRANSCRIBED = 2         # WhisperX 转录完成
    SEGMENTED = 3           # 语义章节切分完成
    TRANSLATED = 4          # 逐句翻译完成
    READY_FOR_REVIEW = 5    # Obsidian 文档已生成
    PUBLISHED = 6           # 已分发

    def get_next_status(self) -> "WorkflowStatus":
        """获取下一个状态"""
        next_value = self.value + 1
        if next_value <= WorkflowStatus.PUBLISHED.value:
            return WorkflowStatus(next_value)
        return self  # 已是最终状态

    def can_resume_from(self, current_status: "WorkflowStatus") -> bool:
        """判断是否可以从当前状态恢复"""
        return self.value > current_status.value
```

### 4.2 状态转移图

```
┌──────────┐
│  INIT    │ 0: URL 已入库
└────┬─────┘
     │ run.py --url "xxx"
     ↓
┌──────────┐
│DOWNLOADED│ 1: 本地文件就绪
└────┬─────┘
     │ WhisperX 转录
     ↓
┌──────────┐
│TRANSCRIBED│ 2: 英文原文就绪
└────┬─────┘
     │ AI 语义切分
     ↓
┌──────────┐
│SEGMENTED │ 3: 章节划分 JSON 就绪
└────┬─────┘
     │ LLM 逐句翻译
     ↓
┌──────────┐
│TRANSLATED│ 4: 中英对照就绪
└────┬─────┘
     │ 生成 Obsidian 文档
     ↓
┌──────────────────┐
│READY_FOR_REVIEW  │ 5: 等待用户校对
└────────┬─────────┘
         │ publish.py --id 1024
         ↓
┌──────────┐
│PUBLISHED │ 6: 已分发
└──────────┘
```

### 4.3 断点续传逻辑

```python
def resume_workflow(episode_id: int) -> None:
    """
    断点续传入口

    逻辑：
    1. 查询数据库获取当前状态
    2. 根据 status 决定从哪个阶段恢复
    3. 执行 status + 1 对应的函数
    """
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    current_status = WorkflowStatus(episode.workflow_status)

    # 状态 → 处理函数映射
    handlers = {
        WorkflowStatus.INIT: download_media,
        WorkflowStatus.DOWNLOADED: transcribe_episode,
        WorkflowStatus.TRANSCRIBED: segment_chapters,
        WorkflowStatus.SEGMENTED: translate_transcript,
        WorkflowStatus.TRANSLATED: generate_obsidian_doc,
        WorkflowStatus.READY_FOR_REVIEW: publish_content,
        WorkflowStatus.PUBLISHED: lambda: print("已发布，无需操作")
    }

    # 执行下一个阶段
    next_status = current_status.get_next_status()
    if next_status != current_status:
        handler = handlers[next_status]
        handler(episode)

        # 更新状态
        episode.workflow_status = next_status.value
        db.commit()
```

---

## 5. 建表脚本

### 5.1 从零创建

```sql
-- =====================================================
-- EnglishPod3 Enhanced 数据库创建脚本
-- 从零创建全新数据库
-- =====================================================

-- 1. 创建 Episode 表
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    source_url VARCHAR(500),
    audio_path VARCHAR(500),
    file_hash VARCHAR(64) NOT NULL UNIQUE,
    file_size INTEGER,
    duration FLOAT NOT NULL,
    language VARCHAR(10) NOT NULL DEFAULT 'en-US',
    workflow_status INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_episodes_file_hash ON episodes(file_hash);
CREATE INDEX idx_episodes_workflow_status ON episodes(workflow_status);

-- 2. 创建 AudioSegment 表
CREATE TABLE audio_segments (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    segment_index INTEGER NOT NULL,
    segment_id VARCHAR(50) NOT NULL,
    segment_path VARCHAR(500),
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    transcription_started_at DATETIME,
    recognized_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
    UNIQUE(episode_id, segment_index)
);

CREATE INDEX idx_episode_segment ON audio_segments(episode_id, segment_index);
CREATE INDEX idx_segment_status ON audio_segments(status);
CREATE INDEX idx_episode_status_segment ON audio_segments(episode_id, status, segment_index);

-- 3. 创建 TranscriptCue 表
CREATE TABLE transcript_cues (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    segment_id INTEGER,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    speaker VARCHAR(50) NOT NULL DEFAULT 'Unknown',
    text TEXT NOT NULL,
    chapter_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
    FOREIGN KEY (segment_id) REFERENCES audio_segments(id) ON DELETE CASCADE
);

CREATE INDEX idx_episode_time ON transcript_cues(episode_id, start_time);
CREATE INDEX idx_segment_id ON transcript_cues(segment_id);

-- 4. 创建 Chapter 表
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
    UNIQUE(episode_id, chapter_index)
);

CREATE INDEX idx_episode_chapter ON chapters(episode_id, chapter_index);

-- 5. 添加 TranscriptCue 的 chapter_id 外键（必须在Chapter表创建后）
ALTER TABLE transcript_cues ADD COLUMN chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL;
CREATE INDEX idx_cue_chapter ON transcript_cues(chapter_id);

-- 6. 创建 Translation 表
CREATE TABLE translations (
    id INTEGER PRIMARY KEY,
    cue_id INTEGER NOT NULL REFERENCES transcript_cues(id) ON DELETE CASCADE,
    language_code VARCHAR(10) NOT NULL,
    text TEXT NOT NULL,
    translation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    translation_error TEXT,
    translation_retry_count INTEGER NOT NULL DEFAULT 0,
    translation_started_at DATETIME,
    translation_completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cue_id, language_code)
);

CREATE INDEX idx_translations_cue ON translations(cue_id);
CREATE INDEX idx_translations_language ON translations(language_code);
CREATE INDEX idx_translation_status ON translations(translation_status);
```

---

## 6. 复用代码清单

### 6.1 完全复制（无需修改）

| 文件 | 复制路径 |
| --- | --- |
| `backend/app/services/whisper_service.py` | `englishpod3-enhanced/backend/app/services/whisper_service.py` |
| `backend/app/utils/hardware_patch.py` | `englishpod3-enhanced/backend/app/utils/hardware_patch.py` |
| `backend/app/utils/file_utils.py` | `englishpod3-enhanced/backend/app/utils/file_utils.py` |
| `backend/app/config.py` | `englishpod3-enhanced/backend/app/config.py`（需要修改部分配置）|

### 6.2 复制后修改

| 原文件 | 新文件 | 修改点 |
| --- | --- | --- |
| `backend/app/models.py` | `backend/app/models.py` | 删除 Podcast/Highlight/Note/AIQueryRecord，新增 Chapter，修改 Episode/TranscriptCue |
| `backend/app/services/transcription_service.py` | `backend/app/services/transcription_service.py` | 修改 `save_cues_to_db()` 新增 translation，修改 `sync_episode_transcription_status()` 扩展状态 |
| `backend/app/services/ai_service.py` | `backend/app/services/semantic_service.py` | 修改为语义分析服务 |

---

## 7. 待确认事项

1. **是否需要保留 Highlight/Note/AIQueryRecord 表**？
   - 如果未来需要 Web UI 版本，可以考虑保留
   - 纯 CLI 版本不需要

---

**文档结束** | 请审核后反馈修改意见
