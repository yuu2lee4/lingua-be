# AI 翻译服务规格说明

## 概述

本文档定义 AI 翻译服务的功能规格、性能指标和质量要求。

---

## 功能规格

### 1. 核心翻译功能

#### 1.1 多语言支持

支持以下 14 种语言的翻译：

| 语言代码 | 语言名称 | 支持方向 |
|----------|----------|----------|
| `en-US` | 英语（美国） | 源语言/目标语言 |
| `zh-CN` | 简体中文 | 目标语言 |
| `zh-TW` | 繁体中文 | 目标语言 |
| `ja-JP` | 日语 | 目标语言 |
| `ko-KR` | 韩语 | 目标语言 |
| `de-DE` | 德语 | 目标语言 |
| `fr-FR` | 法语 | 目标语言 |
| `es-ES` | 西班牙语 | 目标语言 |
| `pt-BR` | 葡萄牙语（巴西） | 目标语言 |
| `ru-RU` | 俄语 | 目标语言 |
| `ar` | 阿拉伯语 | 目标语言 |
| `vi-VN` | 越南语 | 目标语言 |
| `uk-UA` | 乌克兰语 | 目标语言 |
| `id-ID` | 印尼语 | 目标语言 |

#### 1.2 翻译模式

- **异步翻译**: 提交任务后返回任务 ID，通过轮询获取结果（`POST /translations`）
- **同步翻译**: 阻塞等待翻译完成，直接返回结果（`POST /translations/sync`）
- **多语言并行**: 同时翻译多个目标语言
- **术语表支持**: 确保专业术语翻译一致性
- **上下文键**: 支持 `key` 参数提供翻译语境信息（如 UI 元素路径）

#### 1.3 UI-First 翻译策略 (Prompt v3)

翻译采用 UI-First 策略，优先级：术语表合规 > 源文准确性 > 本地交易所惯例 > UI 清晰度。

**提示词 6 步骤**:
1. **Glossary Compliance** (最高优先级) - 术语表检查必须在所有翻译决策之前执行，术语表中的翻译必须精确使用
2. **Source Language Conflict Resolution** - 英中无冲突时结合两种语言理解；冲突时以英文为准
3. **Preserve Technical Elements** - 保留占位符（如 `{{n}}`、`{{amount}}`）、数字、符号和格式
4. **Follow Local Exchange Standards** - 参考本地知名交易所的 UI 用语
5. **Apply UI-First Translation Principles** - 按 UI 元素类型差异化翻译：
   - 按钮 → 本地化动作动词，长度匹配，清晰度 > 极端简短
   - 状态标签 → 行业标准交易术语
   - 描述/提示 → 完整短语，自然语句
6. **Language-Specific Rules** - 标点符号、空格和敬语/正式度规则

**System Prompt**: 定位为加密货币交易所平台的产品 UX 翻译员。

#### 1.4 语言特定规则

##### 标点符号规则

| 语言分组 | 语言 | 规则 |
|---------|------|------|
| CJK | zh-CN, zh-TW, ja-JP, ko-KR | 全角标点（，。！？），CJK 字符间不加空格，技术术语和品牌名保留空格 |
| 东南亚 | vi-VN, id-ID | 半角标点，标点后加空格 |
| 阿拉伯 | ar | 阿拉伯标点（، ؛ ؟），RTL 文本，数字和英文保持 LTR |
| 法语 | fr-FR | 不间断空格置于 ! ? : ; » 之前 |
| 西方 | de-DE, es-ES, pt-BR, ru-RU, uk-UA | 半角标点，标点后加空格 |

##### 敬语/正式度规则

| 语言 | 规则 |
|------|------|
| ja-JP | 使用 です/ます体（礼貌形式），禁止使用随意形式 |
| ko-KR | 使用 존댓말（敬语），禁止使用 반말 |
| de-DE | 使用正式 "Sie" 形式，禁止使用非正式 "du" |
| es-ES | 使用正式 "usted" 形式，禁止使用非正式 "tú" |
| vi-VN, id-ID, pt-BR | 专业但平易的语气，避免过度正式 |

> **注意**: ar-AE, nl-NL, tr-TR, th-TH, hi-IN, bn-BD 已从支持列表移除（v0.8.0）。

