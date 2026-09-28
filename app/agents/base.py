"""
基础 Agent 类

提供统一的 LLM 调用接口和生命周期管理
"""

from abc import ABC, abstractmethod
from typing import Any

from app.logger import logger
from app.clients.llm_client import UnifiedLLMClient
from app.core.constants import AGENT_DEFAULT_MODELS


class BaseAgent(ABC):
    """
    基础 Agent 类

    所有 Agent 继承此类，获得统一的 LLM 调用能力
    """

    # Agent 类型，子类需要覆盖
    agent_type: str = "base"

    def __init__(
        self,
        model: str | None = None,
        llm_client: UnifiedLLMClient | None = None,
    ):
        """
        初始化 Agent

        Args:
            model: 使用的模型名称，默认根据 agent_type 从配置获取
            llm_client: LLM 客户端实例，默认创建新实例
        """
        self._model = model or AGENT_DEFAULT_MODELS.get(self.agent_type)
        self._llm_client = llm_client or UnifiedLLMClient()
        self._owns_client = llm_client is None  # 标记是否拥有客户端

    @property
    def model(self) -> str:
        """获取模型名称"""
        return self._model

    async def setup(self) -> None:
        """
        初始化钩子

        子类可以覆盖此方法执行初始化逻辑
        """
        pass

    async def cleanup(self) -> None:
        """
        清理钩子

        子类可以覆盖此方法执行清理逻辑
        """
        if self._owns_client:
            await self._llm_client.close()

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        调用 LLM

        Args:
            messages: 消息列表，content 可以是字符串或 content blocks 列表（多模态）
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            生成的文本内容
        """
        logger.info(
            f"[{self.__class__.__name__}._call_llm] 调用 LLM, model={self._model}"
        )
        return await self._llm_client.chat_completion(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """
        执行 Agent 主逻辑

        子类必须实现此方法
        """
        pass

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.cleanup()
