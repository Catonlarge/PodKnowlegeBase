# 数据库设计文档：EnglishPod3 Enhanced

| 文档版本 | V1.0 |
| --- | --- |
| **日期** | 2026-02-04 |
| **状态** | 待审核 |
| **数据库** | SQLite |
| **ORM** | SQLAlchemy 2.0+ |

---

## 目录

1. [设计原则](#1-设计原则)
2. [ER图](#2-er图)
3. [表结构详解](#3-表结构详解)
4. [状态机设计](#4-状态机设计)
5. [索引设计](#5-索引设计)
6. [迁移脚本](#6-迁移脚本)

---

## 1. 设计原则

### 1.1 核心设计理念

| 原则 | 说明 | 实现方式 |
| --- | --- | --- |
| **数据即资产 (Data as Asset)** | 存储过程数据，构建 RLHF 微调数据集 | Translation.original_translation vs translation 差异追踪 |
| **内容赛马 (Content Racing)** | 1:N 堆叠式架构，支持多角度分发 | MarketingPost 表无唯一性约束，angle_tag 策略标签 |
| **绝对锚定 (Absolute Anchoring)** | 使用 ID 隐形锚点，确保数据回填一致性 | Obsidian 中使用 `cue://ID` 格式 |
| **断点续传优先** | 所有长时间运行的操作必须支持中断恢复 | 状态字段 + 错误记录 + 重试计数 |
| **虚拟分段** | 不切割物理文件，只记录时间范围 | AudioSegment.segment_path 生命周期管理 |
| **绝对时间** | 使用相对于原始音频的绝对时间 | TranscriptCue.start_time/end_time |
| **状态一致性** | 状态通过子实体聚合计算，不冗余存储 | Episode 状态由 AudioSegment/TranscriptCue 状态决定 |
| **3NF规范** | 消除数据冗余，保证一致性 | @property 动态计算属性 |

### 1.2 从PodFlow复用的设计

| 模块 | 复用程度 | 说明 |
| --- | --- | --- |
| AudioSegment | 完全复用 | 虚拟分段机制，支持中断恢复 |
| Whisper转录状态 | 完全复用 | status: pending/processing/completed/failed |
| 绝对时间计算 | 完全复用 | start_time = segment.start_time + cue['start'] |

### 1.3 新增设计

| 模块 | 说明 |
| --- | --- |
| 翻译状态管理 | 仿AudioSegment设计，支持LLM调用的断点续传 |
| 7状态工作流 | INIT→DOWNLOADED→TRANSCRIBED→SEGMENTED→TRANSLATED→READY_FOR_REVIEW→PUBLISHED |
| 章节划分 | Chapter表存储AI语义分析结果 |

---

## 2. ER图

```
┌──────────────────────┐
│      Episode         │
├──────────────────────┤
│ id (PK)             │
│ source_url          │──┐
│ title               │  │
│ audio_path          │  │ 1:N         ┌──────────────┐
│ file_hash           │  │             │              │
│ duration            │  │             │              │
│ workflow_status     │──┘│             │              │
│ created_at          │    │             │              │
│ updated_at          │    │             │              │
└──────────────────────┘    │             │              │
         │                   │             │              │
         │ 1:N               │             │              │
         ▼                   │             │              │
┌──────────────────────┐    │             │              │
│   AudioSegment       │    │             │              │
├──────────────────────┤    │             │              │
│ id (PK)             │    │             │              │
│ episode_id (FK)      │──┘ │             │              │
│ segment_index       │      │             │              │
│ segment_id          │      │             │              │
│ segment_path        │      │             │              │
│ start_time          │      │             │              │
│ end_time            │      │             │              │
│ status              │      │             │              │
│ error_message       │      │             │              │
│ retry_count         │      │             │              │
│ transcription_...   │      │             │              │
│ recognized_at       │      │             │              │
└──────────────────────┘      │             │              │
         │                   │             │              │
         │ 1:N               │             │              │
         ▼                   │             │              │
┌──────────────────────┐    │             │              │
│   TranscriptCue      │    │             │              │
├──────────────────────┤    │             │              │
│ id (PK)             │    │             │              │
│ segment_id (FK)      │──┘ │             │              │
│ start_time          │    │             │              │
│ end_time            │    │             │              │
│ speaker             │    │             │              │
│ text (English)      │    │             │              │
│ chapter_id (FK)      │    │─────────────┼──────────────┘ │
│ created_at          │    │             │                        │
└──────────────────────┘    │             │                        │
         │                   │             │ 1:N                    │
         │ 1:N               │             ▼                        │
         ▼                   │      ┌──────────────┐                │
┌──────────────────────┐    │      │   Chapter    │                │
│     Translation      │    │      ├──────────────┤                │
├──────────────────────┤    │      │ id (PK)     │                │
│ id (PK)             │    │      │ episode_id   │                │
│ cue_id (FK)         │──┘ │      │ chapter_index│                │
│ language_code       │    │      │ title (中文) │                │
│ translation (Translated) │    │      │ summary     │                │
│ translation_status  │    │      │ start_time  │                │
│ translation_error   │    │      │ end_time    │                │
│ translation_retry...│    │      │ created_at  │                │
│ ...                 │    │      └──────────────┘                │
└──────────────────────┘    │                                      │
                            └──────────────────────────────────┘
```

---

## 3. 表结构详解

### 3.1 Episode 表

**表名**: `episodes`

**说明**: 存储视频/音频文件的元数据和工作流状态

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `title` | VARCHAR(255) | NOT NULL | - | 标题 |
| `show_name` | VARCHAR(255) | NULLABLE | NULL | 播客节目名称（来自metadata） |
| `source_url` | VARCHAR(500) | NULLABLE | NULL | 原始URL（YouTube/Bilibili等） |
| `audio_path` | VARCHAR(500) | NULLABLE | NULL | 本地音频文件路径 |
| `file_hash` | VARCHAR(64) | NOT NULL, UNIQUE | - | MD5哈希（去重） |
| `file_size` | INTEGER | NULLABLE | NULL | 文件大小（字节） |
| `duration` | FLOAT | NOT NULL | - | 时长（秒） |
| `language` | VARCHAR(10) | NOT NULL | 'en-US' | 语言代码 |
| `ai_summary` | TEXT | NULLABLE | NULL | **AI 生成的全篇总结**（支持回填更新） |
| `workflow_status` | INTEGER | NOT NULL | 0 | 工作流状态（0-6） |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 更新时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_episodes` | `id` | PRIMARY KEY |
| `idx_episodes_file_hash` | `file_hash` | UNIQUE |
| `idx_episodes_workflow_status` | `workflow_status` | INDEX |

#### workflow_status 枚举值

| 值 | 常量名 | 说明 |
| --- | --- | --- |
| 0 | INIT | 已入库，URL已记录 |
| 1 | DOWNLOADED | 本地文件就绪 |
| 2 | TRANSCRIBED | WhisperX转录完成 |
| 3 | SEGMENTED | 语义章节切分完成 |
| 4 | TRANSLATED | 逐句翻译完成 |
| 5 | READY_FOR_REVIEW | Obsidian文档已生成 |
| 6 | PUBLISHED | 已分发 |

#### SQLAlchemy 模型

```python
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    show_name = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    audio_path = Column(String(500), nullable=True)
    file_hash = Column(String(64), nullable=False, unique=True, index=True)
    file_size = Column(Integer, nullable=True)
    duration = Column(Float, nullable=False)
    language = Column(String(10), nullable=False, default="en-US")
    ai_summary = Column(Text, nullable=True)  # AI 生成的全篇总结
    workflow_status = Column(Integer, nullable=False, default=0, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系映射
    segments = relationship("AudioSegment", back_populates="episode", cascade="all, delete-orphan")
    transcript_cues = relationship("TranscriptCue", back_populates="episode", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="episode", cascade="all, delete-orphan")
    publication_records = relationship("PublicationRecord", back_populates="episode", cascade="all, delete-orphan")
    marketing_posts = relationship("MarketingPost", back_populates="episode", cascade="all, delete-orphan")
```

---

### 3.2 AudioSegment 表

**表名**: `audio_segments`

**说明**: 虚拟分段，支持长音频的异步转录和中断恢复

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `episode_id` | INTEGER | FOREIGN KEY, NOT NULL | - | 关联Episode |
| `segment_index` | INTEGER | NOT NULL | - | 分段序号（0, 1, 2...） |
| `segment_id` | VARCHAR(50) | NOT NULL | - | 分段ID（如"segment_001"） |
| `segment_path` | VARCHAR(500) | NULLABLE | NULL | 临时音频文件路径 |
| `start_time` | FLOAT | NOT NULL | - | 在原音频中的开始时间（秒） |
| `end_time` | FLOAT | NOT NULL | - | 在原音频中的结束时间（秒） |
| `status` | VARCHAR(20) | NOT NULL | 'pending' | 转录状态 |
| `error_message` | TEXT | NULLABLE | NULL | 错误信息 |
| `retry_count` | INTEGER | NOT NULL | 0 | 重试次数 |
| `transcription_started_at` | DATETIME | NULLABLE | NULL | 开始转录时间 |
| `recognized_at` | DATETIME | NULLABLE | NULL | 识别完成时间 |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_audio_segments` | `id` | PRIMARY KEY |
| `idx_episode_segment` | `episode_id, segment_index` | INDEX |
| `idx_segment_status` | `status` | INDEX |
| `idx_episode_status_segment` | `episode_id, status, segment_index` | INDEX |
| `_episode_segment_uc` | `episode_id, segment_index` | UNIQUE |

#### status 枚举值

| 值 | 说明 | segment_path 值 |
| --- | --- | --- |
| pending | 等待转录 | NULL |
| processing | 正在转录中 | 临时文件路径 |
| completed | 转录完成 | NULL（已删除） |
| failed | 转录失败 | 临时文件路径（保留用于重试） |

#### segment_path 生命周期

```
┌────────────┐    FFmpeg提取    ┌────────────┐    转录成功    ┌────────────┐
│  pending   │ ───────────────→ │ processing │ ────────────→ │ completed  │
│  (NULL)    │                 │ (有路径)   │                 │  (NULL)    │
└────────────┘                 └────────────┘                 └────────────┘
                                       │
                                       │ 转录失败
                                       ▼
                                  ┌────────────┐
                                  │   failed   │
                                  │ (保留路径)  │
                                  └────────────┘
```

#### SQLAlchemy 模型

```python
class AudioSegment(Base):
    __tablename__ = "audio_segments"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    segment_index = Column(Integer, nullable=False)
    segment_id = Column(String(50), nullable=False)
    segment_path = Column(String(500), nullable=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    transcription_started_at = Column(DateTime, nullable=True)
    recognized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    episode = relationship("Episode", back_populates="segments")
    transcript_cues = relationship("TranscriptCue", back_populates="segment", cascade="all, delete-orphan")

    @property
    def duration(self):
        """分段时长（动态计算）"""
        return self.end_time - self.start_time

    __table_args__ = (
        UniqueConstraint('episode_id', 'segment_index', name='_episode_segment_uc'),
        Index('idx_episode_segment', 'episode_id', 'segment_index'),
        Index('idx_segment_status', 'status'),
        Index('idx_episode_status_segment', 'episode_id', 'status', 'segment_index'),
    )
```

---

### 3.3 Translation 表

**表名**: `translations`

**说明**: 存储**RLHF 双文本**（数据资产化），支持无限扩展和断点续传

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `cue_id` | INTEGER | FOREIGN KEY, NOT NULL | - | 关联TranscriptCue |
| `language_code` | VARCHAR(10) | NOT NULL | - | 语言代码（'zh', 'ja', 'fr'...） |
| **`original_translation`** | TEXT | NULLABLE | NULL | **AI 原始版本**（Rejected Sample，首次生成后永久不可变） |
| **`translation`** | TEXT | NULLABLE | NULL | **当前生效版本**（Chosen Sample，用户修改后更新此字段） |
| **`is_edited`** | BOOLEAN | NOT NULL | FALSE | **RLHF 标记**：`original != current` 时自动设为 TRUE |
| `translation_status` | VARCHAR(20) | NOT NULL | 'pending' | 翻译状态 |
| `translation_error` | TEXT | NULLABLE | NULL | 翻译错误信息 |
| `translation_retry_count` | INTEGER | NOT NULL | 0 | 翻译重试次数 |
| `translation_started_at` | DATETIME | NULLABLE | NULL | 翻译开始时间 |
| `translation_completed_at` | DATETIME | NULLABLE | NULL | 翻译完成时间 |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_translations` | `id` | PRIMARY KEY |
| `idx_translations_cue` | `cue_id` | INDEX |
| `idx_translations_language` | `language_code` | INDEX |
| `idx_translation_status` | `translation_status` | INDEX |
| `_cue_language_uc` | `cue_id, language_code` | UNIQUE |

#### language_code 常用值

| 代码 | 语言 | 说明 |
| --- | --- | --- |
| `zh` | 中文 | 简体中文 |
| `zh-TW` | 中文 | 繁体中文 |
| `ja` | 日语 | |
| `ko` | 韩语 | |
| `fr` | 法语 | |
| `es` | 西班牙语 | |
| `de` | 德语 | |

#### translation_status 枚举值

| 值 | text 值 | 说明 |
| --- | --- | --- |
| pending | NULL | 未翻译 |
| processing | NULL | 正在调用LLM API |
| completed | "翻译内容" | 翻译成功 |
| failed | NULL | 翻译失败 |

#### 翻译状态生命周期

```
┌────────────┐    开始翻译    ┌────────────┐    翻译成功    ┌────────────┐
│  pending   │ ─────────────→ │ processing │ ────────────→ │ completed  │
│  (NULL)    │               │  (NULL)    │               │ ("翻译内容")│
└────────────┘               └────────────┘               └────────────┘
                                    │
                                    │ 翻译失败
                                    ▼
                               ┌────────────┐
                               │   failed   │
                               │  (NULL)    │
                               └────────────┘
```

#### RLHF 双文本工作流

```
┌──────────────────┐     LLM 首次生成      ┌─────────────────────────────┐
│   初始状态        │ ──────────────────→  │  original = "AI 翻译 A"    │
│  (NULL, NULL)    │                     │  translation = "AI 翻译 A"  │
└──────────────────┘                     │  is_edited = FALSE          │
                                        └─────────────────────────────┘
                                                 │
                                                 │ 用户在 Obsidian 修改
                                                 ▼
                                        ┌─────────────────────────────┐
                                        │  original = "AI 翻译 A"     │
                                        │  translation = "人工修正 B"  │
                                        │  is_edited = TRUE           │
                                        └─────────────────────────────┘
                                                 │
                                                 │ 导出训练数据 (WHERE is_edited=TRUE)
                                                 ▼
                                        ┌─────────────────────────────┐
                                        │  Input: "原文 + AI 翻译 A"  │
                                        │  Output: "人工修正 B"       │
                                        │  → 用于 DPO/RLHF 微调        │
                                        └─────────────────────────────┘
```

#### SQLAlchemy 模型

```python
class Translation(Base):
    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, index=True)
    cue_id = Column(Integer, ForeignKey("transcript_cues.id", ondelete="CASCADE"), nullable=False)
    language_code = Column(String(10), nullable=False)
    original_translation = Column(Text, nullable=True)  # AI 原始版本，永久不可变
    translation = Column(Text, nullable=True)  # 当前生效版本
    is_edited = Column(Boolean, nullable=False, default=False)  # RLHF 标记
    translation_status = Column(String(20), nullable=False, default="pending")
    translation_error = Column(Text, nullable=True)
    translation_retry_count = Column(Integer, nullable=False, default=0)
    translation_started_at = Column(DateTime, nullable=True)
    translation_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    cue = relationship("TranscriptCue", back_populates="translations")

    __table_args__ = (
        UniqueConstraint('cue_id', 'language_code', name='_cue_language_uc'),
        Index('idx_translations_cue', 'cue_id'),
        Index('idx_translations_language', 'language_code'),
        Index('idx_translation_status', 'translation_status'),
        Index('idx_translation_ep_lang_status', 'cue_id', 'language_code', 'translation_status'),  # 复合索引
        Index('idx_translation_is_edited', 'is_edited'),  # RLHF 数据筛选
    )
```

---

### 3.4 PublicationRecord 表（新增）

**表名**: `publication_records`

**说明**: 存储发布分发记录，追踪各平台发布状态

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `episode_id` | INTEGER | FOREIGN KEY, NOT NULL | - | 关联Episode |
| `platform` | VARCHAR(50) | NOT NULL | - | 平台名称（'feishu', 'ima', 'marketing'） |
| `platform_record_id` | VARCHAR(255) | NULLABLE | NULL | 平台返回的记录ID |
| `status` | VARCHAR(20) | NOT NULL | 'pending' | 发布状态 |
| `published_at` | DATETIME | NULLABLE | NULL | 发布时间 |
| `error_message` | TEXT | NULLABLE | NULL | 错误信息 |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_publication_records` | `id` | PRIMARY KEY |
| `idx_pub_episode` | `episode_id` | INDEX |
| `idx_pub_platform` | `platform` | INDEX |
| `idx_pub_status` | `status` | INDEX |

#### platform 枚举值

| 值 | 说明 |
| --- | --- |
| `feishu` | 飞书平台 |
| `ima` | 腾讯IMA知识库 |
| `marketing` | 营销端 |

#### status 枚举值

| 值 | 说明 |
| --- | --- |
| `pending` | 待发布 |
| `processing` | 发布中 |
| `success` | 发布成功 |
| `failed` | 发布失败 |

#### SQLAlchemy 模型

```python
class PublicationRecord(Base):
    __tablename__ = "publication_records"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    platform_record_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    published_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    episode = relationship("Episode", back_populates="publication_records")

    __table_args__ = (
        Index('idx_pub_episode', 'episode_id'),
        Index('idx_pub_platform', 'platform'),
        Index('idx_pub_status', 'status'),
    )
```

---

### 3.5 TranslationCorrection 表（新增）

**表名**: `translation_corrections`

**说明**: 存储AI翻译修正记录，支持Token优化（Patch Mode）

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `cue_id` | INTEGER | FOREIGN KEY, NOT NULL | - | 关联TranscriptCue |
| `language_code` | VARCHAR(10) | NOT NULL | - | 语言代码 |
| `original_text` | TEXT | NOT NULL | - | 原翻译内容 |
| `corrected_text` | TEXT | NOT NULL | - | 修正后内容 |
| `ai_model` | VARCHAR(50) | NULLABLE | NULL | 使用的AI模型 |
| `corrected_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 修正时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_translation_corrections` | `id` | PRIMARY KEY |
| `idx_corr_cue` | `cue_id` | INDEX |
| `idx_corr_language` | `language_code` | INDEX |

#### SQLAlchemy 模型

```python
class TranslationCorrection(Base):
    __tablename__ = "translation_corrections"

    id = Column(Integer, primary_key=True, index=True)
    cue_id = Column(Integer, ForeignKey("transcript_cues.id", ondelete="CASCADE"), nullable=False)
    language_code = Column(String(10), nullable=False)
    original_text = Column(Text, nullable=False)
    corrected_text = Column(Text, nullable=False)
    ai_model = Column(String(50), nullable=True)
    corrected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    cue = relationship("TranscriptCue")

    __table_args__ = (
        Index('idx_corr_cue', 'cue_id'),
        Index('idx_corr_language', 'language_code'),
    )
```

---

### 3.6 MarketingPost 表（核心亮点）

**表名**: `marketing_posts`

**说明**: 存储**内容赛马**式营销文案，支持 1:N 堆叠式多角度分发

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键（每条文案独立身份证） |
| `episode_id` | INTEGER | FOREIGN KEY, NOT NULL | - | 关联Episode |
| `chapter_id` | INTEGER | FOREIGN KEY, NULLABLE | NULL | **粒度控制**：NULL=全篇文案，有值=章节切片文案 |
| `platform` | VARCHAR(50) | NOT NULL | - | 渠道标识（'xhs', 'twitter', 'bilibili'等） |
| **`angle_tag`** | VARCHAR(50) | NOT NULL | - | **策略标签**（如"职场焦虑向"、"干货硬核向"、"搞笑吐槽向"） |
| `title` | VARCHAR(255) | NOT NULL | - | 帖子标题/首图文案 |
| `content` | TEXT | NOT NULL | - | 完整营销正文（含 Emoji、排版） |
| `status` | VARCHAR(20) | NOT NULL | 'pending' | 文案状态 |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_marketing_posts` | `id` | PRIMARY KEY |
| `idx_marketing_episode` | `episode_id` | INDEX |
| `idx_marketing_chapter` | `chapter_id` | INDEX |
| `idx_marketing_platform` | `platform` | INDEX |
| `idx_marketing_angle` | `angle_tag` | INDEX |
| `idx_marketing_ep_angle` | `episode_id, angle_tag` | INDEX |  # 复合索引优化 |

#### platform 枚举值

| 值 | 说明 |
| --- | --- |
| `xhs` | 小红书 |
| `twitter` | Twitter/X |
| `bilibili` | 哔哩哔哩 |
| `wechat` | 微信公众号 |
| `douyin` | 抖音 |

#### angle_tag 策略标签示例

| 标签 | 说明 | 示例场景 |
| --- | --- | --- |
| `职场焦虑向` | 针对职场痛点，制造焦虑共鸣 | "35岁危机还在用死工资..." |
| `干货硬核向` | 强调实用性，知识密集型 | "5分钟掌握10个商务英语..." |
| `搞笑吐槽向` | 幽默风格，轻松娱乐 | "老外学中文的迷惑行为..." |
| `情感故事向` | 讲故事，情感共鸣 | "那个深夜，我打通了..." |
| `热点蹭流向` | 结合时事热点 | "ChatGPT来了，你的英语..." |

#### SQLAlchemy 模型

```python
class MarketingPost(Base):
    __tablename__ = "marketing_posts"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    platform = Column(String(50), nullable=False)
    angle_tag = Column(String(50), nullable=False)  # 策略标签
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    episode = relationship("Episode", back_populates="marketing_posts")
    chapter = relationship("Chapter")

    __table_args__ = (
        Index('idx_marketing_episode', 'episode_id'),
        Index('idx_marketing_chapter', 'chapter_id'),
        Index('idx_marketing_platform', 'platform'),
        Index('idx_marketing_angle', 'angle_tag'),
        Index('idx_marketing_ep_angle', 'episode_id', 'angle_tag'),
        # 注意：无唯一性约束，支持 1:N 堆叠式设计
    )
```

---

### 3.7 TranscriptCue 表

**表名**: `transcript_cues`

**说明**: 存储单句字幕（英文原文）

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `segment_id` | INTEGER | FOREIGN KEY, NULLABLE | NULL | 关联AudioSegment（通过segment获取episode） |
| `start_time` | FLOAT | NOT NULL | - | 绝对时间（相对于原始音频） |
| `end_time` | FLOAT | NOT NULL | - | 绝对时间（相对于原始音频） |
| `speaker` | VARCHAR(50) | NOT NULL | 'Unknown' | 说话人标识 |
| `text` | TEXT | NOT NULL | - | 英文字幕文本 |
| `chapter_id` | INTEGER | FOREIGN KEY, NULLABLE | NULL | 关联Chapter |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_transcript_cues` | `id` | PRIMARY KEY |
| `idx_episode_time` | `episode_id, start_time` | INDEX |
| `idx_segment_id` | `segment_id` | INDEX |
| `idx_cue_chapter` | `chapter_id` | INDEX |

#### SQLAlchemy 模型

```python
class TranscriptCue(Base):
    __tablename__ = "transcript_cues"

    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("audio_segments.id", ondelete="CASCADE"), nullable=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    speaker = Column(String(50), nullable=False, default="Unknown")
    text = Column(Text, nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    segment = relationship("AudioSegment", back_populates="transcript_cues")
    chapter = relationship("Chapter", back_populates="transcript_cues")
    translations = relationship("Translation", back_populates="cue", cascade="all, delete-orphan")

    @property
    def episode_id(self) -> int:
        """通过segment动态获取episode_id（遵循3NF）"""
        return self.segment.episode_id if self.segment else None

    @property
    def episode(self) -> "Episode":
        """通过segment动态获取episode对象"""
        return self.segment.episode if self.segment else None

    # 便捷属性：获取指定语言的翻译
    def get_translation(self, language_code: str = "zh") -> Optional[str]:
        """获取指定语言的翻译"""
        for t in self.translations:
            if t.language_code == language_code and t.translation_status == "completed":
                return t.translation
        return None

    __table_args__ = (
        Index('idx_segment_id', 'segment_id'),
        Index('idx_cue_chapter', 'chapter_id'),
        Index('idx_cue_start_time', 'segment_id', 'start_time'),  # 复合索引优化
    )
```

---

### 3.8 Chapter 表

**表名**: `chapters`

**说明**: 存储AI语义分析生成的中文章节划分结果

#### 字段列表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY | AUTO | 主键 |
| `episode_id` | INTEGER | FOREIGN KEY, NOT NULL | - | 关联Episode |
| `chapter_index` | INTEGER | NOT NULL | - | 章节序号（0, 1, 2...） |
| `title` | VARCHAR(255) | NOT NULL | - | 中文章节标题 |
| `summary` | TEXT | NULLABLE | NULL | 章节摘要（中文） |
| `start_time` | FLOAT | NOT NULL | - | 章节开始时间（秒） |
| `end_time` | FLOAT | NOT NULL | - | 章节结束时间（秒） |
| `status` | VARCHAR(20) | NOT NULL | 'pending' | 章节状态 |
| `ai_model_used` | VARCHAR(50) | NULLABLE | NULL | 使用的AI模型 |
| `processed_at` | DATETIME | NULLABLE | NULL | 处理完成时间 |
| `created_at` | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

#### 索引

| 索引名 | 字段 | 类型 |
| --- | --- | --- |
| `pk_chapters` | `id` | PRIMARY KEY |
| `idx_episode_chapter` | `episode_id, chapter_index` | INDEX |
| `_episode_chapter_uc` | `episode_id, chapter_index` | UNIQUE |

#### SQLAlchemy 模型

```python
class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    ai_model_used = Column(String(50), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系映射
    episode = relationship("Episode", back_populates="chapters")
    transcript_cues = relationship("TranscriptCue", back_populates="chapter")

    @property
    def duration(self):
        """章节时长（动态计算）"""
        return self.end_time - self.start_time

    __table_args__ = (
        UniqueConstraint('episode_id', 'chapter_index', name='_episode_chapter_uc'),
        Index('idx_episode_chapter', 'episode_id', 'chapter_index'),
        Index('idx_chapter_status', 'status'),
    )
```

---

### 3.9 Obsidian 隐形锚点机制（核心亮点）

**设计背景**：解决 Obsidian 文档与数据库之间的数据回填一致性难题。传统方案使用时间戳或行号作为锚点，容易因编辑操作导致偏移错乱。

**核心机制**：使用 **`cue://ID`** 格式的绝对锚点，确保数据回填时的强一致性。

#### 锚点格式定义

| 格式 | 说明 | 示例 |
| --- | --- | --- |
| `cue://<cue_id>` | 绝对锚点，关联 TranscriptCue.id | `cue://1024` |
| `chapter://<chapter_id>` | 章节锚点，关联 Chapter.id | `chapter://56` |
| `post://<post_id>` | 营销文案锚点，关联 MarketingPost.id | `post://789` |

#### Obsidian Markdown 渲染策略

**显示层（用户看到）**：
```markdown
| 时间轴 | 英文原文 | 中文翻译 |
| :--- | :--- | :--- |
| 00:05 | Hello world. | 你好世界。 |
```

**源码层（实际存储）**：
```markdown
| 时间轴 | 英文原文 | 中文翻译 |
| :--- | :--- | :--- |
| [00:05](cue://1024) | Hello world. | 你好世界。 |
```

#### 回填阶段工作流

```
┌────────────────────────────────────────────────────────────────┐
│                      生产阶段 (run.py)                         │
├────────────────────────────────────────────────────────────────┤
│  1. Whisper 生成 TranscriptCue (id=1024)                       │
│  2. LLM 生成翻译 → 写入 translations 表                         │
│  3. 渲染 Markdown → 插入 [00:05](cue://1024)                   │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                     校对阶段 (Obsidian)                        │
├────────────────────────────────────────────────────────────────┤
│  1. 用户在 Obsidian 中修改翻译                                  │
│  2. Markdown 源码保持 [00:05](cue://1024) 不变                 │
│  3. 用户保存文件                                               │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                    回填阶段 (publish.py)                       │
├────────────────────────────────────────────────────────────────┤
│  1. 解析 Markdown，提取 cue://1024 作为唯一 Key                 │
│  2. 查询数据库：SELECT * FROM transcript_cues WHERE id=1024    │
│  3. 比对文本差异 → 更新 translations.translation               │
│  4. 设置 translations.is_edited = TRUE (如有差异)              │
└────────────────────────────────────────────────────────────────┘
```

#### 锚点机制的优势

| 对比维度 | 时间戳锚点 | 行号锚点 | **ID 隐形锚点** |
| --- | --- | --- | --- |
| **抗编辑性** | ❌ 插入行导致偏移 | ❌ 删除行导致错乱 | ✅ 唯一ID永不变化 |
| **可读性** | ✅ 用户可见时间 | ❌ 纯数字无意义 | ✅ 显示时间，链接ID |
| **回填精度** | ⚠️ 可能重复或模糊 | ⚠️ 删除后无法定位 | ✅ 数据库主键精确匹配 |
| **实现复杂度** | 低 | 低 | 中（需解析协议） |

#### SQLAlchemy 辅助方法

```python
class TranscriptCue(Base):
    # ... 现有代码 ...

    @property
    def obsidian_anchor(self) -> str:
        """生成 Obsidian 隐形锚点"""
        time_str = f"{int(self.start_time // 60):02d}:{int(self.start_time % 60):02d}"
        return f"[{time_str}](cue://{self.id})"

    @property
    def obsidian_link(self) -> str:
        """生成用于回填的协议链接"""
        return f"cue://{self.id}"
```

#### 数据回填示例代码

```python
def parse_markdown_and_backfill(markdown_content: str, db_session):
    """解析 Obsidian Markdown 并回填数据库"""
    from re import findall

    # 提取所有 cue://ID 链接
    anchors = findall(r'\[.*?\]\(cue://(\d+)\)', markdown_content)

    for cue_id in anchors:
        cue = db_session.query(TranscriptCue).get(cue_id)
        if cue:
            # 提取对应的翻译文本（实际实现需解析表格）
            new_translation = extract_translation_from_table(markdown_content, cue_id)

            # RLHF 双文本更新
            if cue.translations[0].original_translation != new_translation:
                cue.translations[0].translation = new_translation
                cue.translations[0].is_edited = True
                print(f"✓ Cue {cue_id} 已更新 (is_edited=TRUE)")

    db_session.commit()
```

---

## 4. ER图

```
┌──────────────────────┐
│      Episode         │
├──────────────────────┤
│ id (PK)             │
│ source_url          │──┐
│ title               │  │
│ ai_summary          │  │ 1:N         ┌──────────────┐
│ file_hash           │  │             │              │
│ duration            │  │             │              │
│ workflow_status     │──┘│             │              │
│ created_at          │    │             │              │
│ updated_at          │    │             │              │
└──────────────────────┘    │             │              │
         │                   │             │              │
         │ 1:N               │             │              │
         ▼                   │             │ 1:N          │
┌──────────────────────┐    │             │              │
│   AudioSegment       │    │             │              │
├──────────────────────┤    │             │              │
│ id (PK)             │    │             │              │
│ episode_id (FK)      │──┘ │             │              │
│ segment_index       │      │             │              │
│ segment_id          │      │             │              │
│ segment_path        │      │             │              │
│ start_time          │      │             │              │
│ end_time            │      │             │              │
│ status              │      │             │              │
│ error_message       │      │             │              │
│ retry_count         │      │             │              │
│ transcription_...   │      │             │              │
│ recognized_at       │      │             │              │
└──────────────────────┘      │             │              │
         │                   │             │              │
         │ 1:N               │             │              │
         ▼                   │             │              │
┌──────────────────────┐    │             │              │
│   TranscriptCue      │    │             │              │
├──────────────────────┤    │             │              │
│ id (PK)             │    │             │              │
│ segment_id (FK)      │──┘ │             │              │
│ start_time          │    │             │              │
│ end_time            │    │             │              │
│ speaker             │    │             │              │
│ text (English)      │    │             │              │
│ chapter_id (FK)      │    │─────────────┼──────────────┘ │
│ created_at          │    │             │                        │
└──────────────────────┘    │             │  1:N                   │
         │                   │             ▼                        │
         │ 1:N               │      ┌──────────────┐                │
         ▼                   │      │   Chapter    │                │
┌──────────────────────┐    │      ├──────────────┤                │
│     Translation      │    │      │ id (PK)     │                │
├──────────────────────┤    │      │ episode_id   │                │
│ id (PK)             │    │      │ chapter_index│                │
│ cue_id (FK)         │──┘ │      │ title (中文) │                │
│ language_code       │    │      │ summary     │                │
│ original_translation│    │      │ start_time  │                │
│ translation         │    │      │ end_time    │                │
│ is_edited           │    │      │ created_at  │                │
│ translation_status  │    │      └──────────────┘                │
│ ...                 │    │                                      │
└──────────────────────┘    │                                      │
                            │      ┌──────────────┐                │
                            │      │MarketingPost │                │
                            │      ├──────────────┤                │
                            │      │ id (PK)     │                │
                            │      │ episode_id  │                │
                            └──────│ chapter_id  │                │
                                   │ platform    │                │
                                   │ angle_tag   │                │
                                   │ title       │                │
                                   │ content     │                │
                                   └──────────────┘                │
                            └──────────────────────────────────┘
```

---

## 5. 表结构详解

### 4.1 Episode 工作流状态

```python
from enum import IntEnum

class WorkflowStatus(IntEnum):
    """工作流状态枚举"""
    INIT = 0                # 已入库，URL已记录
    DOWNLOADED = 1          # 本地文件就绪
    TRANSCRIBED = 2         # WhisperX转录完成
    SEGMENTED = 3           # 语义章节切分完成
    TRANSLATED = 4          # 逐句翻译完成
    READY_FOR_REVIEW = 5    # Obsidian文档已生成
    PUBLISHED = 6           # 已分发

    def get_next_status(self) -> "WorkflowStatus":
        """获取下一个状态"""
        next_value = self.value + 1
        if next_value <= WorkflowStatus.PUBLISHED.value:
            return WorkflowStatus(next_value)
        return self
```

### 4.2 AudioSegment 转录状态

```python
class TranscriptionStatus(str):
    """转录状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
```

### 4.3 TranscriptCue 翻译状态

```python
class TranslationStatus(str):
    """翻译状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
```

### 4.4 状态转移图

```
Episode 工作流状态转移：
┌──────┐   run.py    ┌──────────┐  WhisperX  ┌───────────┐
│ INIT │ ──────────→ │DOWNLOADED│ ──────────→│TRANSCRIBED│
└──────┘             └──────────┘            └───────────┘
                                                        │
                                                        │ AI切分
                                                        ▼
                                                 ┌───────────┐
                                                 │ SEGMENTED │
                                                 └───────────┘
                                                        │
                                                        │ LLM翻译
                                                        ▼
                                                 ┌───────────┐
                                                 │TRANSLATED │
                                                 └───────────┘
                                                        │
                                                        │ 生成文档
                                                        ▼
                                                 ┌──────────────┐
                                                 │READY_FOR_... │
                                                 └──────────────┘
                                                        │
                                                        │ publish.py
                                                        ▼
                                                 ┌───────────┐
                                                 │ PUBLISHED │
                                                 └───────────┘


AudioSegment 转录状态转移（每个Segment独立）：
┌────────┐  开始转录  ┌───────────┐  成功  ┌──────────┐
│pending│ ────────→ │processing │ ──────→ │completed │
└────────┘          └───────────┘        └──────────┘
                           │
                           │ 失败
                           ▼
                        ┌──────┐
                        │failed │ ──┐
                        └──────┘   │ 重试
                                   ▼
                            （回到processing）


TranscriptCue 翻译状态转移（每个Cue独立，仿AudioSegment）：
┌────────┐  开始翻译  ┌───────────┐  成功  ┌──────────┐
│pending│ ────────→ │processing │ ──────→ │completed │
└────────┘          └───────────┘        └──────────┘
                           │
                           │ 失败
                           ▼
                        ┌──────┐
                        │failed │ ──┐
                        └──────┘   │ 重试
                                   ▼
                            （回到processing）
```

---

## 5. 索引设计

### 5.1 索引汇总表

| 表名 | 索引名 | 字段 | 类型 | 用途 |
| --- | --- | --- | --- | --- |
| episodes | pk_episodes | id | PRIMARY KEY | 主键 |
| episodes | idx_episodes_file_hash | file_hash | UNIQUE | 去重查询 |
| episodes | idx_episodes_workflow_status | workflow_status | INDEX | 状态过滤 |
| audio_segments | pk_audio_segments | id | PRIMARY KEY | 主键 |
| audio_segments | idx_episode_segment | episode_id, segment_index | INDEX | 顺序查询 |
| audio_segments | idx_segment_status | status | INDEX | 状态过滤 |
| audio_segments | idx_episode_status_segment | episode_id, status, segment_index | INDEX | 复合查询 |
| transcript_cues | pk_transcript_cues | id | PRIMARY KEY | 主键 |
| transcript_cues | idx_segment_id | segment_id | INDEX | Segment关联 |
| transcript_cues | idx_cue_chapter | chapter_id | INDEX | Chapter关联 |
| transcript_cues | idx_cue_start_time | segment_id, start_time | INDEX | 复合查询优化 |
| translations | pk_translations | id | PRIMARY KEY | 主键 |
| translations | idx_translations_cue | cue_id | INDEX | Cue关联 |
| translations | idx_translations_language | language_code | INDEX | 语言过滤 |
| translations | idx_translation_status | translation_status | INDEX | 状态过滤 |
| translations | idx_translation_ep_lang_status | cue_id, language_code, translation_status | INDEX | 复合查询优化 |
| translations | idx_translation_is_edited | is_edited | INDEX | RLHF 数据筛选 |
| chapters | pk_chapters | id | PRIMARY KEY | 主键 |
| chapters | idx_episode_chapter | episode_id, chapter_index | INDEX | 顺序查询 |
| chapters | idx_chapter_status | status | INDEX | 状态过滤 |
| marketing_posts | pk_marketing_posts | id | PRIMARY KEY | 主键 |
| marketing_posts | idx_marketing_episode | episode_id | INDEX | Episode关联 |
| marketing_posts | idx_marketing_chapter | chapter_id | INDEX | Chapter关联 |
| marketing_posts | idx_marketing_platform | platform | INDEX | 平台过滤 |
| marketing_posts | idx_marketing_angle | angle_tag | INDEX | 策略标签过滤 |
| marketing_posts | idx_marketing_ep_angle | episode_id, angle_tag | INDEX | 复合查询优化 |
| publication_records | pk_publication_records | id | PRIMARY KEY | 主键 |
| publication_records | idx_pub_episode | episode_id | INDEX | Episode关联 |
| publication_records | idx_pub_platform | platform | INDEX | 平台过滤 |
| publication_records | idx_pub_status | status | INDEX | 状态过滤 |
| translation_corrections | pk_translation_corrections | id | PRIMARY KEY | 主键 |
| translation_corrections | idx_corr_cue | cue_id | INDEX | Cue关联 |
| translation_corrections | idx_corr_language | language_code | INDEX | 语言过滤 |

### 5.2 索引设计原则

| 原则 | 说明 | 示例 |
| --- | --- | --- |
| **外键必索引** | 所有外键字段必须建立索引 | episode_id, segment_id, chapter_id |
| **查询覆盖** | 常用查询条件建立复合索引 | (episode_id, status, segment_index) |
| **排序优化** | 排序字段包含在索引中 | (episode_id, start_time) |
| **唯一约束** | 业务唯一性约束 | (episode_id, segment_index) |

---

## 6. 建表脚本

### 6.1 从零创建

```sql
-- =====================================================
-- EnglishPod3 Enhanced 数据库创建脚本
-- 从零创建全新数据库
-- =====================================================

-- 1. 创建 Episode 表
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    show_name VARCHAR(255),
    source_url VARCHAR(500),
    audio_path VARCHAR(500),
    file_hash VARCHAR(64) NOT NULL UNIQUE,
    file_size INTEGER,
    duration FLOAT NOT NULL,
    language VARCHAR(10) NOT NULL DEFAULT 'en-US',
    ai_summary TEXT,
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

-- 3. 创建 Chapter 表（需在TranscriptCue之前创建）
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ai_model_used VARCHAR(50),
    processed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
    UNIQUE(episode_id, chapter_index)
);

CREATE INDEX idx_episode_chapter ON chapters(episode_id, chapter_index);
CREATE INDEX idx_chapter_status ON chapters(status);

-- 4. 创建 TranscriptCue 表（移除冗余episode_id，遵循3NF）
CREATE TABLE transcript_cues (
    id INTEGER PRIMARY KEY,
    segment_id INTEGER,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    speaker VARCHAR(50) NOT NULL DEFAULT 'Unknown',
    text TEXT NOT NULL,
    chapter_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (segment_id) REFERENCES audio_segments(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
);

CREATE INDEX idx_segment_id ON transcript_cues(segment_id);
CREATE INDEX idx_cue_chapter ON transcript_cues(chapter_id);
CREATE INDEX idx_cue_start_time ON transcript_cues(segment_id, start_time);

-- 5. 创建 Translation 表（RLHF 双文本设计）
CREATE TABLE translations (
    id INTEGER PRIMARY KEY,
    cue_id INTEGER NOT NULL REFERENCES transcript_cues(id) ON DELETE CASCADE,
    language_code VARCHAR(10) NOT NULL,
    original_translation TEXT,
    translation TEXT,
    is_edited BOOLEAN NOT NULL DEFAULT 0,
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
CREATE INDEX idx_translation_ep_lang_status ON translations(cue_id, language_code, translation_status);
CREATE INDEX idx_translation_is_edited ON translations(is_edited);

-- 6. 创建 PublicationRecord 表
CREATE TABLE publication_records (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    platform VARCHAR(50) NOT NULL,
    platform_record_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    published_at DATETIME,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE INDEX idx_pub_episode ON publication_records(episode_id);
CREATE INDEX idx_pub_platform ON publication_records(platform);
CREATE INDEX idx_pub_status ON publication_records(status);

-- 7. 创建 TranslationCorrection 表
CREATE TABLE translation_corrections (
    id INTEGER PRIMARY KEY,
    cue_id INTEGER NOT NULL,
    language_code VARCHAR(10) NOT NULL,
    original_text TEXT NOT NULL,
    corrected_text TEXT NOT NULL,
    ai_model VARCHAR(50),
    corrected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cue_id) REFERENCES transcript_cues(id) ON DELETE CASCADE
);

CREATE INDEX idx_corr_cue ON translation_corrections(cue_id);
CREATE INDEX idx_corr_language ON translation_corrections(language_code);

-- 8. 创建 MarketingPost 表（内容赛马）
CREATE TABLE marketing_posts (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    chapter_id INTEGER,
    platform VARCHAR(50) NOT NULL,
    angle_tag VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
);

CREATE INDEX idx_marketing_episode ON marketing_posts(episode_id);
CREATE INDEX idx_marketing_chapter ON marketing_posts(chapter_id);
CREATE INDEX idx_marketing_platform ON marketing_posts(platform);
CREATE INDEX idx_marketing_angle ON marketing_posts(angle_tag);
CREATE INDEX idx_marketing_ep_angle ON marketing_posts(episode_id, angle_tag);
```

---

## 7. 附录

### 7.1 数据字典

| 表名 | 中文名 | 记录数估算 | 说明 |
| --- | --- | --- | --- |
| episodes | 剧集表 | 100-1000 | 存储视频/音频元数据 |
| audio_segments | 音频分段表 | 500-5000 | 虚拟分段，约每个Episode 5-10个分段 |
| transcript_cues | 字幕表 | 10000-100000 | 单句字幕（英文），约每个Episode 100-1000条 |
| translations | 翻译表 | 10000-200000 | **RLHF 双文本**存储，约每个Cue 1-2种语言 |
| chapters | 章节表 | 200-2000 | AI语义切分的章节，约每个Episode 2-10个 |
| marketing_posts | 营销文案表 | 500-5000 | **内容赛马**，约每个Episode 5-10条多角度文案 |
| publication_records | 发布记录表 | 200-4000 | 分发记录，约每个Episode 1-4个平台 |
| translation_corrections | 翻译修正表 | 1000-10000 | AI修正记录，用于Token优化 |

### 7.2 关键业务规则

1. **断点续传规则**：
   - AudioSegment: 失败时保留segment_path，重试时直接使用
   - Translation: 失败时记录translation_error，重试时重新调用LLM

2. **状态同步规则**：
   - Episode.workflow_status 由工作流阶段决定（手动更新）
   - AudioSegment.status 由转录结果决定（自动更新）
   - Translation.translation_status 由翻译结果决定（自动更新）

3. **数据一致性规则**：
   - 删除Episode时，级联删除所有AudioSegment、TranscriptCue、Chapter、Translation
   - 删除AudioSegment时，级联删除所有TranscriptCue、Translation
   - 删除TranscriptCue时，级联删除所有Translation
   - 删除Chapter时，TranscriptCue.chapter_id 设为 NULL

### 7.3 性能优化建议

1. **批量操作**：
   - 转录时按Segment顺序处理，避免并发
   - 翻译时按批次处理（每批50条Cue），减少API调用

2. **索引维护**：
   - 定期 ANALYZE 表，更新统计信息
   - 监控慢查询，优化索引

3. **数据归档**：
   - 已发布（PUBLISHED）的Episode可考虑归档
   - 临时文件定期清理

---

**文档结束** | 请审核后反馈修改意见
