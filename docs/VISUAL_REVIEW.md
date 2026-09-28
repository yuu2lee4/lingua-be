# 多模态视觉评审流程文档

## 概述

视觉评审（Visual Review）是翻译质量保证体系的补充环节，通过**浏览器沙盒截图 + 多模态 LLM 分析**的方式，检测翻译在真实 UI 中的视觉呈现问题。

与文本评审（QualityReviewAgent、ConsistencyReviewAgent）关注翻译内容本身不同，视觉评审关注翻译部署到产品 UI 后的**渲染效果**：布局溢出、文本截断、未翻译残留、编码乱码等。

### 核心特性

- **多模态分析** - 通过 Claude Vision 同时分析参考语言和目标语言截图
- **浏览器沙盒** - 在隔离的 Docker 沙盒中运行真实浏览器截图
- **三维评分** - 布局质量、文本渲染、翻译完整性独立评分
- **优雅降级** - 沙盒不可用时返回降级响应，不阻塞其他流程

---

## 系统架构

### 两层沙盒架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    ai-translation 服务                            │
│                                                                   │
│  ┌──────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │   API Endpoint   │→ │ VisualReview    │→ │VisualReview   │  │
│  │ POST /api/v1/    │  │   Service       │  │   Agent       │  │
│  │  visual-reviews  │  │                 │  │ (BaseAgent)   │  │
│  └──────────────────┘  └─────────────────┘  └───────┬───────┘  │
│                                                       │          │
│  ┌────────────────────────────────────────────────────┘          │
│  │                                                               │
│  ▼                                                               │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    SandboxClient                            │  │
│  │  ┌─────────────────────┐  ┌─────────────────────────────┐  │  │
│  │  │  管理 API 客户端     │  │     沙盒内部 API 客户端       │  │  │
│  │  │  (_mgmt_client)     │  │     (_sandbox_client)        │  │  │
│  │  │  :8000              │  │     :{api_port}              │  │  │
│  │  └──────────┬──────────┘  └──────────────┬──────────────┘  │  │
│  └─────────────┼────────────────────────────┼─────────────────┘  │
└────────────────┼────────────────────────────┼────────────────────┘
                 │                            │
                 ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ai-sandbox 服务                              │
│                                                                   │
│  ┌────────────────────┐     ┌──────────────────────────────────┐│
│  │   管理 API (:8000)  │     │      Docker 沙盒容器              ││
│  │                    │     │  ┌────────────────────────────┐  ││
│  │  POST /api/v1/     │────▶│  │  内部 API (:{api_port})   │  ││
│  │    sandbox         │     │  │  POST /action              │  ││
│  │  DELETE /api/v1/   │     │  │  GET /screenshot           │  ││
│  │    sandbox/{id}    │     │  │  GET /health               │  ││
│  └────────────────────┘     │  └────────────────────────────┘  ││
│                              │  ┌────────────────────────────┐  ││
│                              │  │  Chromium + XFCE Desktop   │  ││
│                              │  │  VNC :5910 / noVNC :6910   │  ││
│                              │  └────────────────────────────┘  ││
│                              └──────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 两层 API 架构 | 管理 API + 沙盒内部 API | Docker 网络隔离，管理 API 无法可靠代理到容器内部 |
| 非默认端口 | VNC:5910, noVNC:6910, API:8010 | 避免与管理 API (:8000) 和其他服务端口冲突 |
| 串行语言处理 | 逐个语言截图和评审 | 共享单个浏览器沙盒实例，无法并行导航 |
| 180s 超时 | httpx timeout=180s | 截图响应约 300-400KB base64，传输时间较长 |

---

## 评审流程

### 完整工作流

