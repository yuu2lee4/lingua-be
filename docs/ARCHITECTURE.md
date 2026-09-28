# AI 翻译服务架构文档

## 概述

本项目是基于 **Claude Agent SDK** 构建的智能翻译服务，采用多 Agent 协作架构，提供高质量的多语言翻译能力。

### 核心特性

- **多 Agent 协作** - 翻译、质量评审、一致性评审 Agent 协同工作
- **异步/同步翻译** - 支持异步任务处理和同步阻塞翻译两种模式
- **智能重试机制** - 基于质量反馈的自动重试优化
- **术语表支持** - 确保专业术语翻译一致性
- **多 LLM 支持** - 支持 Claude、OpenAI、Gemini 等多种模型
- **Tolgee 集成** - 从 Tolgee 翻译平台同步术语数据
- **Web UI** - Next.js 前端管理界面

---

## 技术栈

| 组件 | 技术选型 |
|------|----------|
| Web 框架 | FastAPI + Uvicorn |
| AI Agent | Claude Agent SDK |
| 语言 | Python 3.13+ |
| 包管理 | uv |
| 配置中心 | Apollo |
| 数据库 | MySQL + aiomysql |
| 日志 | Loguru |
| 代码质量 | Black + Ruff + MyPy |
| 容器化 | Docker |

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         客户端请求                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI 应用层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   /healthz   │  │  /api/v1/    │  │  异常处理 & CORS      │  │
│  │   健康检查    │  │  路由分发     │  │                       │  │
│  └──────────────┘  └──────┬───────┘  └──────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         服务层 (Services)                        │
│  ┌────────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ TranslationService │  │   JobService   │  │GlossaryService│  │
│  │   翻译任务管理      │  │   任务状态管理  │  │  术语表管理   │  │
│  └─────────┬──────────┘  └───────┬────────┘  └──────┬───────┘  │
└─────────────┼────────────────────┼──────────────────┼───────────┘
              │                    │                  │
              ▼                    ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    数据访问层 (Repositories)                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  GlossaryRepository                       │  │
│  │  • 术语 CRUD    • 翻译管理    • 候选术语管理    • 导入导出  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┼───────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 层 (Agents)                           │
│  ┌─────────────────────────────────────────────────┐            │
│  │                  LeadAgent                       │            │
│  │                 (流程编排器)                      │            │
│  └────────────┬──────────────┬──────────────────────┘            │
│               │              │                                   │
│   ┌───────────▼───────┐  ┌───▼────────────────┐  ┌───────────┐  │
│   │ TranslationAgent  │  │   Review Agents    │  │ Glossary  │  │
│   │   (翻译执行器)     │  │  ┌──────────────┐  │  │ Extraction│  │
│   │                   │  │  │QualityAgent  │  │  │  Agent    │  │
│   │  • 术语查找        │  │  │ (质量评审)    │  │  │           │  │
│   │  • 提示词构建      │  │  └──────────────┘  │  │ • AI提取   │  │
│   │  • LLM 调用       │  │  ┌──────────────┐  │  │ • 候选入库 │  │
│   │  • 结果验证        │  │  │ConsistencyAg │  │  │           │  │
│   │                   │  │  │ (一致性评审)  │  │  │           │  │
│   └───────────────────┘  │  └──────────────┘  │  └───────────┘  │
│                          └────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      基础设施层                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ UnifiedLLM   │  │   JobStore   │  │      Config          │  │
│  │   Client     │  │  (内存存储)   │  │   (Apollo 配置)       │  │
│  │              │  │              │  │                      │  │
│  │ • Claude     │  │ • 任务存储    │  │ • API Keys           │  │
│  │ • OpenAI     │  │ • TTL 清理   │  │ • 模型配置            │  │
│  │ • Gemini     │  │ • 状态管理    │  │ • MySQL 配置          │  │
│  │ • Bedrock    │  │              │  │ • Bedrock 配置        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    DatabasePool (MySQL)                   │  │
│  │  • 异步连接池   • 自动重连   • 连接回收   • DictCursor     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
app/
├── main.py                    # FastAPI 应用入口
├── api/
│   └── v1/
│       ├── router.py          # API v1 路由聚合
│       └── endpoints/
│           ├── translation.py # 翻译端点
│           ├── glossary.py    # 术语表端点
│           └── visual_review.py # 视觉评审端点
├── agents/                    # Agent 实现
│   ├── base.py               # 基础 Agent 抽象类
│   ├── translation_agent.py  # 翻译 Agent（UI-First 策略 v3 + 术语表合规优先 + 源语言冲突解决）
│   ├── lead_agent.py         # 流程编排 Agent
│   ├── glossary_extraction_agent.py  # 术语提取 Agent
│   └── review/
│       ├── quality_agent.py      # 质量评审 Agent
│       ├── consistency_agent.py  # 一致性评审 Agent
│       └── visual_review_agent.py # 视觉评审 Agent（多模态）
├── schemas/                   # Pydantic 数据模型
│   ├── translation.py        # 翻译相关模型（含 key 上下文字段）
│   ├── job.py                # 任务模型
│   ├── glossary.py           # 术语表模型
│   ├── glossary_db.py        # 术语表数据库模型
│   ├── lark_job.py           # Lark 翻译任务模型
│   ├── review.py             # 评审模型
│   └── visual_review.py      # 视觉评审模型
├── services/                  # 业务逻辑层
│   ├── translation_service.py
│   ├── job_service.py
│   ├── glossary_service.py        # Level 2: 业务 AI 术语库
│   ├── match_glossary_service.py  # Level 1: 匹配术语库
│   ├── binance_glossary_service.py # Binance 交易所术语库
│   └── visual_review_service.py   # 视觉评审服务
├── repositories/              # 数据访问层
│   └── glossary_repository.py # 术语表 Repository
├── db/                        # 数据库层
│   └── connection.py         # MySQL 连接池
├── clients/
│   ├── llm_client.py         # 统一 LLM 客户端（支持多模态 + Bedrock）
│   ├── lark_client.py        # Lark 飞书 API 客户端（Sheets + Bitable）
│   ├── sandbox_client.py     # 浏览器沙盒客户端（ai-sandbox REST API）
│   └── cua_sandbox_client.py # CUA 持久化沙盒客户端（duck-type 兼容）
├── config/
│   ├── configuration.py      # Apollo 配置
│   └── settings.py           # 环境设置
├── core/
│   ├── constants.py          # 常量定义
│   └── exceptions.py         # 自定义异常
├── storage/
│   └── job_store.py          # 任务存储
├── logger/
│   └── logging.py            # 日志配置
└── utils/                    # 工具函数

