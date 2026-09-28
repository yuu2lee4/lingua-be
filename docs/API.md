# AI 翻译服务 API 文档

## 概述

AI 翻译服务提供智能化多语言翻译能力，基于 Claude Agent SDK 构建，支持异步任务处理、质量评审和术语一致性检查。

**服务地址**: `http://localhost:8080`
**API 版本**: v1
**文档地址**: `/docs` (Swagger UI) | `/redoc` (ReDoc)

---

## 通用信息

### 支持的语言

| 语言代码 | 语言名称 |
|----------|----------|
| `en-US` | 英语（美国） |
| `zh-CN` | 简体中文 |
| `zh-TW` | 繁体中文 |
| `ja-JP` | 日语 |
| `ko-KR` | 韩语 |
| `de-DE` | 德语 |
| `fr-FR` | 法语 |
| `es-ES` | 西班牙语 |
| `pt-BR` | 葡萄牙语（巴西） |
| `ru-RU` | 俄语 |
| `ar` | 阿拉伯语 |
| `vi-VN` | 越南语 |
| `uk-UA` | 乌克兰语 |
| `id-ID` | 印尼语 |

### 任务状态

| 状态 | 说明 |
|------|------|
| `pending` | 等待处理 |
| `in_progress` | 处理中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `cancelled` | 已取消 |

### 翻译阶段

| 阶段 | 说明 |
|------|------|
| `pending` | 等待开始 |
| `translating` | 翻译中 |
| `quality_review` | 质量评审中 |
| `retrying` | 重试翻译中 |
| `consistency_review` | 一致性评审中 |
| `completed` | 已完成 |

---

## 基础端点

### 健康检查

检查服务是否正常运行。

```http
GET /healthz
```

**响应**

```json
{
  "msg": "OK"
}
```

### 服务信息

获取服务基本信息。

```http
GET /api/v1/info
```

**响应**

```json
{
  "name": "AI Translation Service",
  "version": "0.1.0"
}
```

---

## 翻译接口

### 提交翻译任务（异步）

提交异步翻译任务，返回任务 ID 用于后续查询。

```http
POST /api/v1/translations
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source_text_1` | string | ✅* | - | 源文本1（英文） |
| `source_lang_1` | string | ❌ | `en-US` | 源语言1代码 |
| `source_text_2` | string | ❌ | `null` | 源文本2（中文，可选，用于英中双源对照翻译） |
| `source_lang_2` | string | ❌ | `null` | 源语言2代码 |
| `source_text` | string | ✅* | - | 源文本（向后兼容，等价于 `source_text_1`） |
| `source_lang` | string | ❌ | `en-US` | 源语言代码（向后兼容，等价于 `source_lang_1`） |
| `key` | string | ❌ | `null` | 文本标识键，可提供翻译语境信息（如 UI 元素路径或业务域） |
| `target_langs` | string[] | ✅ | - | 目标语言代码列表 |
| `glossary_path` | string | ❌ | `null` | 术语表文件路径 |
| `translation_model` | string | ❌ | `null` | 翻译使用的模型 |
| `review_model` | string | ❌ | `null` | 评审使用的模型 |
| `quality_threshold` | int | ❌ | `95` | 质量评分阈值 (0-100) |
| `max_retries` | int | ❌ | `2` | 最大重试次数 (0-5) |

> *`source_text_1`、`source_text`、`source_text_2` 至少提供其一。`source_text` 与 `source_text_1` 双向兼容，提供任一即可。

**请求示例（新格式 - 双源）**

```json
{
  "source_text_1": "Welcome to our platform! We provide the best trading experience.",
  "source_text_2": "欢迎来到我们的平台！我们提供最好的交易体验。",
  "key": "home.welcome_banner",
  "target_langs": ["ja-JP", "ko-KR", "vi-VN"],
  "quality_threshold": 95,
  "max_retries": 2
}
```

**请求示例（旧格式 - 向后兼容）**

```json
{
  "source_text": "Welcome to our platform! We provide the best trading experience.",
  "key": "home.welcome_banner",
  "target_langs": ["zh-CN", "ja-JP", "ko-KR"],
  "quality_threshold": 75,
  "max_retries": 2
}
```