```
┌────────────────────────────────────────────────────────────────┐
│                  VisualReviewAgent 工作流程                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Phase 0: 沙盒准备 (setup)                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  1. 清理同名沙盒残留（2 轮 DELETE）                         │  │
│  │  2. POST /api/v1/sandbox 创建沙盒容器                      │  │
│  │  3. 等待内部 API 健康检查通过（GET /health, 最多 20 次）     │  │
│  │  4. 初始化沙盒内部 API 客户端                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 1: 截取参考语言截图                                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  URL: {base_url}/{reference_lang}{url_path}               │  │
│  │  例: https://www.example.com/en-US/ai                     │  │
│  │                                                            │  │
│  │  导航步骤: Ctrl+L → Ctrl+A → 输入 URL → Enter → 等待 8s   │  │
│  │  首屏截图 + scroll_positions 次滚动截图                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 2: 逐语言评审（串行）                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  for lang_code in target_langs:                            │  │
│  │    1. 导航到目标语言 URL 并截图                              │  │
│  │       URL: {base_url}/{lang_code}{url_path}                │  │
│  │    2. 构建多模态消息:                                       │  │
│  │       ┌──────────────────────────────────────────┐         │  │
│  │       │ [参考语言截图(s)] + [目标语言截图(s)]       │         │  │
│  │       │ + 评审提示词 (JSON 输出格式)               │         │  │
│  │       └──────────────────────────────────────────┘         │  │
│  │    3. 调用多模态 LLM (Claude Vision)                       │  │
│  │    4. 解析 JSON 响应 → VisualLanguageReview                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 3: 汇总结果                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  统计通过/失败数量，计算总耗时                               │  │
│  │  返回 VisualReviewResponse                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Phase 4: 沙盒清理 (cleanup)                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  DELETE /api/v1/sandbox/{id} 销毁沙盒容器                   │  │
│  │  关闭 HTTP 客户端                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 截图导航流程

沙盒内部浏览器通过模拟键盘操作完成 URL 导航：

```
POST /action {"action": "key", "key": "ctrl+l"}    → 聚焦地址栏
POST /action {"action": "key", "key": "ctrl+a"}    → 全选当前 URL
POST /action {"action": "type", "text": "<url>"}   → 输入新 URL
POST /action {"action": "key", "key": "Return"}    → 回车导航
asyncio.sleep(8)                                    → 等待页面加载
GET /screenshot                                     → 截取屏幕
```

### URL 模式

Example 网站通过 URL 路径切换语言：

```
{base_url}/{lang_code}{url_path}

示例：
https://www.example.com/en-US/ai     ← 参考语言
https://www.example.com/zh-CN/ai     ← 简体中文
https://www.example.com/ja-JP/ai     ← 日语
https://www.example.com/ko-KR/ai     ← 韩语
```

---

## 评审维度

### LLM 评估的三个维度

| 维度 | 字段 | 评分范围 | 检测内容 |
|------|------|----------|---------|
| 布局质量 | `layout_score` | 0-100 | 文本溢出容器、文本截断（省略号/截断）、布局错乱/元素错位、按钮/标签宽度异常 |
| 文本渲染 | `text_rendering_score` | 0-100 | 编码问题（乱码/mojibake）、字体渲染问题、字符显示异常、缺失字形/占位框 |
| 翻译完整性 | `translation_completeness_score` | 0-100 | 英文残留未翻译、占位符字符串可见、不应混合的多语言内容、空白缺失翻译 |

### 问题分类

**问题类型** (`issue_type`):

| 类型 | 说明 |
|------|------|
| `truncation` | 文本被截断 |
| `overflow` | 文本溢出容器 |
| `encoding` | 编码/乱码问题 |
| `layout` | 布局错乱 |
| `untranslated` | 未翻译的内容 |
| `mistranslation` | 明显的翻译错误 |
| `style` | 样式/风格问题 |

**严重程度** (`severity`):

| 级别 | 说明 |
|------|------|
| `critical` | 影响可用性，用户无法正常使用 |
| `major` | 明显问题，影响用户体验 |
| `minor` | 外观/装饰性问题 |

### 通过标准

- **默认阈值**: `overall_score >= 80`
- 阈值可通过 `VisualReviewAgent` 的 `visual_quality_threshold` 参数调整
- 各维度评分独立计算，`overall_score` 由 LLM 综合评定

---

## 组件说明

### SandboxClient

浏览器沙盒客户端，封装 ai-sandbox REST API。适用于需要隔离环境的场景。

**文件**: `app/clients/sandbox_client.py`

```python
class SandboxClient:
    __init__(base_url="http://localhost:8000", timeout=180.0)

    # 沙盒生命周期（管理 API）
    async create_sandbox(name, resolution, memory, cpu) -> str     # 返回 sandbox_id
    async delete_sandbox(sandbox_id) -> None

    # 浏览器操作（沙盒内部 API）
    async navigate_to_url(sandbox_id, url) -> None
    async take_screenshot(sandbox_id) -> str                       # 返回 base64 PNG
    async scroll_page(sandbox_id, direction, amount) -> None

    # 资源管理
    async close() -> None