xxl_lark_translation.py        # XXL-JOB 定时任务入口（Lark 翻译 + 术语同步）

data/
├── glossary.json              # 业务 AI 术语库数据（从 CSV 转换）
├── glossary.csv               # 术语源数据（从外部系统导出）
└── binance_glossary/
    └── binance_glossary.json  # Binance 交易所多语言 UI 术语

examples/
└── glossary.yaml              # 匹配术语库源数据

frontend/                      # Next.js 前端应用
├── src/
│   ├── app/                   # 页面路由
│   │   ├── glossary/          # 术语管理页面
│   │   ├── translations/      # 翻译任务页面
│   │   └── visual-review/     # 视觉评审页面
│   ├── components/            # UI 组件 (shadcn/ui)
│   └── lib/                   # API 客户端和工具函数
├── package.json
└── pnpm-lock.yaml

scripts/
├── convert_glossary.py        # 术语表格式转换脚本（CSV → JSON/YAML）
├── entrypoint.sh              # K8s 统一入口（3 服务并行）
├── entrypoint-api.sh          # API-only 入口
└── entrypoint-xxl.sh          # XXL-JOB Executor-only 入口

migrations/
└── 002_create_two_glossary_tables.sql   # 两级术语库表
```

---

## 核心组件

### 1. Agent 层

#### BaseAgent

所有 Agent 的抽象基类，提供统一的生命周期管理和 LLM 调用接口。

```python
class BaseAgent(ABC):
    agent_type: str
    default_model: str

    async def setup(self) -> None
    async def cleanup(self) -> None
    async def _call_llm(messages, temperature, max_tokens) -> str
    async def run(*args, **kwargs) -> Any  # 抽象方法
