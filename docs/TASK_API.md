# Task API 接口文档

异步任务处理接口，支持翻译和摘要等 AI 任务类型。

## 基本信息

- **Base URL**: `/ai-api/v1`
- **协议**: HTTP
- **数据格式**: JSON
- **鉴权**: Bearer Token
- **框架**: FastAPI (Python)

---

## 鉴权

所有 Task API 接口需要在请求头中携带 Bearer Token：

```
Authorization: Bearer <token>
```

Token 通过 Apollo 配置中心的 `task_api.bearer_token` 配置项管理。若该配置项为空或未配置，则跳过鉴权（开发环境）。

| 场景 | 行为 |
|------|------|
| 未配置 token | 所有请求放行（不鉴权） |
| 已配置 token，请求未携带或不匹配 | 返回 `401 Unauthorized` |
| 已配置 token，请求携带且匹配 | 正常处理 |

### 请求示例

```bash
curl -X POST http://localhost:8080/ai-api/v1/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token" \
  -d '{"task_type": 1, "translation_params": {"target_languages": ["zh-CN"], "content": "Hello"}}'
```

---

## 接口列表

| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 创建任务 | POST | `/task` | 创建异步 AI 任务 |
| 获取任务 | GET | `/task/{task_id}` | 获取任务状态和结果 |
| 批量获取任务 | POST | `/task/batch` | 批量获取多个任务的状态和结果 |

---

## 1. 创建任务

创建一个新的异步 AI 任务。任务创建后会异步执行，可通过获取任务接口查询执行状态和结果。

### 请求

```
POST /ai-api/v1/task
Content-Type: application/json
```