##### 本地交易所标准

为 12 种语言提供本地交易所术语参考，涵盖常用 UI 术语（Deposit、Withdraw、Executed、More）：

| 语言 | 参考交易所 |
|------|-----------|
| ja-JP | BitFlyer, Coincheck, GMO Coin |
| ko-KR | Upbit, Bithumb, Coinone |
| vi-VN | Binance VN, MEXC VN |
| es-ES | Binance, Bitso, Bit2Me |
| fr-FR | Binance, Kraken, Paymium |
| de-DE | Binance, Kraken, Bitcoin.de |
| pt-BR | Binance, Mercado Bitcoin, Foxbit |
| ru-RU | Binance, Garantex, Exmo |
| ar | Binance, Rain, BitOasis |
| uk-UA | Binance, Kuna, WhiteBIT |
| id-ID | Indodax, Tokocrypto, Pintu, TRIV |

### 2. 质量保证机制

#### 2.1 质量评审

每个翻译结果经过 QualityReviewAgent 评审，采用分步评估流程：

**评估流程**:
1. **术语表检查** (门控) - 官方术语表术语必须精确匹配，任何不匹配 → Hard Fail (mark=0)
2. **源语言冲突判定** - 英中无冲突时结合两种语言作为参考；冲突时以英文为准
3. **质量评估** (仅在步骤 1-2 通过后执行)

| 维度 | 分值 | 说明 |
|------|------|------|
| 准确性 (Accuracy) | 35 分 | 核心含义匹配、占位符/数字/符号保留（错误则 Hard Fail） |
| Binance 术语 (Terminology) | 30 分 | 次要参考，每个偏差扣 3 分，非 Hard Fail |
| 流畅性 (Fluency) | 20 分 | 目标语言的自然程度，适合 UI 场景 |
| 风格 (Style) | 15 分 | 加密货币/金融领域专业性，简洁易用 |

**评分规则**:
- 总分范围: 0-100
- 权重: Accuracy 35 + Terminology 30 + Fluency 20 + Style 15 = 100
- 默认通过阈值: 95 分
- 低于阈值触发自动重试
- Hard Fail 条件: 术语表不匹配、核心含义错误、占位符/数字/符号错误 → mark=0

#### 2.2 一致性评审

对所有目标语言进行循环组合的一致性评审，减少语言多时组合数量过多的问题：

```
目标语言: [A, B, C]
循环组合: [(A,B), (B,C), (C,A)]
组合数量: N (而非 C(N,2) = N×(N-1)/2)
```

**检查内容**:
- 相同源文本的术语翻译是否一致
- 是否符合术语表定义
- 是否存在可能导致混淆的不一致

#### 2.3 自动重试

- 默认最大重试次数: 2 次
- 重试携带质量反馈，指导 LLM 改进翻译
- 重试后重新进行质量评审

### 3. 任务管理

#### 3.1 任务状态

| 状态 | 说明 |
|------|------|
| `pending` | 等待处理 |
| `in_progress` | 处理中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `cancelled` | 已取消 |

#### 3.2 翻译阶段

| 阶段 | 说明 |
|------|------|
| `pending` | 等待开始 |
| `translating` | 翻译中 |
| `quality_review` | 质量评审中 |
| `retrying` | 重试翻译中 |
| `consistency_review` | 一致性评审中 |
| `completed` | 已完成 |

#### 3.3 任务生命周期

- 任务 TTL: 1 小时（3600 秒）
- 自动清理: 每分钟执行一次
- 支持手动取消: 仅限 `pending` 和 `in_progress` 状态

---

## 模型配置

### 支持的 LLM 提供商

| 提供商 | 模型 | 用途 | 备注 |
|--------|------|------|------|
| Anthropic | `claude-sonnet-4-5-20250929` | 翻译、评审 | 支持原生 API + Bedrock |
| Anthropic | `claude-opus-4-6` | 高质量翻译 | 支持原生 API + Bedrock |
| OpenAI | `gpt-4o-mini` | 翻译、评审 | - |
| OpenAI | `gpt-5-mini` | 翻译、评审 | - |
| OpenAI | `gpt-5.2` | 翻译、评审 | 推理模型，自动关闭 thinking |
| Google | `gemini-2.5-flash` | 翻译、评审 | thinking_budget=0 |
| Google | `gemini-3-flash-preview` | 翻译、评审 | thinking_level=minimal |
| Google | `gemini-3-pro-preview` | 高质量翻译 | thinking_level=low |