```

**特性**:
- 支持异步上下文管理器
- 统一的 LLM 调用封装
- 可配置的模型选择

#### TranslationAgent

执行单个语言的翻译任务，采用 **UI-First 翻译策略**。

**职责**:
- 从源文本中查找相关术语（两级术语表）
- 获取目标语言的本地交易所标准和敬语规则
- 构建包含术语表、标点规则、交易所标准的提示词
- 调用 LLM 执行翻译
- 应用 Level 1 直接匹配覆盖
- 验证术语匹配情况

**输入**: `source_text`, `feedback` (可选的评审反馈), `key` (可选的上下文标识键)
**输出**: `TranslationItem`

**UI-First 翻译策略** (Prompt v3):

翻译提示词包含 6 个步骤，优先级：术语表合规 > 源文准确性 > 本地交易所惯例 > UI 清晰度：
1. **Glossary Compliance** (最高优先级) - 术语表检查必须在所有翻译决策之前执行，精确使用术语表翻译
2. **Source Language Conflict Resolution** - 英中无冲突时结合理解；冲突时以英文为准
3. **Preserve Technical Elements** - 保留占位符、数字、符号和格式
4. **Follow Local Exchange Standards** - 参考本地交易所惯例（如 BitFlyer、Upbit 等）
5. **Apply UI-First Translation Principles** - 按 UI 元素类型翻译（按钮→动作动词, 状态标签→行业术语, 描述→完整短语）
6. **Language-Specific Rules** - 标点符号和敬语/正式度规则

**语言分组与规则**:

| 语言分组 | 语言 | 标点规则 | 敬语/正式度 |
|---------|------|---------|------------|
| CJK | zh-CN, zh-TW, ja-JP, ko-KR | 全角标点，CJK 字符间不加空格 | ja-JP: です/ます体, ko-KR: 존댓말 |
| 东南亚 | vi-VN, id-ID | 各语言独立规则 | vi-VN, id-ID: 专业但平易 |
| 阿拉伯 | ar | RTL 标点 (، ؛ ؟) | - |
| 法语 | fr-FR | 标点前加不间断空格 | - |
| 西方 | de-DE, es-ES, pt-BR, ru-RU, uk-UA | 半角标点 | de-DE: Sie 形式, es-ES: usted 形式, pt-BR: 专业但平易 |

**本地交易所标准** (12 种语言):

为以下语言提供本地交易所术语参考: vi-VN, ja-JP, ko-KR, es-ES, fr-FR, de-DE, pt-BR, ru-RU, ar, uk-UA, id-ID。包含 "Deposit"、"Withdraw"、"Executed"、"More" 等常用交易 UI 术语的本地化标准。

#### QualityReviewAgent

评估翻译质量并给出 PASS/FAIL 判定和评分。

**评估流程** (分步执行):
1. **术语表检查** (门控) - 官方术语表术语必须精确匹配，不匹配则 Hard Fail (mark=0)
2. **源语言冲突判定** - 英中冲突时以英文为准
3. **质量评估** - Accuracy 35 + Terminology 30 + Fluency 20 + Style 15

**优先级**: Glossary Compliance > Accuracy > Binance Terminology > Fluency > Style

**输入**: `source_text`, `translated_text`, `target_lang`, `source_text_2` (可选)
**输出**: `QualityReviewResult`

#### ConsistencyReviewAgent

检查多语言翻译的术语一致性（按语言对循环组合评审）。

**检查项**:
- 不同语言中相同术语的翻译是否一致
- 翻译是否符合术语表预期
- 是否存在可能导致用户困惑的术语不一致

**评审方式**: 对所有目标语言进行循环组合评审：(1,2), (2,3), ..., (n-1,n), (n,1)
例如 3 种语言 [zh-CN, ja-JP, ko-KR] 会产生 3 个语言对：zh-CN↔ja-JP, ja-JP↔ko-KR, ko-KR↔zh-CN

**输入**: `source_text`, `translations` (两个语言的翻译列表)
**输出**: `ConsistencyPairResult`

#### VisualReviewAgent

通过浏览器沙盒截图 + 多模态 LLM 分析翻译在真实 UI 中的视觉呈现质量。

**评估维度**:
- 布局质量 (Layout Quality): 文本溢出、截断、布局错乱
- 文本渲染 (Text Rendering): 编码问题、字体渲染、乱码
- 翻译完整性 (Translation Completeness): 未翻译残留、占位符可见

**工作流程**:
1. 创建浏览器沙盒（Docker 容器）
2. 截取参考语言（en-US）页面截图
3. 逐个目标语言：导航 → 截图 → 构建多模态消息 → Claude Vision 分析
4. 汇总评审结果，销毁沙盒

**依赖**: ai-sandbox 服务或 CUA 持久化沙盒服务（二选一）

**沙盒客户端**:
- `SandboxClient`: Docker 容器沙盒，按需创建/销毁
- `CuaSandboxClient`: CUA 持久化浏览器服务，duck-type 兼容，无需创建/销毁容器

**输入**: `VisualReviewRequest`
**输出**: `VisualReviewResponse`

> 详细流程参见 [VISUAL_REVIEW.md](VISUAL_REVIEW.md)

#### LeadAgent

翻译流程编排器，协调整个翻译流程。

**流程编排**:

```
┌────────────────────────────────────────────────────────────────┐
│                      LeadAgent 工作流程                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Phase 1: 初始翻译                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  并行翻译所有目标语言（传递 key 上下文）                      │  │
│  │  TranslationAgent × N (N = 目标语言数)                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 2: 质量评审                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  并行评审所有翻译结果                                       │  │
│  │  QualityReviewAgent × N                                   │  │
│  │  识别未通过阈值的翻译                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 3: 重试循环 (最多 max_retries 次)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  while 存在未通过的翻译 and 重试次数 < max_retries:         │  │
│  │      1. 携带反馈重新翻译                                    │  │
│  │      2. 重新进行质量评审                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 4: 一致性评审（语言对循环组合）                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  对所有语言对执行一致性评审（循环组合方式）                    │  │
│  │  ConsistencyReviewAgent × N (N=语言数)                      │  │
│  │  组合方式: (1,2), (2,3), ..., (n-1,n), (n,1)                │  │
│  │  例如: 3语言 → 3对, 4语言 → 4对, 5语言 → 5对               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  返回 TranslationResponse                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 2. 服务层

#### TranslationService

翻译任务的主入口，负责任务的创建、执行和管理。

**核心方法**:
- `submit_translation()` - 提交异步翻译任务（返回 job_id，后台执行）
- `_execute_translation()` - 后台执行任务
- `translate_sync()` - 同步执行翻译（阻塞等待结果，直接返回 TranslationResponse）
- `cancel_translation()` - 取消任务

#### VisualReviewService

视觉评审服务，协调 VisualReviewAgent 执行多模态视觉评审。

**核心方法**:
- `execute_visual_review()` - 创建沙盒 → 执行评审 → 清理资源

**特性**: 沙盒不可用时返回降级响应（`sandbox_error`），不抛异常。

> 详细说明参见 [VISUAL_REVIEW.md](VISUAL_REVIEW.md)

#### JobService

任务状态管理服务。

**核心方法**:
- `create_job()` - 创建新任务
- `get_job_status()` - 获取任务状态
- `update_progress()` - 更新任务进度
- `complete_job()` / `fail_job()` - 完成/失败任务

#### GlossaryService (Level 2: 业务 AI 术语库)

业务 AI 术语库服务，提供 AI 策划的专业术语用于提示词丰富。

**核心方法**:
- `load_glossary()` - 从 JSON 文件加载术语表（支持缓存）
- `load_glossary_from_db()` - 从数据库加载术语表（支持缓存）
- `get_business_terms_for_prompt()` - 获取用于提示词丰富的术语
- `get_two_tier_glossary_data()` - 同时获取两级术语数据
- `invalidate_db_cache()` - 使数据库缓存失效
- `warmup_cache()` - 预热缓存

**缓存策略**:
- 内存缓存 TTL: 60 分钟
- 写操作自动触发缓存失效
- 应用启动时预热缓存
- 数据库不可用时自动降级到文件模式

#### MatchGlossaryService (Level 1: 匹配术语库)

匹配术语库服务，提供直接翻译查找功能。

**核心方法**:
- `lookup_translation()` - 查找单个术语的翻译
- `get_direct_matches()` - 从源文本中查找所有匹配术语
- `upsert_translations_batch()` - 批量插入或更新翻译
- `initialize_from_yaml()` - 从 YAML 文件初始化术语库
- `warmup_cache()` - 预热缓存

**数据源**:
- 主要从 `examples/glossary.yaml` 加载
- 支持数据库持久化和内存缓存
- 使用词边界匹配确保精确匹配