**响应** `202 Accepted`

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | 任务唯一标识 (UUID) |
| `status` | string | 任务状态 |
| `message` | string | 状态消息 |

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Translation job submitted successfully"
}
```

---

### 同步翻译

同步执行翻译，直接返回完整翻译结果（无需轮询）。

```http
POST /api/v1/translations/sync
Content-Type: application/json
```

**请求参数**

与 `POST /api/v1/translations` 完全一致。

**请求示例**

```json
{
  "source_text_1": "Welcome to our platform!",
  "target_langs": ["zh-CN", "ja-JP"],
  "quality_threshold": 95
}
```

**响应** `200 OK`

直接返回 `TranslationResponse` 对象（参见[数据模型](#translationresponse)），包含所有翻译结果。

```json
{
  "source_text_1": "Welcome to our platform!",
  "source_lang_1": "en-US",
  "source_text_2": null,
  "source_lang_2": null,
  "source_text": "Welcome to our platform!",
  "source_lang": "en-US",
  "translations": [
    {
      "target_lang": "zh-CN",
      "translated_text": "欢迎来到我们的平台！",
      "quality_score": 97,
      "quality_feedback": "翻译准确流畅",
      "retry_count": 0,
      "latency_ms": 1234.5,
      "glossary_terms_found": [],
      "glossary_terms_matched": []
    }
  ],
  "consistency_passed": true,
  "consistency_feedback": null,
  "consistency_pair_results": [],
  "total_latency_ms": 5678.9
}
```

> **与异步接口的区别**: 异步接口（`POST /api/v1/translations`）立即返回 `job_id`，需通过 `GET /api/v1/translations/{job_id}` 轮询获取结果；同步接口阻塞等待翻译完成后直接返回结果，适合对延迟不敏感的场景。

---

### 查询任务状态

根据任务 ID 查询翻译任务的状态和结果。

```http
GET /api/v1/translations/{job_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | 任务 ID |

**响应** `200 OK`

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": {
    "total_languages": 3,
    "completed_languages": 3,
    "current_phase": "completed",
    "current_language": null,
    "retry_count": 0,
    "progress_percent": 100.0
  },
  "response": {
    "source_text": "Welcome to our platform!",
    "source_lang": "en-US",
    "translations": [
      {
        "target_lang": "zh-CN",
        "translated_text": "欢迎来到我们的平台！",
        "quality_score": 85,
        "quality_feedback": "翻译准确流畅",
        "retry_count": 0,
        "latency_ms": 1234.5,
        "glossary_terms_found": ["platform"],
        "glossary_terms_matched": ["platform"]
      }
    ],
    "consistency_passed": true,
    "consistency_feedback": null,
    "consistency_pair_results": [
      {
        "lang1": "zh-CN",
        "lang2": "ja-JP",
        "passed": true,
        "feedback": "术语使用一致",
        "checked_terms_count": 3,
        "inconsistent_terms_count": 0
      }
    ],
    "total_latency_ms": 5678.9
  },
  "error": null,
  "created_at": "2024-01-22T10:00:00Z",
  "updated_at": "2024-01-22T10:01:00Z",
  "completed_at": "2024-01-22T10:01:00Z"
}
```

**任务进行中的响应示例**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress",
  "progress": {
    "total_languages": 3,
    "completed_languages": 1,
    "current_phase": "translating",
    "current_language": "ja-JP",
    "retry_count": 0,
    "progress_percent": 33.33
  },
  "response": null,
  "error": null,
  "created_at": "2024-01-22T10:00:00Z",
  "updated_at": "2024-01-22T10:00:30Z",
  "completed_at": null
}
```

**错误响应** `404 Not Found`