### AWS Bedrock 支持

通过 `USE_BEDROCK=true` 环境变量启用，使用 Bearer Token 认证访问 AWS Bedrock 上的 Claude 模型。

**Bedrock 模型映射**:

| 原生模型 | Bedrock 模型 ID |
|----------|-----------------|
| `claude-sonnet-4-5-20250929` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `claude-opus-4-6` | `us.anthropic.claude-opus-4-6-v1` |

**认证方式**: Bearer Token（自定义 `AsyncAnthropicBedrockBearer` 类，跳过 SigV4 签名）

**配置**:

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `bedrock.use_bedrock` / `USE_BEDROCK` | 是否启用 Bedrock | `false` |
| `bedrock.aws_bearer_token` / `AWS_BEARER_TOKEN_BEDROCK` | Bearer Token | - |
| `bedrock.aws_region` / `AWS_REGION` | AWS 区域 | `us-west-2` |

### Agent 默认模型

| Agent 类型 | 默认模型 |
|------------|----------|
| TranslationAgent | `claude-opus-4-6` |
| QualityReviewAgent | `gpt-5.2` |
| ConsistencyReviewAgent | `gpt-5.2` |
| GlossaryExtractionAgent | `claude-opus-4-6` |
| VisualReviewAgent | `claude-sonnet-4-5-20250929` |

---

## 视觉评审规格

### 概述

视觉评审通过浏览器沙盒截图 + 多模态 LLM 分析翻译在真实 UI 中的视觉呈现质量。

### 评审维度

| 维度 | 评分范围 | 检测内容 |
|------|----------|---------|
| 布局质量 (Layout Quality) | 0-100 | 文本溢出、截断、布局错乱、元素错位 |
| 文本渲染 (Text Rendering) | 0-100 | 编码问题、字体渲染、乱码、缺失字形 |
| 翻译完整性 (Translation Completeness) | 0-100 | 未翻译残留、占位符可见、混合语言 |

### 通过标准

- 默认阈值: `overall_score >= 80`
- 各维度评分独立，总体评分由 LLM 综合评定

### 依赖

- 浏览器沙盒服务（二选一）：
  - **ai-sandbox**: Docker 容器沙盒，按需创建/销毁（`SandboxClient`）
  - **CUA Computer-Server**: 持久化浏览器服务，无需创建/销毁容器（`CuaSandboxClient`，duck-type 兼容）
- Claude Vision 多模态能力（`ANTHROPIC_API_KEY` 或 Bedrock）

### 错误处理

| 场景 | 策略 |
|------|------|
| 沙盒不可用 | 返回降级响应，`sandbox_error` 字段说明原因 |
| 单语言截图失败 | 该语言 0 分，其他语言继续 |
| LLM 解析失败 | 返回默认 70 分 |

> 详细流程参见 [VISUAL_REVIEW.md](VISUAL_REVIEW.md)

---

## 术语表规格

### 两级术语库系统 (Two-Tier Glossary System)

项目采用两级术语库系统，分别处理不同场景的术语需求：

| 级别 | 名称 | 用途 | 数据源 | 服务 |
|------|------|------|--------|------|
| Level 1 | Match Glossary (匹配术语库) | 直接翻译替换，确保一致性 | `examples/glossary.yaml` | `MatchGlossaryService` |
| Level 2 | Business AI Glossary (业务 AI 术语库) | 提示词丰富，提供术语定义 | `data/glossary.json` 或 MySQL | `GlossaryService` |
| 扩展 | Binance Glossary (交易所术语) | L1 匹配 + L2 提示词补充 | `data/binance_glossary/` | `BinanceGlossaryService` |

### Level 1: 匹配术语库 (Match Glossary)

用于翻译过程中的直接术语替换，确保关键术语翻译一致。

#### YAML 文件格式 (`examples/glossary.yaml`)