```

**关键实现**:
- `create_sandbox`: 预清理同名残留 → 创建容器（指定非默认端口） → 等待健康检查 → 初始化内部 API 客户端
- `navigate_to_url`: 通过 xdotool 模拟键盘操作完成 URL 导航
- `take_screenshot`: 通过 scrot 截取 X11 显示屏，返回 base64 编码 PNG

### CuaSandboxClient

CUA Computer-Server 持久化沙盒客户端，与 `SandboxClient` duck-type 兼容，`VisualReviewAgent` 可无缝切换使用。

**文件**: `app/clients/cua_sandbox_client.py`

```python
class CuaSandboxClient:
    __init__(base_url="http://...:8000", timeout=180.0)

    # 生命周期（空操作，CUA 是持久服务）
    async create_sandbox(name, resolution, memory, cpu) -> str     # 健康检查，返回固定 ID
    async delete_sandbox(sandbox_id) -> None                        # 空操作

    # 浏览器操作（POST /cmd）
    async navigate_to_url(sandbox_id, url) -> None
    async take_screenshot(sandbox_id) -> str                       # 返回 base64 PNG
    async scroll_page(sandbox_id, direction, amount) -> None

    # 额外能力
    async run_command(command) -> dict                              # 容器内 shell 命令
    async execute_js(script) -> Any                                # 浏览器内 JS 执行
    async get_current_url() -> str                                 # 获取当前页面 URL

    # 资源管理
    async close() -> None
```

**与 SandboxClient 的差异**:

| 特性 | SandboxClient | CuaSandboxClient |
|------|--------------|------------------|
| 服务模式 | Docker 容器，按需创建/销毁 | 持久化服务，常驻运行 |
| 创建开销 | ~15-20s（容器启动 + 健康检查） | ~0s（仅健康检查） |
| API 协议 | REST（管理 API + 沙盒内部 API） | SSE 流式响应（POST /cmd） |
| 导航方式 | xdotool 键盘模拟 | `open` 命令 |
| 额外功能 | 无 | Shell 命令、JS 执行、URL 获取 |

### VisualReviewAgent

视觉评审 Agent，继承 `BaseAgent`。

**文件**: `app/agents/review/visual_review_agent.py`

```python
class VisualReviewAgent(BaseAgent):
    agent_type = "visual_review"

    __init__(sandbox_client, sandbox_base_url, visual_quality_threshold=80, **kwargs)

    async setup()        # 创建沙盒
    async cleanup()      # 销毁沙盒
    async run(request: VisualReviewRequest) -> VisualReviewResponse
```

**多模态消息构建**:

Agent 使用 Anthropic content blocks 格式构建多模态消息：

```python
messages = [
    {
        "role": "system",
        "content": "You are a professional UI/UX translation quality reviewer..."
    },
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Reference screenshots:"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            {"type": "text", "text": "Target language screenshots:"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            {"type": "text", "text": "Evaluate... Respond in JSON format:..."},
        ],
    },
]
```

### VisualReviewService

视觉评审服务，协调 Agent 生命周期。

**文件**: `app/services/visual_review_service.py`

```python
class VisualReviewService:
    __init__(sandbox_base_url=os.getenv("SANDBOX_API_URL", "http://localhost:8000"))
    async execute_visual_review(request) -> VisualReviewResponse
```

使用 `async with VisualReviewAgent(...)` 管理 Agent 的 setup/cleanup 生命周期。

---

## API 接口

### 执行视觉评审

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
    "target_langs": ["zh-CN", "ja-JP", "ko-KR"],
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
            "issues": [
                {
                    "issue_type": "truncation",
                    "severity": "minor",
                    "location": "Navigation menu, third item",
                    "description": "Menu text slightly truncated with ellipsis",
                    "suggestion": "Shorten translation or increase container width"
                }
            ],
            "screenshots_count": 2,
            "feedback": "Overall good visual quality with minor text truncation"
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

**沙盒不可用时的降级响应**

```json
{
    "reviews": [],
    "reference_lang": "en-US",
    "total_languages": 3,
    "passed_count": 0,
    "failed_count": 0,
    "total_latency_ms": 0.0,
    "sandbox_error": "沙盒创建失败，无法执行视觉评审"
}
```

---

## 数据模型

### VisualReviewRequest

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_langs` | string[] | 目标语言代码列表 |
| `base_url` | string | 网站基础 URL |
| `url_path` | string | 语言代码后的路径 |
| `reference_lang` | string | 参考语言代码 |
| `scroll_positions` | int | 截图滚动次数 |
| `review_model` | string \| null | 评审模型 |
| `sandbox_resolution` | string | 沙盒分辨率 |