#### BinanceGlossaryService (Binance 交易所术语库)

Binance 交易所多语言 UI 术语服务，从 Binance 网站爬取的术语数据中提供 L1 直接匹配和 L2 提示词增强。

**核心方法**:
- `load()` - 从 JSON 文件加载术语，拆分为 L1 和 L2
- `get_direct_matches()` - L1 匹配：首词倒排索引 + 词边界精确匹配
- `get_prompt_terms()` - L2 提示词术语：仅质量过滤的短术语（≤4 词）
- `get_l2_glossary()` - 返回 L2 Glossary 对象（供一致性评审合并用）

**L1/L2 拆分策略**:
- L1（全部术语）: 用于直接翻译匹配，约 16K 术语
- L2（质量过滤）: 仅 ≤4 词的短术语，排除占位符、交易对、小数价格

**性能优化**:
- 首词倒排索引避免遍历全部术语
- 内存缓存，Cache TTL: 2 小时
- 每次提示词最多包含 30 条术语

**数据来源**: `data/binance_glossary/binance_glossary.json`

#### GlossaryExtractionAgent

基于人工翻译结果的术语提取 Agent。

**职责**:
- 分析源文本和人工翻译
- 识别专业术语、产品名称、技术概念
- 生成候选术语并存入数据库

**输入**: `GlossaryExtractRequest` (source_text, human_translation, target_lang, translation_job_id)
**输出**: `GlossaryExtractResponse` (extracted_terms, candidates_created)

**提取标准**:
- 专业术语：特定领域的专业词汇
- 产品名称：品牌、产品、功能名称
- 技术概念：技术术语、API 名称、操作名称
- 行业用语：金融、区块链、交易等行业专用词汇

**不提取的内容**:
- 日常用语
- 通用动词和形容词
- 已有明确翻译规范的常见词

**批量处理**:
支持 `extract_batch()` 方法进行批量术语提取

### 3. 数据访问层

#### GlossaryRepository

术语表数据访问层，封装所有数据库操作。

**术语 CRUD**:
- `create_term()` - 创建术语
- `get_term_by_id()` / `get_term_by_en()` - 查询术语
- `update_term()` - 更新术语
- `delete_term()` - 删除术语（软删除）
- `list_terms()` - 分页列表
- `search_terms()` - 搜索术语
- `get_all_active_terms()` - 获取所有激活术语

**翻译管理**:
- `update_translation()` - 更新术语翻译

**候选术语管理**:
- `create_candidate()` - 创建候选术语
- `list_candidates()` - 列出候选术语
- `review_candidate()` - 审核候选术语

**导入导出**:
- `import_terms()` - 批量导入术语

### 4. 基础设施层

#### UnifiedLLMClient

统一的 LLM 客户端，支持多个 LLM 提供商和 AWS Bedrock。

**支持的提供商**:
| 提供商 | 模型 | 备注 |
|--------|------|------|
| Anthropic | `claude-sonnet-4-5-20250929`, `claude-opus-4-6` | 支持原生 API + Bedrock |
| OpenAI | `gpt-4o-mini`, `gpt-5-mini`, `gpt-5.2` | 推理模型自动关闭 thinking |
| Google | `gemini-2.5-flash`, `gemini-3-flash-preview`, `gemini-3-pro-preview` | 按版本配置 thinking level |

**Agent 默认模型配置**:
| Agent 类型 | 默认模型 |
|------------|----------|
| TranslationAgent | `claude-opus-4-6` |
| QualityReviewAgent | `gpt-5.2` |
| ConsistencyReviewAgent | `gpt-5.2` |
| GlossaryExtractionAgent | `claude-opus-4-6` |
| VisualReviewAgent | `claude-sonnet-4-5-20250929` |

**AWS Bedrock 支持**:
- 通过 `USE_BEDROCK=true` 环境变量启用
- 使用 Bearer Token 认证（跳过 SigV4 签名），自定义 `AsyncAnthropicBedrockBearer` 类
- 自动将原生模型名映射到 Bedrock 模型 ID:
  - `claude-sonnet-4-5-20250929` → `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
  - `claude-opus-4-6` → `us.anthropic.claude-opus-4-6-v1`
- 环境变量: `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`（默认 us-west-2）

**自动功能**:
- 根据模型名称自动选择提供商
- 自动配置 API 密钥和端点
- 统一的调用接口
- 推理模型自动关闭/降低 thinking（GPT-5.x: none, o1/o3: low, Gemini: 按版本配置）

#### JobStore

内存实现的任务存储。

**特性**:
- 基于字典的快速查找
- 后台清理任务 (每分钟运行)
- TTL 自动过期 (默认 1 小时)
- 支持状态过滤查询

#### DatabasePool

MySQL 异步连接池管理器。

**核心方法**:
- `initialize()` - 初始化连接池
- `close()` - 关闭连接池
- `acquire()` - 获取连接（上下文管理器）
- `execute()` - 执行写操作
- `fetch_one()` / `fetch_all()` - 查询操作
- `insert_and_get_id()` - 插入并返回自增 ID

**特性**:
- 基于 aiomysql 的异步连接池
- 自动连接回收和重连
- DictCursor 返回字典格式
- UTF8MB4 字符集支持

#### Configuration

Apollo 配置中心集成。

**配置分类**:
- LLM 配置 (模型名称、回退策略)
- 外部服务配置 (Redis、Consul 等)
- MySQL 数据库配置
- API 密钥配置

---

## 术语库系统 (Glossary System)

### 概述

项目采用两级人工维护术语库 + Binance 交易所术语扩展，分别处理不同场景的术语需求：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Glossary System                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Level 1: Match Glossary (匹配术语库)                            │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  • 用途: 直接翻译替换，确保一致性                           │  │   │
│  │  │  • 数据源: examples/glossary.yaml                         │  │   │
│  │  │  • 服务: MatchGlossaryService                             │  │   │
│  │  │  • 匹配方式: 词边界精确匹配                                 │  │   │
│  │  │  • 数据库表: match_glossary_terms                            │ │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              ↓                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Level 2: Business AI Glossary (业务 AI 术语库)                  │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  • 用途: 提示词丰富，为 LLM 提供术语定义和上下文            │  │   │
│  │  │  • 数据源: data/glossary.json 或 MySQL                    │  │   │
│  │  │  • 服务: GlossaryService                                  │  │   │
│  │  │  • 包含: 术语定义、词性、翻译建议                           │  │   │
│  │  │  • 数据库表: business_glossary_terms                         ││
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              ↓                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Binance Glossary (交易所术语扩展)                                │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  • 用途: 补充交易所 UI 术语（不覆盖人工维护数据）             │  │   │
│  │  │  • 数据源: data/binance_glossary/binance_glossary.json││
│  │  │  • 服务: BinanceGlossaryService                           │  │   │
│  │  │  • L1 部分: 全部术语用于直接匹配（~16K）                    │  │   │
│  │  │  • L2 部分: 质量过滤的短术语（≤4 词）用于提示词增强          │  │   │
│  │  │  • 性能: 首词倒排索引，内存缓存 2 小时                      │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Level 1: 匹配术语库 (Match Glossary)

**用途**: 提供直接翻译查找，用于翻译过程中的术语替换，确保关键术语翻译一致。

**特点**:
- 词边界精确匹配（使用正则 `\b...\b`）
- 高性能内存缓存
- 自动从 YAML 初始化

**数据格式** (`examples/glossary.yaml`):
```yaml
Copy Trade:
  zh-CN: 跟单交易
  ja-JP: コピートレード
  ko-KR: 카피 트레이딩