```json
{
  "detail": "Job not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 取消翻译任务

取消正在进行的翻译任务。

```http
DELETE /api/v1/translations/{job_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | 任务 ID |

**响应** `204 No Content`

无响应体

**错误响应** `404 Not Found`

```json
{
  "detail": "Job not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 数据模型

### TranslationItem

单个语言的翻译结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_lang` | string | 目标语言代码 |
| `translated_text` | string | 翻译文本 |
| `quality_score` | int \| null | 质量评分 (0-100) |
| `quality_feedback` | string \| null | 质量评审反馈 |
| `review_input` | string \| null | 评审模型输入（debug 用途） |
| `retry_count` | int | 重试次数 |
| `latency_ms` | float | 翻译耗时（毫秒） |
| `glossary_terms_found` | string[] | 源文本中找到的术语 |
| `glossary_terms_matched` | string[] | 翻译中匹配的术语 |
| `glossary_l1_direct_matches` | object | L1 术语库强制覆盖的术语 `{term_en: translation}` |
| `placeholder_issues` | string[] | 占位符校验问题 |

### TranslationResponse

完整的翻译响应。

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_text_1` | string | 源文本1（英文） |
| `source_lang_1` | string | 源语言1代码 |
| `source_text_2` | string \| null | 源文本2（中文，可选） |
| `source_lang_2` | string \| null | 源语言2代码（可选） |
| `source_text` | string | 源文本（向后兼容） |
| `source_lang` | string | 源语言代码（向后兼容） |
| `translations` | TranslationItem[] | 翻译结果列表 |
| `consistency_passed` | bool | 一致性检查是否通过（所有语言对都通过则为 True） |
| `consistency_feedback` | string \| null | 一致性检查反馈 |
| `consistency_pair_results` | ConsistencyPairResult[] | 语言对一致性评审结果列表 |
| `total_latency_ms` | float | 总耗时（毫秒） |

### ConsistencyPairResult

语言对一致性评审结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `lang1` | string | 语言1代码 |
| `lang2` | string | 语言2代码 |
| `passed` | bool | 是否通过 |
| `feedback` | string | 评审反馈 |
| `checked_terms_count` | int | 检查的术语数量 |
| `inconsistent_terms_count` | int | 不一致的术语数量 |

### QualityScore

质量评分详情。

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | int | 总体评分 (0-100) |
| `accuracy` | int | 准确性评分 |
| `fluency` | int | 流畅性评分 |
| `terminology` | int | 术语一致性评分 |
| `style` | int | 风格一致性评分 |

### JobProgress

任务进度信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_languages` | int | 目标语言总数 |
| `completed_languages` | int | 已完成的语言数 |
| `current_phase` | string | 当前阶段 |
| `current_language` | string \| null | 当前处理的语言 |
| `retry_count` | int | 当前重试次数 |
| `total_consistency_pairs` | int | 一致性评审语言对总数 |
| `completed_consistency_pairs` | int | 已完成的一致性评审语言对数 |
| `current_consistency_pair` | string \| null | 当前评审的语言对 |
| `progress_percent` | float | 进度百分比 (只读) |

---

## 错误处理

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| `200` | 请求成功 |
| `202` | 任务已接受（异步处理） |
| `204` | 操作成功，无返回内容 |
| `400` | 请求参数错误 |
| `404` | 资源未找到 |
| `422` | 请求体验证失败 |
| `500` | 服务器内部错误 |

### 业务异常

| 异常类型 | 说明 |
|----------|------|
| `JobNotFoundError` | 任务未找到 |
| `JobAlreadyExistsError` | 任务已存在 |
| `JobCancelledError` | 任务已取消 |
| `TranslationFailedError` | 翻译失败 |
| `QualityCheckFailedError` | 质量检查失败 |
| `GlossaryLoadError` | 术语表加载错误 |
| `GlossaryTermNotFoundError` | 术语未找到 |
| `GlossaryTermExistsError` | 术语已存在 |
| `DatabaseConnectionError` | 数据库连接错误 |
| `DatabaseQueryError` | 数据库查询错误 |
| `MaxRetriesExceededError` | 超过最大重试次数 |
| `SandboxError` | 沙盒操作错误 |
| `VisualReviewError` | 视觉评审错误 |

---

## 视觉评审接口

> 详细流程文档参见 [VISUAL_REVIEW.md](VISUAL_REVIEW.md)

### 执行视觉评审

通过浏览器沙盒截图对比各语言 UI 呈现，检测布局溢出、文本截断等问题。

```http
POST /api/v1/visual-reviews
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `target_langs` | string[] | ✅ | - | 目标语言代码列表 |
| `base_url` | string | ❌ | `https://www.example.com` | 网站基础 URL |
| `url_path` | string | ❌ | `/ai` | 语言代码后的路径 |
| `reference_lang` | string | ❌ | `en-US` | 参考语言代码 |
| `scroll_positions` | int | ❌ | `1` | 截图滚动次数 (0-10) |
| `review_model` | string | ❌ | `null` | 评审使用的模型 |
| `sandbox_resolution` | string | ❌ | `1920x1080` | 沙盒分辨率 |

**请求示例**

```json
{
    "target_langs": ["zh-CN", "ja-JP"],
    "base_url": "https://www.example.com",
    "url_path": "/ai",
    "reference_lang": "en-US",
    "scroll_positions": 1
}
```

**响应** `200 OK`

```json
{
    "reviews": [
        {
            "lang_code": "zh-CN",
            "lang_name": "简体中文",
            "overall_score": 92,
            "layout_score": 95,
            "text_rendering_score": 90,
            "translation_completeness_score": 90,
            "passed": true,
            "issues": [],
            "screenshots_count": 2,
            "feedback": "Overall good visual quality"
        }
    ],
    "reference_lang": "en-US",
    "total_languages": 1,
    "passed_count": 1,
    "failed_count": 0,
    "total_latency_ms": 285430.5,
    "sandbox_error": null
}
```

---

## 使用示例

### Python 示例

```python
import httpx
import asyncio

async def translate_text():
    async with httpx.AsyncClient(base_url="http://localhost:8080") as client:
        # 1. 提交翻译任务
        response = await client.post("/api/v1/translations", json={
            "source_text": "Hello, welcome to our platform!",
            "target_langs": ["zh-CN", "ja-JP"],
            "quality_threshold": 75
        })
        job = response.json()
        job_id = job["job_id"]
        print(f"任务已提交: {job_id}")

        # 2. 轮询查询结果
        while True:
            response = await client.get(f"/api/v1/translations/{job_id}")
            result = response.json()

            if result["status"] == "completed":
                print("翻译完成!")
                for t in result["response"]["translations"]:
                    print(f"  {t['target_lang']}: {t['translated_text']}")
                break
            elif result["status"] == "failed":
                print(f"翻译失败: {result['error']}")
                break
            else:
                progress = result["progress"]
                print(f"进度: {progress['progress_percent']:.1f}% - {progress['current_phase']}")
                await asyncio.sleep(2)

asyncio.run(translate_text())
```

### cURL 示例

```bash
# 提交翻译任务
curl -X POST http://localhost:8080/api/v1/translations \
  -H "Content-Type: application/json" \
  -d '{
    "source_text": "Welcome to our trading platform!",
    "target_langs": ["zh-CN", "ja-JP"],
    "glossary_path": "data/glossary.csv"
  }'

# 查询任务状态
curl http://localhost:8080/api/v1/translations/{job_id}

# 取消任务
curl -X DELETE http://localhost:8080/api/v1/translations/{job_id}
```

---

## 术语表系统

### 两级术语库架构

项目采用两级术语库系统，通过 API 主要管理 Level 2 (Business AI Glossary)：

| 级别 | 名称 | 用途 | 数据源 |
|------|------|------|--------|
| Level 1 | Match Glossary (匹配术语库) | 直接翻译替换 | `examples/glossary.yaml` |
| Level 2 | Business AI Glossary (业务 AI 术语库) | 提示词丰富 | MySQL / `data/glossary.json` |
| 扩展 | Binance Glossary (交易所术语) | L1 直接匹配 + L2 提示词补充 | `data/binance_glossary/binance_glossary.json` |

> **说明**: 以下术语表接口主要管理 Level 2 (Business AI Glossary)。Level 1 (Match Glossary) 通过 YAML 文件导入初始化，在应用启动时自动加载。Binance Glossary 从本地 JSON 加载，补充交易所 UI 术语但不覆盖人工维护数据。

---

## 术语表接口 (Business AI Glossary)

### 创建术语

```http
POST /api/v1/glossary/terms
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `term_en` | string | ✅ | 英文术语 |
| `definition` | string | ❌ | 术语定义 |
| `part_of_speech` | string | ❌ | 词性 |
| `do_not_translate` | bool | ❌ | 是否不翻译 |
| `translations` | object | ❌ | 各语言翻译 {"zh-CN": "翻译"} |
| `source` | string | ❌ | 来源 (manual/ai_extracted/imported) |

**请求示例**

```json
{
  "term_en": "Copy Trade",
  "definition": "A trading feature that allows users to automatically copy trades",
  "translations": {
    "zh-CN": "跟单交易",
    "ja-JP": "コピートレード"
  }
}
```

**响应** `201 Created`

```json
{
  "term_id": "e8f2b9d1a3c5f7e9",
  "term_en": "Copy Trade",
  "definition": "A trading feature...",
  "part_of_speech": "",
  "do_not_translate": false,
  "translations": {"zh-CN": "跟单交易", "ja-JP": "コピートレード"},
  "source": "manual",
  "status": "active",
  "created_at": "2024-01-22T10:00:00Z",
  "updated_at": "2024-01-22T10:00:00Z"
}
```

---

### 列出术语

```http
GET /api/v1/glossary/terms?page=1&page_size=20&status=active&search=trade
```

**查询参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页数量 (1-100) |
| `status` | string | - | 状态筛选 (active/inactive/pending) |
| `search` | string | - | 搜索关键词 |

**响应** `200 OK`

```json
{
  "total": 150,
  "items": [...],
  "page": 1,
  "page_size": 20
}
```

---

### 搜索术语

```http
GET /api/v1/glossary/terms/search?keyword=trade&limit=20
```

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | ✅ | 搜索关键词 |
| `limit` | int | ❌ | 返回数量限制 (默认 20) |

---

### 获取术语

```http
GET /api/v1/glossary/terms/{term_id}
```

---

### 更新术语

```http
PATCH /api/v1/glossary/terms/{term_id}
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| `definition` | string | 术语定义 |
| `part_of_speech` | string | 词性 |
| `do_not_translate` | bool | 是否不翻译 |
| `status` | string | 状态 (active/inactive/pending) |

---

### 删除术语

```http
DELETE /api/v1/glossary/terms/{term_id}
```

**响应** `204 No Content`

---

### 更新翻译

```http
PUT /api/v1/glossary/terms/{term_id}/translations/{lang_code}
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `translation` | string | ✅ | 翻译内容 |

**请求示例**

```json
{
  "translation": "跟单交易"
}
```

---

### AI 术语提取

基于人工翻译结果，使用 AI 提取潜在的专业术语。

```http
POST /api/v1/glossary/extract
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_text` | string | ✅ | 原文 |
| `human_translation` | string | ✅ | 人工翻译 |
| `target_lang` | string | ✅ | 目标语言代码 |
| `translation_job_id` | string | ❌ | 关联的翻译任务 ID |

**请求示例**

```json
{
  "source_text": "Enable spot trading and margin trading features",
  "human_translation": "启用现货交易和杠杆交易功能",
  "target_lang": "zh-CN"
}
```

**响应** `200 OK`

```json
{
  "extracted_terms": [
    {
      "term_en": "spot trading",
      "suggested_translation": "现货交易",
      "confidence": 92.5,
      "context": "spot trading and margin trading"
    },
    {
      "term_en": "margin trading",
      "suggested_translation": "杠杆交易",
      "confidence": 90.0,
      "context": "margin trading features"
    }
  ],
  "candidates_created": 2
}
```

---

### 列出候选术语

```http
GET /api/v1/glossary/candidates?page=1&page_size=20&status=pending
```

**查询参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页数量 |
| `status` | string | - | 状态筛选 (pending/approved/rejected/migrated) |

---

### 审核候选术语

```http
POST /api/v1/glossary/candidates/{candidate_id}/review
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | ✅ | 审核操作 (approved/rejected) |
| `translations` | object | ❌ | 确认的翻译（批准时可覆盖候选翻译） |
| `migrate_to_match` | bool | ❌ | 是否迁移到 Match Glossary（默认 false） |
| `migrate_to_business` | bool | ❌ | 是否迁移到 Business Glossary（默认 true） |

**请求示例**

```json
{
  "action": "approved",
  "translations": {"zh-CN": "跟单交易"},
  "migrate_to_business": true
}
```

---

### 导入术语

```http
POST /api/v1/glossary/import
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `terms` | array | ✅ | 术语列表 |
| `overwrite` | bool | ❌ | 是否覆盖已存在的术语 |

**响应** `200 OK`

```json
{
  "imported": 45,
  "skipped": 5,
  "errors": ["term_xxx: 格式错误"]
}
```

---

### 导出术语

```http
GET /api/v1/glossary/export
```

**响应** `200 OK`

```json
{
  "terms": [...],
  "exported_at": "2024-01-22T10:00:00Z",
  "total": 150
}
```

---

### 清除缓存

```http
POST /api/v1/glossary/cache/invalidate
```

**响应** `204 No Content`

---

### 从翻译结果更新术语库

基于翻译结果同时更新 Match Glossary 和提取候选术语。

```http
POST /api/v1/glossary/update-from-translation
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_text` | string | ✅ | 原文 |
| `translations` | object | ✅ | 各语言翻译 {"zh-CN": "翻译"} |
| `translation_job_id` | string | ❌ | 关联的翻译任务 ID |
| `extract_business_terms` | bool | ❌ | 是否提取业务术语（默认 true） |

**请求示例**

```json
{
  "source_text": "Copy Trade allows you to follow experienced traders",
  "translations": {
    "zh-CN": "跟单交易允许您跟随经验丰富的交易者",
    "ja-JP": "コピートレードで経験豊富なトレーダーをフォローできます"
  },
  "extract_business_terms": true
}
```

**响应** `200 OK`

```json
{
  "match_glossary_updated": 1,
  "candidates_created": 2,
  "errors": []
}
```

**功能说明**:
1. 将源文本和翻译写入 Match Glossary（可覆盖）
2. 可选通过 AI 提取业务术语到候选术语表

---

### Tolgee 术语同步

从 Tolgee 翻译平台同步术语数据到本地术语库。

```http
POST /api/v1/glossary/sync
Content-Type: application/json
```

**请求参数**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `glossary_level` | string | ✅ | 术语库级别: `L1_MATCH` 或 `L2_BUSINESS` |
| `organization_id` | int | ✅ | Tolgee 组织 ID |
| `glossary_id` | int | ✅ | Tolgee 术语表 ID |
| `glossary_name` | string | ❌ | 术语表名称 |
| `base_language_tag` | string | ❌ | 基础语言标签（默认 `en`） |
| `terms` | GlossarySyncTerm[] | ❌ | 术语列表 |

**GlossarySyncTerm**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `term_text` | string | ✅ | 基础语言术语文本 |
| `description` | string | ❌ | 术语描述 |
| `translations` | object | ❌ | 各语言翻译 `{"zh-CN": "翻译"}` |
| `is_non_translatable` | bool | ❌ | 是否不翻译 |
| `is_case_sensitive` | bool | ❌ | 是否大小写敏感 |
| `is_forbidden_term` | bool | ❌ | 是否为禁用术语 |

**请求示例**

```json
{
  "glossary_level": "L1_MATCH",
  "organization_id": 1,
  "glossary_id": 42,
  "glossary_name": "Trading Terms",
  "base_language_tag": "en",
  "terms": [
    {
      "term_text": "Spot Trading",
      "description": "Trading with immediate settlement",
      "translations": {
        "zh-CN": "现货交易",
        "ja-JP": "現物取引"
      }
    }
  ]
}
```

**响应** `200 OK`

```json
{
  "synced": 1,
  "errors": []
}
```

**功能说明**:
- `L1_MATCH`: 术语写入匹配术语库（Level 1），用于直接翻译替换
- `L2_BUSINESS`: 术语写入业务 AI 术语库（Level 2），已存在则更新翻译，不存在则创建
- 同步完成后自动清除相关缓存

---

### 查询匹配术语库翻译

在 Match Glossary (Level 1) 中直接查找术语翻译。

```http
GET /api/v1/glossary/match/lookup?term=Copy Trade&lang=zh-CN
```

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `term` | string | ✅ | 英文术语 |
| `lang` | string | ✅ | 目标语言代码 |

**响应** `200 OK`

```json
{
  "term_en": "Copy Trade",
  "target_lang": "zh-CN",
  "translation": "跟单交易",
  "found": true
}
```

**未找到时的响应**

```json
{
  "term_en": "Unknown Term",
  "target_lang": "zh-CN",
  "translation": null,
  "found": false
}
```

---

## 术语表文件格式

### Level 1: 匹配术语库 (Match Glossary)

YAML 格式 (`examples/glossary.yaml`)，用于直接翻译替换：

```yaml
Copy Trade:
  zh-CN: 跟单交易
  ja-JP: コピートレード
  ko-KR: 카피 트레이딩

Spot Trading:
  zh-CN: 现货交易
  ja-JP: 現物取引
```

> 应用启动时自动从 YAML 文件导入到数据库。

### Level 2: 业务 AI 术语库 (Business AI Glossary)

JSON 格式 (`data/glossary.json`)，数据库不可用时的降级方案：

```json
{
  "terms": [
    {
      "term_id": "1",
      "term_en": "platform",
      "definition": "交易平台",
      "part_of_speech": "noun",
      "do_not_translate": false,
      "translations": {
        "zh-CN": "平台",
        "ja-JP": "プラットフォーム"
      }
    }
  ]
}
```

---

## 配置说明

### 环境变量

| 变量名 | 说明 |
|--------|------|
| `ENV` | 运行环境 (LOCAL/DEV/TEST/PRO) |
| `ANTHROPIC_API_KEY` | Claude API 密钥（原生 API 模式） |
| `GOOGLE_API_KEY` | Google Gemini API 密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥 |

### AWS Bedrock 配置

当使用 AWS Bedrock 端点访问 Claude 模型时，配置以下变量（与 `ANTHROPIC_API_KEY` 二选一）：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `USE_BEDROCK` | 是否启用 Bedrock 端点 | `false` |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock Bearer Token | - |
| `AWS_REGION` | AWS 区域 | `us-west-2` |

> **说明**: Bedrock 模式使用 Bearer Token 认证（跳过 SigV4 签名），原生模型名会自动映射到 Bedrock 模型 ID（如 `claude-opus-4-6` → `us.anthropic.claude-opus-4-6-v1`）。

### Apollo MySQL 配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `mysql.host` | MySQL 主机地址 | localhost |
| `mysql.port` | MySQL 端口 | 3306 |
| `mysql.database` | 数据库名 | ai_translation |
| `mysql.user` | 用户名 | root |
| `mysql.password` | 密码 | - |
| `mysql.pool_size` | 连接池大小 | 10 |
| `mysql.pool_recycle` | 连接回收时间（秒） | 3600 |

### 默认模型配置

| Agent 类型 | 默认模型 |
|------------|----------|
| 翻译 | `claude-opus-4-6` |
| 质量评审 | `gpt-5.2` |
| 一致性评审 | `gpt-5.2` |
| 术语提取 | `claude-opus-4-6` |

### Bedrock 配置 (Apollo)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `bedrock.use_bedrock` | 是否启用 Bedrock | `false` |
| `bedrock.aws_bearer_token` | Bearer Token | - |
| `bedrock.aws_region` | AWS 区域 | `us-west-2` |

### Lark 集成配置

| 变量名 | 说明 |
|--------|------|
| `lark.app_id` | 飞书应用 App ID |
| `lark.app_secret` | 飞书应用 App Secret |
| `lark.spreadsheet_token` | 翻译电子表格 Token |

### XXL-JOB 配置

| 变量名 | 说明 |
|--------|------|
| `xxl.admin_baseurl` | XXL-JOB Admin 地址 |
| `xxl.app_name` | 执行器名称 |
| `xxl.listen_port` | 执行器监听端口 |
| `xxl.access_token` | 访问令牌 |

---

## 版本历史

| 版本 | 日期         | 说明 |
|------|------------|------|
| 0.1.0 | 2026-01-20 | 初始版本 |
| 0.1.1 | 2026-01-26 | 添加语言对一致性评审功能 |
| 0.2.0 | 2026-01-28 | 添加术语表 MySQL 持久化和 API |
| 0.3.0 | 2026-01-30 | 重构为两级术语库系统 (Match Glossary + Business AI Glossary) |
| 0.3.1 | 2026-02-04 | 添加从翻译结果更新术语库 API，添加匹配术语库查询 API，更新默认模型配置 |
| 0.3.2 | 2026-02-04 | 扩展支持语言至 20 种，添加术语表 CSV 转换工具 |
| 0.4.0 | 2026-02-09 | UI-First 翻译提示词 v2（本地交易所标准、敬语规则、标点规则）；Lark 飞书集成（翻译任务、术语同步）；添加 `key` 上下文参数 |
| 0.5.0 | 2026-02-10 | 多模态视觉评审（浏览器沙盒截图 + Claude Vision）；SandboxClient；VisualReviewAgent |
| 0.6.0 | 2026-02-11 | Binance 交易所术语库（L1 直接匹配 + L2 提示词增强）；AWS Bedrock Bearer Token 认证；CUA 持久化沙盒客户端 |
| 0.7.0 | 2026-02-14 | 翻译提示词 v3（术语表合规优先、源语言冲突解决）；质量评审重构（分步评估、Hard Fail 机制、评分权重调整） |
| 0.8.0 | 2026-03-01 | 语言精简为 14 种（移除 ar-AE, nl-NL, tr-TR, th-TH, hi-IN, bn-BD）；模型升级 claude-opus-4-6；双源翻译字段（source_text_1 + source_text_2）；TranslationItem 新增 L1 直接匹配和占位符校验字段 |
| 0.9.0 | 2026-03-08 | Tolgee 翻译平台集成（术语同步 API）；同步翻译接口（`POST /translations/sync`）；Next.js 前端 Web UI；统一 Docker 多服务容器部署 |