### VisualReviewResponse

| 字段 | 类型 | 说明 |
|------|------|------|
| `reviews` | VisualLanguageReview[] | 各语言评审结果 |
| `reference_lang` | string | 参考语言 |
| `total_languages` | int | 评审语言总数 |
| `passed_count` | int | 通过数量 |
| `failed_count` | int | 失败数量 |
| `total_latency_ms` | float | 总耗时（毫秒） |
| `sandbox_error` | string \| null | 沙盒错误信息 |

### VisualLanguageReview

| 字段 | 类型 | 说明 |
|------|------|------|
| `lang_code` | string | 语言代码 |
| `lang_name` | string | 语言名称 |
| `overall_score` | int | 总体评分 (0-100) |
| `layout_score` | int | 布局评分 (0-100) |
| `text_rendering_score` | int | 文本渲染评分 (0-100) |
| `translation_completeness_score` | int | 翻译完整性评分 (0-100) |
| `passed` | bool | 是否通过 |
| `issues` | VisualIssue[] | 问题列表 |
| `screenshots_count` | int | 截图数量 |
| `feedback` | string | 评审反馈 |

### VisualIssue

| 字段 | 类型 | 说明 |
|------|------|------|
| `issue_type` | string | 问题类型 |
| `severity` | string | 严重程度 |
| `location` | string | 问题位置描述 |
| `description` | string | 问题描述 |
| `suggestion` | string | 修复建议 |

---

## 错误处理

### 错误处理策略

| 场景 | 策略 | 影响 |
|------|------|------|
| 沙盒创建失败 | `setup()` 设 `sandbox_id=None`，`run()` 返回降级响应 | 所有语言评审跳过，`sandbox_error` 字段说明原因 |
| 页面加载失败 | 截图显示错误页面，LLM 分析后打低分 | 该语言得分偏低 |
| 单语言截图失败 | 该语言返回 0 分 + 失败反馈 | 其他语言正常继续 |
| LLM 调用失败 | 返回默认 70 分 + 描述性反馈 | 不阻塞其他语言 |
| LLM 响应解析失败 | 同上，返回默认 70 分 | 不阻塞其他语言 |
| 沙盒清理失败 | warning 日志 | 不影响评审结果 |

### 异常类型

| 异常 | 来源 | 说明 |
|------|------|------|
| `SandboxError` | `SandboxClient` | 沙盒操作失败（创建、导航、截图、删除） |
| `VisualReviewError` | `VisualReviewAgent` | 评审流程错误 |

---

## 配置

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SANDBOX_API_URL` | 沙盒管理 API 地址 | `http://localhost:8000` |
| `ANTHROPIC_API_KEY` | Claude API 密钥（多模态 LLM 调用需要） | - |

### Agent 默认模型