Spot Trading:
  zh-CN: 现货交易
  ja-JP: 現物取引
```

**数据库表**:
| 表名 | 说明 |
|------|------|
| `match_glossary_terms` | 匹配术语主表 (term_id, term_en, translation_<lang>, source, status) |

### Level 2: 业务 AI 术语库 (Business AI Glossary)

**用途**: 为 LLM 提供术语定义和上下文，丰富翻译提示词，提高翻译质量。

**特点**:
- 包含术语定义、词性、是否翻译标记
- 支持 AI 术语提取和人工审核
- 用于 TranslationAgent 提示词构建

**数据格式** (`data/glossary.json`):
```json
{
  "terms": [
    {
      "term_id": "abc123",
      "term_en": "Copy Trade",
      "definition": "A feature that allows users to automatically copy trades from other traders",
      "part_of_speech": "noun",
      "do_not_translate": false,
      "translations": {
        "zh-CN": "跟单交易",
        "ja-JP": "コピートレード"
      }
    }
  ]
}
```

**数据库表**:
| 表名 | 说明 |
|------|------|
| `business_glossary_terms` | 业务术语主表 (含 definition, translation_<lang>) |
| `glossary_candidates` | AI 提取的候选术语 (待审核, 含迁移标记) |

### 翻译流程中的应用

```
源文本输入
     │
     ▼
┌────────────────────────────────┐
│  Level 1: 查找直接匹配          │
│  MatchGlossaryService          │
│  get_direct_matches()          │
└──────────────┬─────────────────┘
               │ 返回 {term: translation}
               ▼
┌────────────────────────────────┐
│  Level 2: 获取提示词术语        │
│  GlossaryService               │
│  get_business_terms_for_prompt()│
│  (排除已匹配的 Level 1 术语)    │
└──────────────┬─────────────────┘
               │ 返回 [GlossaryTerm]
               ▼
┌────────────────────────────────┐
│  Binance: 补充交易所术语        │
│  BinanceGlossaryService        │
│  get_direct_matches() → L1 补充 │
│  get_prompt_terms() → L2 补充   │
│  (排除已有 L1/L2 术语)          │
└──────────────┬─────────────────┘
               │ 返回补充术语
               ▼
┌────────────────────────────────┐
│  TranslationAgent              │
│  构建 LLM 提示词:               │
│  - 源文本                       │
│  - Level 1 直接匹配（必须使用）  │
│  - Level 2 术语定义（参考）      │
│  - Binance 术语（补充参考）      │
└────────────────────────────────┘
```

### Binance 术语库特性

**数据特点**:
- 短术语（1-4 词）: 行业术语，适合 L1 直接匹配 + L2 提示词增强
- 长 UI 字符串（5+ 词）: 仅用于 L1 翻译记忆匹配，不放入提示词
- 无 definition 和 part_of_speech 字段（来自 DOM/i18n 爬取）

**L2 质量过滤条件**:
- 长度 > 2 字符
- 以字母开头
- 词数 ≤ 4
- 不含占位符（`{n}`, `${value}` 等）
- 不含交易对模式（`BTC/USDT` 等）
- 不含小数价格数据（`0.001` 等）

**在质量评审中的应用**:
QualityReviewAgent 使用 Binance L2 术语作为术语参考，评估翻译中交易所专业术语的准确性。

---

## Tolgee 翻译平台集成

### 概述

项目集成 Tolgee 翻译平台作为术语库管理的外部数据源，通过 webhook 或 API 调用将 Tolgee 上维护的术语数据同步到本地两级术语库。

### 同步机制

```
┌─────────────────────┐
│   Tolgee Platform   │
│   (术语管理)         │
└──────────┬──────────┘
           │ POST /api/v1/glossary/sync
           ▼
