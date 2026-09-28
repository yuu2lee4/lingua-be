"""
浏览器沙盒客户端

封装 ai-sandbox REST API，提供浏览器自动化操作。
采用两层架构：管理 API 负责沙盒生命周期，沙盒内部 API 负责操作和截图。
"""

import asyncio
from urllib.parse import urlparse

import httpx

from app.logger import logger
from app.core.exceptions import SandboxError


class SandboxClient:
    """
    浏览器沙盒客户端

    管理 API（:8000）：创建/删除沙盒、获取沙盒信息
    沙盒内部 API（:{api_port}）：键盘/鼠标操作、截图
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 180.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # 管理 API 客户端
        self._mgmt_client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )
        # 沙盒内部 API 客户端（创建沙盒后初始化）
        self._sandbox_client: httpx.AsyncClient | None = None

    async def create_sandbox(
        self,
        name: str = "visual-review",
        resolution: str = "1920x1080",
        memory: str = "4GB",
        cpu: float = 2.0,
    ) -> str:
        """
        创建浏览器沙盒实例

        使用非默认端口（59xx/69xx/80xx）避免与管理 API 和其他沙盒冲突

        Args:
            name: 沙盒名称
            resolution: 屏幕分辨率
            memory: 内存限制
            cpu: CPU 限制

        Returns:
            沙盒 ID
        """
        # 清理同名沙盒（包括 Docker 残留）
        for _ in range(2):
            await self._mgmt_client.delete(f"/api/v1/sandbox/{name}")
            await asyncio.sleep(1)

        create_payload = {
            "name": name,
            "resolution": resolution,
            "memory": memory,
            "cpu": cpu,
            # 使用非默认端口避免与管理 API（:8000）及其他服务冲突
            "vnc_port": 5910,
            "novnc_port": 6910,
            "api_port": 8010,
        }

        try:
            response = await self._mgmt_client.post(
                "/api/v1/sandbox",
                json=create_payload,
            )

            # 如果创建失败（端口冲突等），尝试删除残留并重建
            if response.status_code != 201:
                await self._mgmt_client.delete(f"/api/v1/sandbox/{name}")
                await asyncio.sleep(2)
                response = await self._mgmt_client.post(
                    "/api/v1/sandbox",
                    json=create_payload,
                )

            response.raise_for_status()
            data = response.json()
            sandbox_id = data["id"]
            api_port = data.get("api_port")

            # 构建沙盒内部 API 的 base_url
            parsed = urlparse(self._base_url)
            sandbox_base = f"{parsed.scheme}://{parsed.hostname}:{api_port}"
            self._sandbox_client = httpx.AsyncClient(
                base_url=sandbox_base,
                timeout=httpx.Timeout(self._timeout),
            )

            # 等待沙盒内部服务就绪
            await self._wait_for_sandbox_ready()

            logger.info(
                f"[SandboxClient.create_sandbox] 沙盒已创建: {sandbox_id}, "
                f"内部 API: {sandbox_base}"
            )
            return sandbox_id
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"创建沙盒失败: {e}")

    async def _wait_for_sandbox_ready(self, max_retries: int = 20) -> None:
        """等待沙盒内部 API 就绪"""
        for i in range(max_retries):
            try:
                response = await self._sandbox_client.get("/health")
                if response.status_code == 200:
                    logger.info(
                        f"[SandboxClient._wait_for_sandbox_ready] "
                        f"沙盒就绪 (尝试 {i + 1}/{max_retries})"
                    )
                    return
            except Exception:
                pass
            await asyncio.sleep(1)
        raise SandboxError("沙盒内部 API 未在超时时间内就绪")

    async def navigate_to_url(self, sandbox_id: str, url: str) -> None:
        """
        在沙盒浏览器中导航到指定 URL

        通过模拟键盘操作：Ctrl+L → Ctrl+A → 输入 URL → Enter → 等待加载

        Args:
            sandbox_id: 沙盒 ID
            url: 目标 URL
        """
        try:
            # 聚焦地址栏
            await self._send_action({"action": "key", "key": "ctrl+l"})
            await asyncio.sleep(0.3)

            # 全选当前 URL
            await self._send_action({"action": "key", "key": "ctrl+a"})
            await asyncio.sleep(0.2)

            # 输入新 URL
            await self._send_action({"action": "type", "text": url})
            await asyncio.sleep(0.3)

            # 回车导航
            await self._send_action({"action": "key", "key": "Return"})

            # 等待页面加载
            await asyncio.sleep(8)

            logger.info(
                f"[SandboxClient.navigate_to_url] 已导航到: {url}"
            )
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"导航失败 [{url}]: {e}")

    async def take_screenshot(self, sandbox_id: str) -> str:
        """
        截取沙盒浏览器当前画面

        Args:
            sandbox_id: 沙盒 ID

        Returns:
            base64 编码的 PNG 截图
        """
        self._ensure_sandbox_client()
        try:
            response = await self._sandbox_client.get("/screenshot")
            response.raise_for_status()
            data = response.json()
            screenshot = data["image"]
            logger.info(
                f"[SandboxClient.take_screenshot] 截图成功, "
                f"大小: {len(screenshot)} chars"
            )
            return screenshot
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
            sandbox_id: 沙盒 ID
            direction: 滚动方向 (up/down)
            amount: 滚动量
        """
        try:
            await self._send_action({
                "action": "scroll",
                "x": 512,
                "y": 384,
                "direction": direction,
                "amount": amount,
            })
            await asyncio.sleep(1)
            logger.info(
                f"[SandboxClient.scroll_page] 滚动 {direction} x{amount}"
            )
        except Exception as e:
            raise SandboxError(f"滚动失败: {e}")

    async def delete_sandbox(self, sandbox_id: str) -> None:
        """
        删除沙盒实例

        Args:
            sandbox_id: 沙盒 ID
        """
        try:
            response = await self._mgmt_client.delete(
                f"/api/v1/sandbox/{sandbox_id}",
            )
            response.raise_for_status()
            logger.info(
                f"[SandboxClient.delete_sandbox] 沙盒已删除: {sandbox_id}"
            )
        except Exception as e:
            logger.warning(
                f"[SandboxClient.delete_sandbox] 删除沙盒失败: {e}"
            )

    async def close(self) -> None:
        """关闭所有 HTTP 客户端"""
        await self._mgmt_client.aclose()
        if self._sandbox_client:
            await self._sandbox_client.aclose()

    def _ensure_sandbox_client(self) -> None:
        """确保沙盒内部 API 客户端已初始化"""
        if self._sandbox_client is None:
            raise SandboxError("沙盒内部 API 客户端未初始化，请先调用 create_sandbox")

    async def _send_action(self, action: dict) -> None:
        """通过沙盒内部 API 发送操作"""
        self._ensure_sandbox_client()
        response = await self._sandbox_client.post("/action", json=action)
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            raise SandboxError(f"操作失败: {data.get('message')}")