### 请求参数

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| task_type | enum | 是 | 任务类型：`TASK_TYPE_TRANSLATION`(1), `TASK_TYPE_SUMMARIZATION`(2) |
| model | string | 否 | 模型名称，默认 `gemini-2.5-flash`（详见[支持的模型](#支持的模型)） |
| user_group | string | 否 | 用户组名称，用于标识调用方（详见[用户组配置](#用户组配置)） |
| translation_params | object | 条件必填 | 翻译任务参数（task_type=1 时必填） |
| summarization_params | object | 条件必填 | 摘要任务参数（task_type=2 时必填） |

#### TranslationParams (翻译任务参数)

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| source_language | string | 否 | 源语言代码，如 `en-US`，不填则自动检测 |
| target_languages | string[] | 是 | 目标语言代码数组，如 `["zh-CN", "ko-KR"]` |
| content | string | 是 | 要翻译的内容 |

#### SummarizationParams (摘要任务参数)

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| content | string | 是 | 要生成摘要的内容 |
| source_language | string | 否 | 源语言代码，用于语言检测 |
| target_language | string | 否 | 目标摘要语言代码 |
| max_length | int | 否 | 最大摘要长度（字符数），默认 200 |
| style | string | 否 | 摘要风格：`concise`(简洁), `detailed`(详细), `bullet_points`(要点)，默认 `concise` |

### 请求示例

**翻译任务 - 单语言翻译**
```json
{
  "task_type": 1,
  "model": "gemini-2.5-flash",
  "user_group": "marketing",
  "translation_params": {
    "source_language": "en-US",
    "target_languages": ["zh-CN"],
    "content": "Hello, world! This is a test message for translation."
  }
}
```

**翻译任务 - 多语言翻译**
```json
{
  "task_type": 1,
  "model": "gemini-2.5-flash",
  "user_group": "product",
  "translation_params": {
    "target_languages": ["zh-CN", "ko-KR", "ja-JP"],
    "content": "Example is a premier global digital asset trading platform."
  }
}
```

**摘要任务 - 简洁摘要**
```json
{
  "task_type": 2,
  "model": "gemini-2.5-flash",
  "user_group": "research",
  "summarization_params": {
    "content": "Bitcoin, the world's first cryptocurrency, was created in 2009 by an anonymous person or group known as Satoshi Nakamoto. It operates on a decentralized network using blockchain technology, which ensures transparency and security. Bitcoin has a limited supply of 21 million coins, making it a deflationary asset. Over the years, it has gained widespread adoption as both a store of value and a medium of exchange...",
    "target_language": "zh-CN",
    "max_length": 150,
    "style": "concise"
  }
}
```

**摘要任务 - 要点摘要**
```json
{
  "task_type": 2,
  "summarization_params": {
    "content": "长篇文章内容...",
    "style": "bullet_points",
    "max_length": 300
  }
}
```

### 响应

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": 0,
  "created_at": "2025-01-15T10:30:00Z"
}
```

### 响应字段

| 字段 | 类型 | 描述 |
|------|------|------|
| task_id | string | 任务唯一标识符 (UUID) |
| status | enum | 任务状态，0=INIT |
| created_at | string | 创建时间 (RFC3339) |

---

## 2. 获取任务

根据任务 ID 获取任务详情、状态和执行结果。

### 请求

```
GET /ai-api/v1/task/{task_id}
```

### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| task_id | string | 是 | 任务 ID |

### 响应示例

**处理中的翻译任务**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": 1,
  "status": 2,
  "model": "gemini-2.5-flash",
  "user_group": "marketing",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:01Z"
}
```

**已完成的翻译任务**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": 1,
  "status": 4,
  "model": "gemini-2.5-flash",
  "user_group": "marketing",
  "translation_output": {
    "translations": {
      "zh-CN": "你好，世界！这是一条翻译测试消息。",
      "ko-KR": "안녕하세요, 세계! 이것은 번역 테스트 메시지입니다."
    }
  },
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:03Z",
  "finished_at": "2025-01-15T10:30:03Z"
}
```

**已完成的摘要任务**
```json
{
  "task_id": "660e8400-e29b-41d4-a716-446655440001",
  "task_type": 2,
  "status": 4,
  "model": "gemini-2.5-flash",
  "user_group": "research",
  "summarization_output": {
    "summary": "比特币是2009年由中本聪创建的首个加密货币，基于去中心化区块链技术运行，总供应量限制为2100万枚，已成为重要的价值储存和交换媒介。",
    "source_language": "en-US"
  },
  "created_at": "2025-01-15T10:31:00Z",
  "updated_at": "2025-01-15T10:31:02Z",
  "finished_at": "2025-01-15T10:31:02Z"
}
```

**失败的任务**
```json
{
  "task_id": "770e8400-e29b-41d4-a716-446655440002",
  "task_type": 1,
  "status": 5,
  "model": "gemini-2.5-flash",
  "error_message": "AI processing failed: rate limit exceeded",
  "created_at": "2025-01-15T10:32:00Z",
  "updated_at": "2025-01-15T10:32:01Z",
  "finished_at": "2025-01-15T10:32:01Z"
}
```

### 响应字段

| 字段 | 类型 | 描述 |
|------|------|------|
| task_id | string | 任务 ID |
| task_type | enum | 任务类型 |
| status | enum | 任务状态 |
| model | string | 使用的模型名称 |
| user_group | string | 用户组（有值时返回） |
| error_message | string | 错误信息（仅失败时返回） |
| created_at | string | 创建时间 |
| updated_at | string | 最后更新时间 |
| finished_at | string | 完成时间（仅完成或失败时返回） |
| translation_output | object | 翻译结果（仅翻译任务完成时返回） |
| summarization_output | object | 摘要结果（仅摘要任务完成时返回） |

> 注意：未赋值的字段不会出现在响应 JSON 中（零值省略）。

#### TranslationOutput (翻译输出)

| 字段 | 类型 | 描述 |
|------|------|------|
| translations | map<string, string> | 语言代码到翻译文本的映射 |

#### SummarizationOutput (摘要输出)

| 字段 | 类型 | 描述 |
|------|------|------|
| summary | string | 生成的摘要 |
| source_language | string | 检测到的源语言代码 |

---

## 3. 批量获取任务

根据多个任务 ID 批量获取任务详情、状态和执行结果。适用于需要同时查询多个任务状态的场景。

### 请求

```
POST /ai-api/v1/task/batch
Content-Type: application/json
```

### 请求参数

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| task_ids | string[] | 是 | 任务 ID 数组，最多支持 100 个 |

### 请求示例

```json
{
  "task_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "660e8400-e29b-41d4-a716-446655440001",
    "770e8400-e29b-41d4-a716-446655440002"
  ]
}
```

### 响应示例

```json
{
  "tasks": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "task_type": 1,
      "status": 4,
      "model": "gemini-2.5-flash",
      "user_group": "marketing",
      "translation_output": {
        "translations": {
          "zh-CN": "你好，世界！"
        }
      },
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:03Z",
      "finished_at": "2025-01-15T10:30:03Z"
    },
    {
      "task_id": "660e8400-e29b-41d4-a716-446655440001",
      "task_type": 2,
      "status": 2,
      "model": "gemini-2.5-flash",
      "user_group": "research",
      "created_at": "2025-01-15T10:31:00Z",
      "updated_at": "2025-01-15T10:31:01Z"
    },
    {
      "task_id": "770e8400-e29b-41d4-a716-446655440002",
      "task_type": 1,
      "status": 5,
      "model": "gemini-2.5-flash",
      "error_message": "AI processing failed: rate limit exceeded",
      "created_at": "2025-01-15T10:32:00Z",
      "updated_at": "2025-01-15T10:32:01Z",
      "finished_at": "2025-01-15T10:32:01Z"
    }
  ]
}
```

### 响应字段

| 字段 | 类型 | 描述 |
|------|------|------|
| tasks | GetTaskResponse[] | 任务列表，结构与单个获取任务响应相同 |

### 注意事项

- 返回结果按请求的 `task_ids` 顺序排列
- 不存在的任务 ID 将被忽略，不会返回在结果中
- 单次请求最多支持 100 个任务 ID
- 使用单次数据库查询，性能优于多次单独查询

---

## 枚举定义

### TaskType (任务类型)

| 值 | 名称 | 描述 |
|------|------|------|
| 0 | TASK_TYPE_UNKNOWN | 未知类型 |
| 1 | TASK_TYPE_TRANSLATION | 翻译任务 |
| 2 | TASK_TYPE_SUMMARIZATION | 摘要任务 |

### TaskStatus (任务状态)

基于有限状态机（FSM）设计：

| 值 | 名称 | 描述 |
|------|------|------|
| 0 | TASK_STATUS_INIT | 初始状态 |
| 1 | TASK_STATUS_BEFORE_PROCESS | 前置处理中 |
| 2 | TASK_STATUS_PROCESSING | AI 处理中 |
| 3 | TASK_STATUS_AFTER_PROCESS | 后置处理中 |
| 4 | TASK_STATUS_FINISH | 已完成 |
| 5 | TASK_STATUS_ERROR | 失败 |

### 状态转换流程

```
INIT → BEFORE_PROCESS → PROCESSING → AFTER_PROCESS → FINISH
         ↓                 ↓              ↓
       ERROR            ERROR          ERROR