| Agent 类型 | 默认模型 | 说明 |
|------------|----------|------|
| `visual_review` | `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5，支持 Vision，速度优于 Opus |

### 沙盒默认参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `resolution` | `1920x1080` | 沙盒屏幕分辨率 |
| `memory` | `4GB` | 容器内存限制 |
| `cpu` | `2.0` | 容器 CPU 限制 |
| `vnc_port` | `5910` | VNC 端口 |
| `novnc_port` | `6910` | noVNC 端口 |
| `api_port` | `8010` | 内部 API 端口 |
| `timeout` | `180s` | HTTP 客户端超时 |

---

## 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `app/clients/sandbox_client.py` | 客户端 | Docker 沙盒 REST API 客户端 |
| `app/clients/cua_sandbox_client.py` | 客户端 | CUA 持久化沙盒客户端（duck-type 兼容） |
| `app/schemas/visual_review.py` | 数据模型 | 请求/响应 Pydantic 模型 |
| `app/agents/review/visual_review_agent.py` | Agent | 视觉评审 Agent |
| `app/services/visual_review_service.py` | 服务 | 视觉评审服务 |
| `app/api/v1/endpoints/visual_review.py` | API | 视觉评审端点 |

### 修改的已有文件

| 文件 | 修改内容 |
|------|----------|
| `app/clients/llm_client.py` | 消息类型从 `list[dict[str, str]]` 扩展为 `list[dict[str, Any]]` |
| `app/agents/base.py` | `_call_llm` 参数类型扩展 |
| `app/core/constants.py` | 添加 `visual_review` 默认模型 |
| `app/core/exceptions.py` | 添加 `SandboxError`、`VisualReviewError` |
| `app/api/v1/router.py` | 注册 `visual_review_router` |
| `app/clients/__init__.py` | 导出 `SandboxClient` |
| `app/agents/review/__init__.py` | 导出 `VisualReviewAgent` |
| `app/agents/__init__.py` | 导出 `VisualReviewAgent` |
| `app/schemas/__init__.py` | 导出视觉评审模型 |
| `app/core/__init__.py` | 导出 `SandboxError`、`VisualReviewError` |

---

## 使用示例

### cURL

```bash
curl -X POST http://localhost:8000/api/v1/visual-reviews \
  -H "Content-Type: application/json" \
  -d '{
    "target_langs": ["zh-CN", "ja-JP"],
    "base_url": "https://www.example.com",
    "url_path": "/ai",
    "reference_lang": "en-US",
    "scroll_positions": 1
  }'
```

### Python

```python
import httpx
import asyncio

async def visual_review():
    async with httpx.AsyncClient(
        base_url="http://localhost:8000",
        timeout=httpx.Timeout(600.0),  # 视觉评审耗时较长
    ) as client:
        response = await client.post("/api/v1/visual-reviews", json={
            "target_langs": ["zh-CN", "ja-JP", "ko-KR"],
            "base_url": "https://www.example.com",
            "url_path": "/ai",
        })
        result = response.json()

        if result.get("sandbox_error"):
            print(f"沙盒错误: {result['sandbox_error']}")
            return

        for review in result["reviews"]:
            status = "✅" if review["passed"] else "❌"
            print(f"{status} {review['lang_name']}: {review['overall_score']}/100")
            for issue in review["issues"]:
                print(f"   [{issue['severity']}] {issue['issue_type']}: {issue['description']}")

asyncio.run(visual_review())
```

---

## 前置依赖

### 浏览器沙盒服务（二选一）

#### 方案 A: ai-sandbox (Docker 容器沙盒)

视觉评审依赖 [ai-sandbox](../README.md) 服务提供浏览器沙盒环境：

```bash
# 启动 ai-sandbox 服务
cd ai-sandbox
docker-compose up -d
```

确保 ai-sandbox 管理 API 可访问（默认 `http://localhost:8000`）。

#### 方案 B: CUA Computer-Server (持久化沙盒)

使用 CUA 持久化浏览器服务作为替代方案，无需管理容器生命周期：

- CUA 服务需已部署并运行
- 通过 `CuaSandboxClient` 访问
- 性能优势：无容器创建开销，截图速度更快

### 环境变量

```bash
export SANDBOX_API_URL=http://localhost:8000     # 沙盒管理 API（ai-sandbox 或 CUA）
export ANTHROPIC_API_KEY=sk-ant-...              # Claude Vision API（原生模式）
# 或使用 Bedrock
export USE_BEDROCK=true
export AWS_BEARER_TOKEN_BEDROCK=...
```

---

## 性能参考

| 指标 | 参考值 | 说明 |
|------|--------|------|
| 沙盒创建 | ~15-20s | 包含 Docker 容器启动和健康检查 |
| 单语言截图 | ~20-30s | 导航 + 等待加载 + 截取 + 传输 |
| 单语言 LLM 评审 | ~30-60s | 多模态分析（含图片传输） |
| 2 语言完整评审 | ~5-10 min | 包含沙盒创建/销毁 |
| 5 语言完整评审 | ~15-20 min | 串行处理，线性增长 |