```yaml
Copy Trade:
  zh-CN: 跟单交易
  ja-JP: コピートレード
  ko-KR: 카피 트레이딩

Spot Trading:
  zh-CN: 现货交易
  ja-JP: 現物取引
```

#### 数据库表结构

##### match_glossary_terms（匹配术语主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 自增主键 |
| `term_id` | VARCHAR(128) | 术语 ID（MD5 哈希） |
| `term_en` | VARCHAR(512) | 英文术语 |
| `translation_<lang>` | VARCHAR(1024) | 各语言翻译列，如 `translation_zh_cn` |
| `source` | VARCHAR(64) | 来源 (imported/manual) |
| `status` | VARCHAR(32) | 状态 (active/inactive) |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

### Level 2: 业务 AI 术语库 (Business AI Glossary)

为 LLM 提供术语定义和上下文，丰富翻译提示词，提高翻译质量。

#### JSON 文件格式 (`data/glossary.json`)

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

#### 数据库表结构

##### business_glossary_terms（业务术语主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 自增主键 |
| `term_id` | VARCHAR(128) | 术语 ID（MD5 哈希） |
| `term_en` | VARCHAR(512) | 英文术语 |
| `definition` | TEXT | 术语定义 |
| `part_of_speech` | VARCHAR(32) | 词性 |
| `do_not_translate` | TINYINT(1) | 是否不翻译 |
| `translation_<lang>` | VARCHAR(1024) | 各语言翻译列，如 `translation_zh_cn` |
| `source` | VARCHAR(64) | 来源 (manual/ai_extracted/imported) |
| `status` | VARCHAR(32) | 状态 (active/inactive/pending/deleted) |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

##### glossary_candidates（候选术语表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 自增主键 |
| `term_id` | VARCHAR(128) | 术语 ID（MD5 哈希） |
| `term_en` | VARCHAR(512) | 英文术语 |
| `definition` | TEXT | 术语定义/语境说明 |
| `part_of_speech` | VARCHAR(32) | 词性 |
| `do_not_translate` | TINYINT(1) | 是否不翻译 |
| `translation_<lang>` | VARCHAR(1024) | 各语言翻译列，如 `translation_zh_cn` |
| `source` | VARCHAR(64) | 来源 (ai_extracted/manual/imported) |
| `status` | VARCHAR(32) | 状态 (pending/approved/rejected/migrated) |
| `migrated_to_match_glossary` | TINYINT(1) | 是否已迁移到 Match Glossary |
| `migrated_to_business_glossary` | TINYINT(1) | 是否已迁移到 Business Glossary |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

### 两级术语库在翻译中的应用

翻译过程中，两级术语库协同工作：

