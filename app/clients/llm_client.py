"""
统一 LLM 客户端

支持 OpenAI、Anthropic Claude 和 Google Gemini 模型
"""

import os
from typing import Any

import httpx
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock

from app.logger import logger
from app.core.constants import MODEL_CONFIGS
from app.core.exceptions import LLMClientError

# Bedrock 模型 ID 映射（原生模型名 → Bedrock 模型 ID）
BEDROCK_MODEL_MAP: dict[str, str] = {
    "claude-sonnet-4-5-20250929": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-opus-4-5-20251101": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "claude-opus-4-6": "us.anthropic.claude-opus-4-6-v1",
}


class AsyncAnthropicBedrockBearer(AsyncAnthropicBedrock):
    """使用 Bearer Token 认证的 Bedrock 客户端（跳过 SigV4 签名）"""

    def __init__(self, bearer_token: str, aws_region: str, **kwargs):
        self._bearer_token = bearer_token
        super().__init__(aws_region=aws_region, **kwargs)

    async def _prepare_request(self, request: httpx.Request) -> None:
        request.headers["Authorization"] = f"Bearer {self._bearer_token}"


class UnifiedLLMClient:
    """
    统一 LLM 客户端

    根据模型名称自动选择对应的 API 客户端
    """

    def __init__(self):
        self._openai_clients: dict[str, AsyncOpenAI] = {}
        self._anthropic_client: AsyncAnthropic | None = None
        self._bedrock_client: AsyncAnthropicBedrockBearer | None = None
        self._genai_client: Any = None
        self._use_bedrock: bool = os.getenv("USE_BEDROCK", "false").lower() == "true"

    def _get_openai_client(self, model: str) -> AsyncOpenAI:
        """获取 OpenAI 兼容客户端"""
        config = MODEL_CONFIGS.get(model)
        if not config:
            raise LLMClientError(model, f"未知的模型: {model}")

        base_url = config.get("base_url", "https://api.openai.com/v1/")
        api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.getenv(api_key_env)

        if not api_key:
            raise LLMClientError(model, f"API 密钥未设置: {api_key_env}")

        cache_key = f"{base_url}:{api_key_env}"
        if cache_key not in self._openai_clients:
            self._openai_clients[cache_key] = AsyncOpenAI(
                base_url=base_url, api_key=api_key
            )

        return self._openai_clients[cache_key]

    def _get_anthropic_client(self) -> AsyncAnthropic | AsyncAnthropicBedrockBearer:
        """获取 Anthropic 客户端（根据配置选择原生 API 或 Bedrock）"""
        if self._use_bedrock:
            return self._get_bedrock_client()
        if self._anthropic_client is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise LLMClientError("anthropic", "API 密钥未设置: ANTHROPIC_API_KEY")
            self._anthropic_client = AsyncAnthropic(api_key=api_key)
        return self._anthropic_client

    def _get_bedrock_client(self) -> AsyncAnthropicBedrockBearer:
        """获取 Bedrock Bearer Token 客户端"""
        if self._bedrock_client is None:
            token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
            region = os.getenv("AWS_REGION", "us-west-2")
            if not token:
                raise LLMClientError(
                    "bedrock", "AWS_BEARER_TOKEN_BEDROCK 未设置"
                )
            self._bedrock_client = AsyncAnthropicBedrockBearer(
                bearer_token=token, aws_region=region
            )
            logger.info(f"[_get_bedrock_client] 使用 Bedrock 端点，region={region}")
        return self._bedrock_client

    def _get_genai_client(self) -> Any:
        """获取 Google GenAI 客户端"""
        if self._genai_client is None:
            try:
                from google import genai

                self._genai_client = genai.Client()
            except ImportError:
                raise LLMClientError("gemini", "google-genai 库未安装")
        return self._genai_client

    def _get_thinking_level(self, model: str) -> str:
        """根据模型返回合适的 thinking level"""
        if "gemini-3-flash" in model:
            return "minimal"  # Flash 支持 minimal
        elif "gemini-3-pro" in model:
            return "low"  # Pro 最低只能 low
        elif "gemini-2" in model:
            return "off"  # 2.x 可以完全关闭
        return "low"

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        统一的聊天补全接口

        Args:
            model: 模型名称
            messages: 消息列表，content 可以是字符串或 content blocks 列表（多模态）
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            生成的文本内容
        """
        config = MODEL_CONFIGS.get(model)
        if not config:
            raise LLMClientError(model, f"未知的模型: {model}")

        provider = config.get("provider", "openai")

        try:
            if provider == "anthropic":
                return await self._call_anthropic(
                    model, messages, temperature, max_tokens
                )
            elif provider == "google":
                return await self._call_gemini(model, messages, temperature, max_tokens)
            else:
                return await self._call_openai(
                    model, messages, temperature, max_tokens
                )
        except Exception as e:
            logger.error(f"[chat_completion] LLM 调用失败 [{model}]: {e}")
            raise LLMClientError(model, str(e))

    def _is_reasoning_model(self, model: str) -> bool:
        """判断是否为推理模型（需要设置 reasoning_effort）"""
        # GPT-5.x 系列、o1/o3 系列是推理模型
        reasoning_prefixes = ("gpt-5", "o1", "o3")
        return any(model.startswith(prefix) for prefix in reasoning_prefixes)

    async def _call_openai(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用 OpenAI API"""
        client = self._get_openai_client(model)

        # 构建请求参数
        params: dict = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }

        # 对推理模型关闭思考以提升速度
        # GPT-5.x 支持 reasoning_effort=None 完全关闭
        # o1/o3 系列最低只能设置 "low"
        if self._is_reasoning_model(model):
            if model.startswith("gpt-5"):
                params["reasoning_effort"] = "none"
            else:
                # o1/o3 系列最低设置为 low
                params["reasoning_effort"] = "low"

        response = await client.chat.completions.create(**params)
        content = response.choices[0].message.content
        return content.strip() if content else ""

    async def _call_anthropic(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用 Anthropic Claude API（支持原生 API 和 Bedrock）"""
        client = self._get_anthropic_client()

        # Bedrock 需要转换模型 ID
        actual_model = model
        if self._use_bedrock:
            actual_model = BEDROCK_MODEL_MAP.get(model)
            if not actual_model:
                raise LLMClientError(
                    model, f"未找到 Bedrock 模型映射: {model}"
                )

        # 分离 system 消息和其他消息
        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                chat_messages.append(msg)

        # 注意：不传递 thinking 参数即为关闭扩展思考（extended thinking）
        # 如需启用，需添加: thinking={"type": "enabled", "budget_tokens": 4096}
        # 构建请求参数
        params: dict = {
            "model": actual_model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        # 新版 Anthropic API 要求 system 是列表格式
        if system_content:
            params["system"] = [{"type": "text", "text": system_content}]

        response = await client.messages.create(**params)
        return response.content[0].text.strip()

    async def _call_gemini(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用 Google Gemini API"""
        from google.genai import types

        client = self._get_genai_client()

        # 分离 system 消息和其他消息
        system_instruction = None
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=msg["content"])]
                ))
            elif msg["role"] == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=msg["content"])]
                ))

        # 如果只有一条消息，直接使用文本
        if len(contents) == 1 and contents[0].role == "user":
            contents = contents[0].parts[0].text

        # 配置 thinking level 以提升速度
        thinking_level = self._get_thinking_level(model)
        if thinking_level == "off":
            # Gemini 2.x 使用 thinking_budget=0 完全关闭
            thinking_config = types.ThinkingConfig(thinking_budget=0)
        else:
            thinking_config = types.ThinkingConfig(thinking_level=thinking_level)

        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_tokens,
                thinking_config=thinking_config,
            ),
        )
        return response.text.strip()

    async def close(self) -> None:
        """关闭所有客户端连接"""
        for client in self._openai_clients.values():
            await client.close()
        self._openai_clients.clear()

        if self._anthropic_client is not None:
            await self._anthropic_client.close()
            self._anthropic_client = None

        if self._bedrock_client is not None:
            await self._bedrock_client.close()
            self._bedrock_client = None

        # Google GenAI 客户端不需要显式关闭
        self._genai_client = None
