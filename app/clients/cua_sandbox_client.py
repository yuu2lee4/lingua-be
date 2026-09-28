"""
CUA Computer-Server 沙盒客户端

封装 CUA 持久化浏览器服务的 REST API，与 SandboxClient duck-type 兼容。
CUA 是已运行的持久服务，无需创建/销毁沙盒，所有操作通过 POST /cmd 完成。
API 使用 SSE 流式响应，每条消息格式为 "data: {json}\n\n"。
"""

import asyncio
import json
from typing import Any

import httpx

from app.logger import logger
from app.core.exceptions import SandboxError


class CuaSandboxClient:
    """
    CUA Computer-Server 客户端

    与 SandboxClient duck-type 兼容，使 VisualReviewAgent 可无缝切换使用。
    核心差异：CUA 是持久服务，无需创建/销毁容器。

    API 端点：POST /cmd，payload: {"command": "...", "params": {...}}
    响应格式：SSE 流（data: {json}）
    """

    DUMMY_SANDBOX_ID = "cua-persistent"

    def __init__(
        self,
        base_url: str = "http://103.101.206.247:8000",
        timeout: float = 180.0,
        page_load_wait: float = 8.0,
        scroll_wait: float = 1.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._page_load_wait = page_load_wait
        self._scroll_wait = scroll_wait
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )

    async def create_sandbox(
        self,
        name: str = "visual-review",
        resolution: str = "1920x1080",
        memory: str = "4GB",
        cpu: float = 2.0,
    ) -> str:
        """
        健康检查 CUA 服务，返回固定沙盒 ID

        Returns:
            固定沙盒 ID
        """
        try:
            response = await self._client.get("/status")
            response.raise_for_status()
            logger.info(
                f"[CuaSandboxClient.create_sandbox] CUA 服务健康检查通过, "
                f"base_url={self._base_url}"
            )
            return self.DUMMY_SANDBOX_ID
        except httpx.HTTPError as e:
            raise SandboxError(f"CUA 服务不可达 [{self._base_url}]: {e}")
        except Exception as e:
            raise SandboxError(f"CUA 健康检查失败: {e}")

    async def navigate_to_url(self, sandbox_id: str, url: str) -> None:
        """
        在 CUA 浏览器中导航到指定 URL

        使用 open 命令打开 URL，然后等待页面加载。

        Args:
            sandbox_id: 沙盒 ID（忽略）
            url: 目标 URL
        """
        try:
            await self._exec("open", {"target": url})
            await asyncio.sleep(self._page_load_wait)
            logger.info(
                f"[CuaSandboxClient.navigate_to_url] 已导航到: {url}"
            )
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"导航失败 [{url}]: {e}")

    async def take_screenshot(self, sandbox_id: str) -> str:
        """
        截取 CUA 浏览器当前画面

        Args:
            sandbox_id: 沙盒 ID（忽略）

        Returns:
            base64 编码的 PNG 截图
        """
        try:
            result = await self._exec("screenshot", {})
            screenshot = result.get("image_data", "")
            if not screenshot:
                raise SandboxError("截图响应中缺少 image_data 字段")
            logger.info(
                f"[CuaSandboxClient.take_screenshot] 截图成功, "
                f"大小: {len(screenshot)} chars"
            )
            return screenshot
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"截图失败: {e}")

    async def scroll_page(
        self,
        sandbox_id: str,
        direction: str = "down",
        amount: int = 3,
    ) -> None:
        """
        滚动页面

        Args:
            sandbox_id: 沙盒 ID（忽略）
            direction: 滚动方向 (up/down)
            amount: 滚动量（clicks）
        """
        try:
            cmd = "scroll_down" if direction == "down" else "scroll_up"
            await self._exec(cmd, {"clicks": amount})
            await asyncio.sleep(self._scroll_wait)
            logger.info(
                f"[CuaSandboxClient.scroll_page] 滚动 {direction} x{amount}"
            )
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"滚动失败: {e}")

    async def delete_sandbox(self, sandbox_id: str) -> None:
        """删除沙盒（空操作，CUA 是持久服务）"""
        logger.info(
            "[CuaSandboxClient.delete_sandbox] CUA 持久服务，跳过删除"
        )

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        await self._client.aclose()

    async def run_command(self, command: str) -> dict:
        """
        在 CUA 容器内执行 shell 命令

        Args:
            command: shell 命令

        Returns:
            {"stdout": str, "stderr": str, "return_code": int}
        """
        try:
            return await self._exec("run_command", {"command": command})
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"Shell 命令执行失败: {e}")

    async def execute_js(self, script: str) -> Any:
        """
        通过容器内 python3 + urllib 获取页面后提取信息，
        或通过 xdotool 在浏览器中执行 JS。

        此方法使用 run_command 在容器中运行 python3 脚本实现。

        Args:
            script: 要执行的 JavaScript 表达式（会被包装到 python3 脚本中
                    通过 Ctrl+L 地址栏注入 javascript: 协议执行）

        Returns:
            脚本执行结果
        """
        # 使用 xdotool + xclip 方案：
        # 1. 在地址栏执行 javascript: 将结果写入剪贴板
        # 2. 通过 xclip 读取剪贴板内容
        js_wrapped = (
            f"javascript:void(document.title=JSON.stringify({script}))"
        )
        # 聚焦地址栏 → 输入 JS → 执行
        await self._exec("hotkey", {"keys": ["ctrl", "l"]})
        await asyncio.sleep(0.3)
        await self._exec("type_text", {"text": js_wrapped})
        await asyncio.sleep(0.3)
        await self._exec("press_key", {"key": "Return"})
        await asyncio.sleep(1.0)

        # 通过 xdotool 获取窗口标题（即 JSON.stringify 结果）
        result = await self._exec(
            "run_command",
            {"command": "xdotool getactivewindow getwindowname"},
        )
        title = result.get("stdout", "").strip()
        try:
            return json.loads(title)
        except (json.JSONDecodeError, TypeError):
            return title

    async def get_current_url(self) -> str:
        """
        获取当前页面 URL

        通过地址栏复制获取。
        """
        try:
            await self._exec("hotkey", {"keys": ["ctrl", "l"]})
            await asyncio.sleep(0.3)
            await self._exec("hotkey", {"keys": ["ctrl", "c"]})
            await asyncio.sleep(0.2)
            result = await self._exec(
                "run_command",
                {"command": "xclip -selection clipboard -o 2>/dev/null || echo ''"},
            )
            return result.get("stdout", "").strip()
        except Exception as e:
            raise SandboxError(f"获取当前 URL 失败: {e}")

    async def _exec(self, command: str, params: dict) -> dict:
        """
        执行 CUA 命令

        API 返回 SSE 流，提取最后一条 data: 行的 JSON。

        Args:
            command: 命令名称
            params: 命令参数

        Returns:
            响应数据字典
        """
        payload = {"command": command, "params": params}
        try:
            response = await self._client.post("/cmd", json=payload)
            response.raise_for_status()

            # 解析 SSE 流式响应：提取最后一个 "data: {json}" 行
            data = self._parse_sse_response(response.text)

            if not data.get("success", True):
                error_msg = data.get("error", data.get("message", "未知错误"))
                raise SandboxError(
                    f"CUA 命令执行失败 [{command}]: {error_msg}"
                )
            return data
        except SandboxError:
            raise
        except httpx.HTTPError as e:
            raise SandboxError(f"CUA 请求失败 [{command}]: {e}")
        except Exception as e:
            raise SandboxError(f"CUA 执行异常 [{command}]: {e}")

    @staticmethod
    def _parse_sse_response(text: str) -> dict:
        """
        解析 SSE 流式响应，提取最后一条 data 行的 JSON

        Args:
            text: 原始响应文本

        Returns:
            解析后的字典
        """
        last_data = {}
        for line in text.strip().splitlines():
            line = line.strip()
            if line.startswith("data: "):
                json_str = line[6:]  # 去掉 "data: " 前缀
                try:
                    last_data = json.loads(json_str)
                except json.JSONDecodeError:
                    pass
        return last_data
