# AI Translation Service

<p align="center">
  <img src="https://img.shields.io/badge/Claude%20Agent%20SDK-0.2+-orange?logo=anthropic&logoColor=white" alt="Claude Agent SDK">
  <img src="https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.104+-green?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/uv-Package%20Manager-purple" alt="uv">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker">
</p>

基于 **Claude Agent SDK** 构建的现代化 AI 翻译 Agent，提供智能化翻译服务。

> **🎯 快速体验**: `git clone <repo> && cd ai-translation && uv run uvicorn app.main:app --reload`

## ✨ 特性

- 🤖 **Claude Agent SDK 驱动** - 基于 Anthropic 官方 Agent SDK
- 🧠 **智能翻译策略** - Agent 自动分析文本特征，选择最佳翻译引擎
- 🚀 **高性能异步 API** - 基于 FastAPI 构建
- 🔄 **多翻译引擎支持** - 集成 Google Translate、DeepL、OpenAI 等
- 🌐 **多语言支持** - 支持 100+ 种语言互相翻译
- 🔧 **工具化架构** - 基于 Agent SDK 的工具系统
- 🎯 **现代开发体验** - uv 包管理、自动格式化、类型检查
- 🐳 **容器化部署** - Docker 支持

## 🛠 技术栈

- **[Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk)** - AI Agent 开发框架
- **[FastAPI](https://fastapi.tiangolo.com/)** - 现代高性能 Web 框架
- **[Loguru](https://loguru.readthedocs.io/)** - 高性能结构化日志库
- **[Apollo](https://github.com/apolloconfig/apollo)** - 分布式配置中心
- **[uv](https://docs.astral.sh/uv/)** - 现代 Python 包管理器

## 🚀 快速开始

### 环境要求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 包管理器

### 安装 uv

```bash
brew install uv
```

### 启动服务

```bash
# 安装依赖并启动开发服务器
uv sync --group dev
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## 📖 API 文档

### 启动后访问

- **交互式 API 文档**: http://localhost:8080/docs
- **ReDoc 文档**: http://localhost:8080/redoc

### 主要端点

#### 根路径
```bash
GET /
```

#### 健康检查
```bash
GET /healthz
```

响应：
```json
{
  "msg": "OK"
}
```

#### 服务信息
```bash
GET /api/v1/info
```

#### 翻译文本 (待实现)
```bash
POST /api/v1/translate
```

请求体：
```json
{
  "text": "Hello, world!",
  "source_lang": "en",
  "target_lang": "zh",
  "engine": "google"
}
```

## ⚙️ 配置管理

本项目基于 **Apollo 配置中心** 进行配置管理，通过环境变量指定运行环境。

### 环境配置
通过 `ENV` 环境变量指定运行环境，系统会自动选择对应的 Apollo 配置中心：

```bash
# 本地开发环境 (默认)
export ENV=LOCAL

# 开发环境
export ENV=DEV

# 测试环境
export ENV=TEST

# 生产环境
export ENV=PROD
```

### Apollo 配置中心
不同环境对应不同的 Apollo 配置服务器，所有配置项都从对应环境的配置中心获取：
- 应用基础配置（服务端口、日志级别等）
- 翻译服务 API 密钥
- 第三方服务配置

更多配置详情请参考 `app/config/settings.py` 和 `app/config/configuration.py`。

## 🐳 Docker 部署

```bash
# 构建镜像
docker build -t ai-translation:latest .

# 运行容器 (本地环境)
docker run -d \
  --name ai-translation \
  -p 8080:8080 \
  -e ENV=LOCAL \
  ai-translation:latest

# 运行容器 (生产环境)
docker run -d \
  --name ai-translation \
  -p 8080:8080 \
  -e ENV=PROD \
  ai-translation:latest
```

## 📁 项目结构

```
ai-translation/
├── app/                          # 应用源码
│   ├── main.py                   # FastAPI 应用入口
│   ├── agents/                   # Claude Agent SDK 集成
│   ├── config/                   # 配置管理
│   ├── logger/                   # 日志系统
│   ├── api/v1/                   # API 路由
│   ├── services/                 # 业务逻辑
│   └── schemas/                  # Pydantic 模型
├── tests/                        # 测试文件
├── pyproject.toml               # 项目配置和依赖
└── README.md                    # 项目文档
```

## 🤝 贡献

1. Fork 项目并创建特性分支
2. 遵循项目代码规范
3. 编写测试并确保通过
4. 提交 Pull Request

## 📄 许可证

[MIT License](LICENSE)

---

**快速开始命令**：
```bash
git clone <repo-url> && cd ai-translation && uv sync --group dev && uv run uvicorn app.main:app --reload
```

访问 http://localhost:8080/docs 查看 API 文档 🚀