┌─────────────────────────────────────────────────────────┐
│                sync_glossary 端点                         │
│  ┌────────────────────────────────────────────────────┐  │
│  │  glossary_level == L1_MATCH?                       │  │
│  │    → MatchGlossaryService.upsert_translations_batch│  │
│  │  glossary_level == L2_BUSINESS?                    │  │
│  │    → GlossaryRepository.create/update_term         │  │
│  └────────────────────────────────────────────────────┘  │
│  → 清除相关缓存                                          │
│  → 返回同步结果 (synced count + errors)                   │
└─────────────────────────────────────────────────────────┘
```

### 数据映射

| Tolgee 字段 | 本地字段 | 说明 |
|-------------|----------|------|
| `term_text` | `term_en` | 基础语言术语 |
| `description` | `definition` | 术语描述/定义 |
| `translations` | `translation_<lang>` | 各语言翻译 |
| `is_non_translatable` | `do_not_translate` | 不翻译标记 |

---

## Lark 飞书集成

### 概述

项目集成飞书（Lark）电子表格作为翻译任务管理和术语库维护的协作界面，通过 XXL-JOB 定时任务实现自动化处理。

### 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Lark 电子表格                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  翻译表格 (多个工作表)                                     │    │
│  │  列: source_text, target_language, target_text,         │    │
│  │      status, mqm, review_summary, properties            │    │
│  └────────────────────────┬────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  术语库表格 (3 个工作表)                                   │    │
│  │  • match_glossary_terms（匹配术语库）                      │    │
│  │  • business_glossary_terms（业务术语库）                    │    │
│  │  • glossary_candidates（候选术语）                          │    │
│  └────────────────────────┬────────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────────┘
                            │ Lark API (LarkSheetsClient)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   XXL-JOB 定时任务                                │
│  ┌───────────────────────┐  ┌────────────────────────────────┐  │
│  │ sync_lark_translations│  │ sync_lark_glossary             │  │
│  │ 处理 status="new"     │  │ 处理 status="reviewed"         │  │
│  │ → 调用翻译服务         │  │ → 提取术语 (GlossaryExtraction)│  │
│  │ → 更新 target_text    │  │ → 更新 status="completed"      │  │
│  └───────────────────────┘  └────────────────────────────────┘  │
│  ┌───────────────────────┐  ┌────────────────────────────────┐  │
│  │sync_lark_glossary_    │  │ migrate_glossary_candidates    │  │
│  │          tables       │  │ 迁移 status="approved" 候选术语 │  │
│  │ 双向同步术语库表       │  │ → 写入 business_glossary_terms │  │
│  └───────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Lark 客户端

#### LarkSheetsClient

电子表格 API 客户端，提供读写操作。

**核心方法**:
- `read_sheet_as_dataframe()` - 读取表格为 DataFrame
- `write_dataframe_to_sheet()` - 写入 DataFrame 到表格
- `write_rows_to_sheet()` - 按行写入指定位置
- `add_sheet()` - 添加新工作表

#### LarkBitableClient

多维表格 API 客户端，提供 CRUD 操作。

**核心方法**:
- `list_all_records()` - 列出所有记录（自动分页）
- `list_records_as_dataframe()` - 列出记录为 DataFrame
- `update_record()` / `batch_update_records()` - 更新记录

### Lark 翻译任务状态

| 状态 | 说明 |
|------|------|
| `new` | 新建，待翻译 |
| `translated` | 已翻译，待审核 |
| `reviewed` | 已审核，待同步术语 |
| `completed` | 已完成 |
| `problem` | 有问题 |

### XXL-JOB 定时任务

| 任务名 | 功能 | 处理对象 |
|--------|------|---------|
| `sync_lark_translations` | 翻译 Lark 表格中新任务 | status="new" 的记录 |
| `sync_lark_glossary` | 从已审核翻译提取术语 | status="reviewed" 的记录 |
| `sync_lark_glossary_tables` | 双向同步术语库表 | 三张术语库表 |
| `migrate_glossary_candidates` | 迁移已批准候选术语 | status="approved" 的候选术语 |

**翻译任务优化**: 相同 `source_text` 但不同 `target_language` 的行会被合并为一个多语言翻译任务，减少 LLM 调用次数。

---

## 数据流

### 翻译请求处理流程

```
┌──────────┐    ┌───────────────┐    ┌─────────────────────┐
│  客户端   │───▶│  API 端点     │───▶│ TranslationService  │
└──────────┘    └───────────────┘    └──────────┬──────────┘
                                                │
                 ┌──────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│                     异步任务执行                            │
│                                                            │
│  ┌──────────────────┐                                      │
│  │    JobService    │ ◀─── 创建任务，状态: pending         │
│  └────────┬─────────┘                                      │
│           │                                                │
│           ▼ 状态更新: in_progress                          │
│  ┌──────────────────┐                                      │
│  │   LeadAgent      │ ◀─── 加载术语表                      │
│  └────────┬─────────┘                                      │
│           │                                                │
│           ├───────────────────────────────────┐            │
│           ▼                                   ▼            │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │TranslationAgent  │  × N (并行)  │TranslationAgent  │    │
│  │    (zh-CN)       │              │    (ja-JP)       │    │
│  └────────┬─────────┘              └────────┬─────────┘    │
│           │                                 │              │
│           └─────────────┬───────────────────┘              │
│                         ▼                                  │
│           ┌──────────────────┐                             │
│           │ QualityReview    │  × N (并行)                 │
│           │    Agents        │                             │
│           └────────┬─────────┘                             │
│                    │                                       │
│                    ▼ (如有未通过，重试)                     │
│           ┌──────────────────┐                             │
│           │ ConsistencyReview│  × N 语言对                 │
│           │     Agents       │  (循环组合评审)             │
│           └────────┬─────────┘                             │
│                    │                                       │
│                    ▼                                       │
│           ┌──────────────────┐                             │
│           │   JobService     │ ◀─── 状态更新: completed    │
│           └──────────────────┘                             │
│                                                            │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
               ┌──────────────────┐
               │     客户端轮询    │ ◀─── GET /translations/{id}
               └──────────────────┘