```
┌─────────────────────────────────────────────────────────┐
│  TranslationAgent 翻译流程                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Level 1 查询: get_direct_matches()                  │
│     └─ 返回直接翻译匹配 {term_en: translation}           │
│                                                         │
│  2. Level 2 查询: get_business_terms_for_prompt()       │
│     └─ 排除已匹配的 Level 1 术语                         │
│     └─ 返回用于提示词丰富的术语列表                       │
│                                                         │
│  3. 构建 LLM 提示词:                                     │
│     └─ 源文本                                           │
│     └─ Level 1 术语 (必须使用的翻译)                     │
│     └─ Level 2 术语 (定义和参考翻译)                     │
│                                                         │
│  4. 调用 LLM 执行翻译                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Level 1 与 Level 2 的区别**:

| 特性 | Level 1 (Match) | Level 2 (Business AI) |
|------|-----------------|------------------------|
| 匹配方式 | 词边界精确匹配 | 文本包含匹配 |
| 翻译使用 | 必须使用 | 参考使用 |
| 数据丰富度 | 仅翻译 | 定义 + 词性 + 翻译 |
| 数据来源 | YAML 导入 | JSON/数据库 + AI 提取 |

### AI 术语提取

基于人工翻译结果的智能术语提取：

**提取标准**:
- 专业术语：特定领域的专业词汇
- 产品名称：品牌、产品、功能名称
- 技术概念：技术术语、API 名称
- 行业用语：金融、区块链、交易等

**不提取的内容**:
- 日常用语
- 通用动词和形容词
- 已有明确翻译规范的常见词

**工作流程**:
1. 人工翻译完成后调用提取 API
2. AI 分析源文和翻译，识别专业术语
3. 提取结果存入候选术语表 (`glossary_candidates`)
4. 人工审核后决定是否入库到 Level 2 (Business AI Glossary)

### Binance 交易所术语库

从 Binance 网站爬取的多语言 UI 术语，补充人工维护术语库覆盖不到的交易所专业术语。

**数据特点**:

| 特性 | 说明 |
|------|------|
| 数据来源 | Binance 网站 DOM/i18n 爬取 |
| 术语数量 | ~16K（L1），质量过滤后 ~数千（L2） |
| 数据格式 | JSON (`data/binance_glossary/binance_glossary.json`) |
| 缺失字段 | 无 definition、part_of_speech（非人工维护） |

**L1/L2 拆分**:

| 部分 | 范围 | 用途 |
|------|------|------|
| L1 | 全部术语 | 直接翻译匹配（翻译记忆） |
| L2 | ≤4 词的短术语 | 提示词增强（质量过滤后） |

**L2 质量过滤规则**:
- 长度 > 2 字符
- 以字母开头
- 词数 ≤ 4
- 不含占位符（`{n}`, `${value}` 等）
- 不含交易对模式（`BTC/USDT` 等）
- 不含小数价格数据

**使用场景**:
- TranslationAgent: L1 补充直接匹配，L2 补充提示词术语
- QualityReviewAgent: L2 术语作为交易所术语参考

**优先级**: 人工维护数据（L1 Match + L2 Business）优先，Binance 术语仅补充缺失部分

### 缓存策略

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 人工维护术语缓存 TTL | 60 分钟 | 内存缓存有效期 |
| Binance 术语缓存 TTL | 120 分钟 | Binance 数据变更频率低 |
| 预热时机 | 应用启动 | 启动时加载所有术语 |
| 失效触发 | 写操作 | 创建/更新/删除术语时（仅人工维护术语） |
| 降级机制 | 自动 | 数据库不可用时切换到文件 |

### 术语表转换

支持从外部系统导出的 CSV 文件转换为项目使用的格式：

**CSV 格式要求**:
- 列名格式: `Term {Language Name} [{lang-code}] {lang-code}`
- Do Not Translate 列: `Do Not Translate {Language Name} [{lang-code}] {lang-code}`
- 编码: UTF-8 with BOM

**转换命令**:
```bash
python scripts/convert_glossary.py -i data/glossary.csv -o data
```

**输出文件**:
- `data/glossary.json`: JSON 格式术语表
- `data/glossary.yaml`: YAML 格式术语表

---

## Lark 飞书集成

### 概述

项目集成飞书电子表格作为翻译任务管理和术语库协作维护平台，通过 XXL-JOB 定时任务自动化处理。

### Lark 翻译表格

**表格结构**:

| 列名 | 说明 |
|------|------|
| `source_text` | 源文本 |
| `source_language` | 源语言（默认 en-US） |
| `target_language` | 目标语言 |
| `target_text` | 翻译结果（由系统写入） |
| `status` | 任务状态 |
| `mqm` | 质量评分 |
| `review_summary` | 评审摘要 |
| `properties` | 表格控制属性（ready/waiting） |

**任务状态流转**:

```
new → translated → reviewed → completed
 │                              ↓
 └──→ problem         (sync_lark_glossary)