```

---

## 支持的语言代码

| 语言代码 | 语言名称 |
|----------|----------|
| ar-AE | 阿拉伯语 |
| de-DE | 德语 |
| en-US | 英语 |
| es-ES | 西班牙语 |
| fr-FR | 法语 |
| ja-JP | 日语 |
| ko-KR | 韩语 |
| nl-NL | 荷兰语 |
| pt-BR | 葡萄牙语 |
| ru-RU | 俄语 |
| tr-TR | 土耳其语 |
| uk-UA | 乌克兰语 |
| vi-VN | 越南语 |
| zh-CN | 简体中文 |
| zh-TW | 繁体中文 |

---

## 支持的模型

| 模型名称 | 提供商 | 描述 |
|----------|--------|------|
| gemini-2.0-flash | Google | 默认处理模型，快速响应 |
| gemini-3-flash-preview | Google | 新一代快速模型 |
| gemini-3-pro-preview | Google | 高质量输出，适合复杂任务 |
| claude-opus-4-6 | Anthropic | Claude 旗舰模型 |
| claude-sonnet-4-5-20250929 | Anthropic | Claude 平衡模型 |
| gpt-5.2 | OpenAI | GPT-5 系列 |
| gpt-5-mini | OpenAI | GPT-5 轻量版 |

用户可在创建任务时通过 `model` 字段指定使用的模型。若指定的模型不在已配置列表中，系统将回退到默认模型 `gemini-2.0-flash` 进行处理。

---

## 用户组配置

系统支持通过 `user_group` 字段标识调用方，便于统计和管理。

### 工作机制

1. 创建任务时指定 `user_group` 字段（如 `growth`、`marketing`）
2. `user_group` 值存储在任务记录中，可通过查询接口返回
3. 当前所有用户组统一使用默认 LLM 客户端进行处理

### 请求示例

```json
{
  "task_type": 1,
  "model": "gemini-2.5-flash",
  "user_group": "growth",
  "translation_params": {
    "target_languages": ["zh-CN"],
    "content": "Hello, World!"
  }
}
```

---

## 错误处理

### HTTP 状态码

| 状态码 | 描述 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误（无效的 task_type、缺少必填参数、不支持的语言代码等） |
| 401 | 未授权（Bearer Token 缺失或无效） |
| 404 | 任务不存在（仅获取单个任务时） |
| 500 | 服务内部错误 |

### 任务级错误

任务处理过程中的错误不会返回 HTTP 错误码，而是体现在任务的 `status`(5=ERROR) 和 `error_message` 字段中：

- **参数缺失**: `missing params`
- **AI 处理失败**: `AI processing failed: <详细原因>`
- **内容被屏蔽**: `Content blocked for task: <task_id>`

### 重试机制

- 任务处理失败时自动重试，最多 **2 次**，每次间隔 **20 秒**
- 不可重试的错误（参数缺失、内容被屏蔽）会立即标记为 ERROR，不会重试
- 所有重试失败后，任务最终标记为 ERROR 状态

---

## 内部实现

### 技术栈

- **Web 框架**: FastAPI (Python)
- **数据库**: MySQL (aiomysql 异步驱动)
- **LLM 客户端**: UnifiedLLMClient（支持 Google Gemini / Anthropic Claude / OpenAI）
- **后台处理**: asyncio.create_task

### 数据库表

表名: `ai_task`

| 列名 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED | 主键，自增 |
| task_id | VARCHAR(64) | 任务 ID (UUID)，唯一索引 |
| task_type | TINYINT | 任务类型 |
| status | TINYINT | 任务状态 |
| model | VARCHAR(64) | 模型名称 |
| user_group | VARCHAR(64) | 用户组 |
| params | JSON | 任务参数 |
| output | JSON | 任务输出 |
| error_message | VARCHAR(1024) | 错误信息 |
| finished_at | DATETIME | 完成时间 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |
| deleted_at | DATETIME | 软删除时间 |

建表 SQL: `migrations/003_create_ai_task_table.sql`

### 启动恢复

服务启动时会自动扫描数据库中状态为 INIT / BEFORE_PROCESS / PROCESSING / AFTER_PROCESS 的任务，分批（每批 100 条）加载并恢复处理，确保服务重启后未完成的任务不会丢失。

### 文件结构

```
app/
├── api/v1/endpoints/task.py      # API 端点定义
├── schemas/task.py               # Pydantic 请求/响应模型
├── services/task_service.py      # 核心服务（FSM + AI 处理 + 重试）
├── repositories/task_repository.py # 数据库访问层
├── core/constants.py             # 语言常量、模型配置
└── core/exceptions.py            # Task 相关异常
```