```

---

## 质量保证机制

### 1. 质量评审

每个翻译结果都会经过质量评审，采用分步评估流程：

**评估流程**:
1. **术语表检查** (门控) - 官方术语不匹配 → Hard Fail (mark=0)
2. **源语言冲突判定** - 英中冲突时以英文为准
3. **质量评估** (仅在步骤 1-2 通过后):

| 维度 | 分值 | 说明 |
|------|------|------|
| 准确性 (Accuracy) | 35 分 | 核心含义匹配、占位符/数字/符号保留 |
| Binance 术语 (Terminology) | 30 分 | 次要参考，每个偏差扣 3 分 |
| 流畅性 (Fluency) | 20 分 | 目标语言的自然程度 |
| 风格 (Style) | 15 分 | 加密货币/金融领域专业性 |

**评分规则**:
- 总分 0-100 (Accuracy 35 + Terminology 30 + Fluency 20 + Style 15)
- 默认阈值: 95 分
- 低于阈值触发重试
- Hard Fail (mark=0): 术语表不匹配、核心含义错误、占位符/数字/符号错误

### 2. 重试机制

```
翻译结果 ──▶ 质量评审 ──▶ 分数 < 阈值?
                              │
                   ┌──────────┴──────────┐
                   │ Yes                 │ No
                   ▼                     ▼
          重试次数 < max?             通过
                   │
        ┌──────────┴──────────┐
        │ Yes                 │ No
        ▼                     ▼
  携带反馈重新翻译           标记为需改进
```

**反馈内容**:
- 原翻译文本
- 质量评审反馈
- 改进建议列表

### 3. 一致性检查（语言对循环组合）

采用循环组合方式对所有目标语言进行一致性评审，减少语言多时组合数量过多的问题：

**评审流程**:
```
语言列表: [zh-CN, ja-JP, ko-KR]
         ↓
生成循环组合: [(zh-CN, ja-JP), (ja-JP, ko-KR), (ko-KR, zh-CN)]
         ↓
逐对评审: ConsistencyReviewAgent × 3
         ↓
汇总结果: consistency_pair_results[]
```

**检查内容**:
- 相同术语翻译一致
- 符合术语表预期
- 无歧义或混淆

**组合数计算**: N（循环组合方式）
- 2 种语言 → 2 对
- 3 种语言 → 3 对
- 4 种语言 → 4 对
- 5 种语言 → 5 对

相比 C(N,2) 的两两组合方式，循环组合大大减少了评审次数（如 10 种语言从 45 对减少到 10 对）。

---

## 配置管理

### 环境配置

| 环境 | 标识 | Apollo 地址 |
|------|------|-------------|
| 本地 | LOCAL | apollo-config.example.com |
| 开发 | DEV | apollo-service-apollo-configservice.apollo:8080 |
| 测试 | TEST | apollo-service-apollo-configservice.apollo:8080 |
| 生产 | PRO | apollo-service-apollo-configservice.apollo:8080 |

### 模型配置

```python
MODEL_CONFIGS = {
    "claude-sonnet-4-5-20250929": {
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic"
    },
    "claude-opus-4-6": {
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
    },
    "gpt-5.2": {
        "base_url": "https://api.openai.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai"
    },
    # ...
}

AGENT_DEFAULT_MODELS = {
    "translation": "claude-opus-4-6",
    "quality_review": "gpt-5.2",
    "consistency_review": "gpt-5.2",
    "glossary_extraction": "claude-opus-4-6",
    "visual_review": "claude-sonnet-4-5-20250929",
}
```

---

## 日志系统

### 日志配置

| 配置项 | 值 |
|--------|-----|
| 格式 | JSON |
| 轮转 | 500 MB |
| 保留 | 7 天 |
| 压缩 | zip |
| 异步写入 | 是 |

### 日志字段

```json
{
  "level": "INFO",
  "time": "2024-01-22 12:34:56.789",
  "caller": "agents/translation_agent.py:45",
  "msg": "[translate] 翻译完成",
  "tid": "req-123456",
  "event": "translation_complete"
}
```

### 日志规范

所有日志消息必须包含函数名前缀：

```python
logger.info(f"[translate_text] 开始翻译，长度: {len(text)}")
logger.error(f"[translate_text] 翻译失败: {e}")
```

---

## 异常处理

### 异常层级

```
TranslationServiceError (基类)
├── JobNotFoundError          # 任务未找到
├── JobAlreadyExistsError     # 任务已存在
├── JobCancelledError         # 任务已取消
├── TranslationFailedError    # 翻译失败
├── QualityCheckFailedError   # 质量检查失败
├── LLMClientError            # LLM 客户端错误
├── GlossaryLoadError         # 术语表加载错误
├── GlossaryTermNotFoundError # 术语未找到
├── GlossaryTermExistsError   # 术语已存在
├── DatabaseError             # 数据库基础异常
│   ├── DatabaseConnectionError  # 连接错误
│   └── DatabaseQueryError       # 查询错误
├── MaxRetriesExceededError   # 超过最大重试次数
├── SandboxError              # 沙盒操作错误
└── VisualReviewError         # 视觉评审错误
```

### 异常处理策略

| 异常类型 | 处理策略 |
|----------|----------|
| LLMClientError | 重试 + 回退模型 |
| QualityCheckFailedError | 重试 + 记录反馈 |
| GlossaryLoadError | 降级为无术语表模式 |
| MaxRetriesExceededError | 返回最佳结果 + 警告 |

---

## 扩展指南

### 添加新的 Agent

1. 继承 `BaseAgent` 类
2. 设置 `agent_type` 和 `default_model`
3. 实现 `run()` 方法
4. 在 `constants.py` 中添加默认模型配置

```python
from app.agents.base import BaseAgent