```

### XXL-JOB 定时任务

| 任务名 | 功能 | 处理对象 |
|--------|------|---------|
| `sync_lark_translations` | 翻译新任务 | status="new" 的记录 |
| `sync_lark_glossary` | 提取术语 | status="reviewed" 的记录 |
| `sync_lark_glossary_tables` | 双向同步术语库表 | 三张术语库表 |
| `migrate_glossary_candidates` | 迁移已批准候选术语 | status="approved" 的候选术语 |

**翻译优化**: 相同 `source_text` 但不同 `target_language` 的行合并为多语言翻译任务，减少 LLM 调用。

**配额**: 单次任务最大处理 500 条记录（`MAX_TRANSLATIONS_PER_RUN`）。

**配置**: `AUTO_ADD_REVIEW_INPUT_COLUMN = False`（不自动在 Lark 表格中添加 review_input 列）。

### Lark API 客户端

| 客户端 | 用途 |
|--------|------|
| `LarkSheetsClient` | 电子表格读写（翻译任务 + 术语库同步） |
| `LarkBitableClient` | 多维表格 CRUD |

**认证方式**: Tenant Access Token（自动缓存和刷新）

---

## Tolgee 翻译平台集成

### 概述

集成 Tolgee 翻译平台作为术语库的外部管理源，支持将 Tolgee 上维护的术语数据同步到本地两级术语库。

### 同步方式

通过 `POST /api/v1/glossary/sync` 接口接收 Tolgee 推送的术语数据：

| 参数 | 说明 |
|------|------|
| `glossary_level` | `L1_MATCH`（匹配术语库）或 `L2_BUSINESS`（业务术语库） |
| `organization_id` | Tolgee 组织 ID |
| `glossary_id` | Tolgee 术语表 ID |
| `terms` | 术语列表（含基础语言文本、描述和各语言翻译） |

### 术语路由规则

| 级别 | 操作 | 说明 |
|------|------|------|
| `L1_MATCH` | `MatchGlossaryService.upsert_translations_batch()` | 直接写入匹配术语库 |
| `L2_BUSINESS` | 查找已存在 → 更新翻译；不存在 → 创建术语 | 写入业务 AI 术语库 |

同步完成后自动清除对应级别的缓存。

---

## 前端应用

### 概述

基于 Next.js 构建的 Web 管理界面，运行在 `:3000` 端口。

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
| `/glossary/candidates` | 候选术语审核 |
| `/glossary/import` | 术语批量导入 |
| `/translations` | 翻译任务管理 |
| `/translations/new` | 提交翻译任务 |
| `/visual-review` | 视觉评审 |

### 配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_API_BASE_URL` | 后端 API 地址 | `http://localhost:8080/api/v1` |

---

## API 规格

### 翻译端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 健康检查 |
| GET | `/api/v1/info` | 服务信息 |
| POST | `/api/v1/translations` | 提交异步翻译任务 |
| POST | `/api/v1/translations/sync` | 同步翻译（阻塞等待结果） |
| GET | `/api/v1/translations/{job_id}` | 查询任务状态 |
| DELETE | `/api/v1/translations/{job_id}` | 取消任务 |

### 术语表端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/glossary/terms` | 创建术语 |
| GET | `/api/v1/glossary/terms` | 列出术语（分页） |
| GET | `/api/v1/glossary/terms/search` | 搜索术语 |
| GET | `/api/v1/glossary/terms/{term_id}` | 获取术语 |
| PATCH | `/api/v1/glossary/terms/{term_id}` | 更新术语 |
| DELETE | `/api/v1/glossary/terms/{term_id}` | 删除术语 |
| PUT | `/api/v1/glossary/terms/{term_id}/translations/{lang_code}` | 更新翻译 |
| POST | `/api/v1/glossary/extract` | AI 术语提取 |
| GET | `/api/v1/glossary/candidates` | 列出候选术语 |
| POST | `/api/v1/glossary/candidates/{id}/review` | 审核候选术语 |
| POST | `/api/v1/glossary/import` | 导入术语 |
| GET | `/api/v1/glossary/export` | 导出术语 |
| POST | `/api/v1/glossary/cache/invalidate` | 清除缓存 |
| POST | `/api/v1/glossary/update-from-translation` | 从翻译结果更新术语库 |
| GET | `/api/v1/glossary/match/lookup` | 查询匹配术语库翻译 |
| POST | `/api/v1/glossary/sync` | 从 Tolgee 同步术语 |
| POST | `/api/v1/visual-reviews` | 执行视觉评审 |

### 请求参数

| 参数 | 限制 |
|------|------|
| `source_text_1` / `source_text` | 至少提供其一（双向兼容） |
| `source_text_2` | 可选，中文源文本（英中双源对照翻译） |
| `key` | 可选，文本标识键（提供翻译语境信息） |
| `target_langs` | 必填，最少 1 种语言 |
| `quality_threshold` | 0-100 (默认 95) |
| `max_retries` | 0-5 (默认 2) |

### 响应状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 202 | 任务已接受 |
| 204 | 操作成功，无内容 |
| 400 | 请求参数错误 |
| 404 | 资源未找到 |
| 422 | 验证失败 |
| 500 | 服务器错误 |