class NewAgent(BaseAgent):
    agent_type = "new_agent"
    default_model = "claude-sonnet-4-5-20250929"

    async def run(self, *args, **kwargs) -> Any:
        # 实现逻辑
        pass
```

### 添加新的 LLM 提供商

1. 在 `constants.py` 的 `MODEL_CONFIGS` 中添加模型配置
2. 在 `UnifiedLLMClient` 中添加提供商处理逻辑

### 添加新的语言支持

在 `constants.py` 的 `SUPPORTED_LANGUAGES` 中添加语言代码。

---

## 前端应用 (Frontend)

### 概述

基于 Next.js 构建的 Web 管理界面，提供术语管理、翻译任务管理和视觉评审的可视化操作。

### 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | Next.js 16 + React 19 |
| 语言 | TypeScript |
| UI 组件 | shadcn/ui + Tailwind CSS |
| 包管理 | pnpm |

### 页面功能

| 路由 | 功能 |
|------|------|
| `/glossary` | 术语管理（查看、创建、搜索） |
| `/glossary/candidates` | 候选术语审核（批准/拒绝） |
| `/glossary/import` | 术语批量导入 |
| `/translations` | 翻译任务管理和状态跟踪 |
| `/translations/new` | 提交新翻译任务 |
| `/visual-review` | 视觉评审 |

### API 集成

前端通过 `NEXT_PUBLIC_API_BASE_URL` 环境变量配置后端 API 地址（默认 `http://localhost:8080/api/v1`）。

---

## 部署

### Docker 统一容器部署

项目采用多阶段构建的统一 Docker 容器，包含三个服务：

```
┌─────────────────────────────────────────┐
│          K8s Pod (单容器)                 │
│  ┌───────────────────────────────────┐  │
│  │ Backend API (FastAPI)    :8080    │  │
│  │ XXL-JOB Executor        :9991    │  │
│  │ Frontend (Next.js)       :3000    │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Dockerfile 构建阶段

| 阶段 | 基础镜像 | 产物 |
|------|----------|------|
| py-builder | python:3.13-slim-bookworm | Python 虚拟环境 (.venv) |
| fe-builder | node:22-bookworm-slim | Next.js standalone 产物 |
| production | python:3.13.3-slim-bullseye | 最终运行镜像 |

### 入口脚本

| 脚本 | 用途 |
|------|------|
| `entrypoint.sh` | 统一入口，并行启动 3 个服务 |
| `entrypoint-api.sh` | 仅启动 Backend API |
| `entrypoint-xxl.sh` | 仅启动 XXL-JOB Executor（当前默认） |

### 环境变量

```bash
# 必需
ENV=LOCAL                    # 运行环境
ANTHROPIC_API_KEY=sk-...     # Claude API 密钥

# 可选
GOOGLE_API_KEY=...           # Gemini API 密钥
OPENAI_API_KEY=...           # OpenAI API 密钥

# Bedrock（可选，与 ANTHROPIC_API_KEY 二选一）
USE_BEDROCK=true             # 启用 Bedrock 端点
AWS_BEARER_TOKEN_BEDROCK=... # Bedrock Bearer Token
AWS_REGION=us-west-2         # AWS 区域

# 前端
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080/api/v1  # 后端 API 地址
```

---

## 性能考虑

### 并行处理

- 多语言翻译并行执行
- 质量评审并行执行
- 使用 `asyncio.gather()` 实现

### 缓存策略

- 术语表缓存 (GlossaryService)
- 避免重复加载相同文件

---

## 术语表转换工具

### convert_glossary.py

将外部系统导出的 CSV 术语表转换为项目使用的 JSON/YAML 格式。

**使用方法**:

```bash
# 默认转换
python scripts/convert_glossary.py

# 指定输入输出
python scripts/convert_glossary.py -i data/glossary.csv -o data
```

**支持的语言列**:

| CSV 列名前缀 | 语言代码 |
|-------------|---------|
| Term English (United States) | en-US |
| Term Arabic (International) | ar |
| Term Bengali (Bangladesh) | bn-BD |
| Term Chinese (China-Simplified) | zh-CN |
| Term Chinese (Taiwan-Traditional) | zh-TW |
| Term Dutch (Netherlands) | nl-NL |
| Term French (France) | fr-FR |
| Term German (Germany) | de-DE |
| Term Hindi (India) | hi-IN |
| Term Indonesian (Indonesia) | id-ID |
| Term Japanese (Japan) | ja-JP |
| Term Korean (South Korea) | ko-KR |
| Term Russian (Russia) | ru-RU |
| Term Spanish (Spain) | es-ES |
| Term Thai (Thailand) | th-TH |
| Term Turkish (Turkey) | tr-TR |
| Term Vietnamese (Vietnam) | vi-VN |
| Term Portuguese (Brazil) | pt-BR |

**Do Not Translate 处理**:
- 支持全局和按语言的 Do Not Translate 标记
- 标记为 DNT 的术语将保留英文原文

### 任务管理

- 内存存储 + TTL 自动清理
- 防止内存泄漏
- 支持任务取消

---

## 安全考虑

### API 密钥管理

- 通过环境变量或 Apollo 配置获取
- 禁止硬编码
- 日志中不记录敏感信息

### 输入验证

- Pydantic 模型验证
- 语言代码白名单
- 参数范围限制

### 超时处理

- LLM 调用设置超时
- 异步任务设置最大执行时间