---

## 配置要求

### 环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `ENV` | 否 | 运行环境 (LOCAL/DEV/TEST/PRO) |
| `ANTHROPIC_API_KEY` | 是* | Claude API 密钥 |
| `OPENAI_API_KEY` | 否 | OpenAI API 密钥 |
| `GOOGLE_API_KEY` | 否 | Google API 密钥 |

*至少需要配置一个 LLM 提供商的 API 密钥

### Apollo 配置

| 配置项 | 说明 |
|--------|------|
| `llm_model_name` | 默认 LLM 模型 |
| `application_name` | 应用名称 |
| `timezone` | 时区设置 |

### MySQL 配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `mysql.host` | MySQL 主机地址 | localhost |
| `mysql.port` | MySQL 端口 | 3306 |
| `mysql.database` | 数据库名 | ai_translation |
| `mysql.user` | 用户名 | root |
| `mysql.password` | 密码 | - |
| `mysql.pool_size` | 连接池大小 | 10 |
| `mysql.pool_recycle` | 连接回收时间（秒） | 3600 |

### 部署配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_WORKERS` | Backend API 工作进程数 | `1` |
| `NEXT_PUBLIC_API_BASE_URL` | 前端 API 地址 | `http://localhost:8080/api/v1` |

### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Backend API (FastAPI) | 8080 | 主后端服务 |
| XXL-JOB Executor | 9991 | 定时任务执行器 |
| Frontend (Next.js) | 3000 | Web 管理界面 |

---

## 默认参数

### 翻译参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `source_lang` | `en-US` | 源语言 |
| `quality_threshold` | `95` | 质量阈值 |
| `max_retries` | `2` | 最大重试次数 |
| `job_ttl` | `3600` | 任务 TTL（秒） |

### 术语表参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `page_size` | `20` | 默认分页大小 |
| `cache_ttl` | `3600` | 缓存 TTL（秒） |
| `search_limit` | `20` | 搜索结果限制 |

---

### Lark 配置要求

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `lark.app_id` | 是* | 飞书应用 App ID |
| `lark.app_secret` | 是* | 飞书应用 App Secret |
| `lark.spreadsheet_token` | 是* | 翻译电子表格 Token |
| `xxl.admin_baseurl` | 是* | XXL-JOB Admin 地址 |
| `xxl.app_name` | 是* | 执行器名称 |
| `xxl.listen_port` | 是* | 执行器监听端口 |
| `xxl.access_token` | 是* | 访问令牌 |

*仅在启用 Lark 集成时需要

---

## 版本信息

| 版本 | 日期      | 说明 |
|------|---------|------|
| 0.1.0 | 2026-01 | 初始版本 |
| 0.2.0 | 2026-01 | 添加术语表 MySQL 持久化、API 和 AI 术语提取 |
| 0.3.0 | 2026-01 | 重构为两级术语库系统 (Match Glossary + Business AI Glossary) |
| 0.3.1 | 2026-02 | 更新 Agent 默认模型配置，添加术语库更新和查询 API |
| 0.3.2 | 2026-02 | 添加术语表 CSV 转换工具，扩展支持语言至 20 种 |
| 0.4.0 | 2026-02 | UI-First 翻译策略 (Prompt v2)，Lark 飞书集成，`key` 上下文参数 |
| 0.5.0 | 2026-02 | 多模态视觉评审（浏览器沙盒截图 + Claude Vision） |
| 0.6.0 | 2026-02 | Binance 交易所术语库；AWS Bedrock Bearer Token 认证；CUA 持久化沙盒客户端 |
| 0.7.0 | 2026-02 | 翻译提示词 v3（术语表合规优先、源语言冲突解决）；质量评审重构（分步评估、Hard Fail 机制、评分权重调整） |
| 0.8.0 | 2026-03 | 语言精简为 14 种；模型升级 claude-opus-4-6；双源翻译请求（source_text_1 + source_text_2）；TranslationItem 新增字段 |
| 0.9.0 | 2026-03 | Tolgee 翻译平台集成（术语同步）；同步翻译接口；Next.js 前端 Web UI；统一 Docker 多服务容器部署 |
