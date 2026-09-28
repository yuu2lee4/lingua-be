"""Consul 服务注册、注销与发现（基于 httpx 异步实现）"""

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from ..logger import logger


def _get_local_ip() -> str:
    """获取本机 IP 地址"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


@dataclass
class ServiceEndpoint:
    """表示发现的服务端点"""

    address: str
    port: int
    service_id: str = ""
    tags: list[str] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"


@dataclass
class _CacheEntry:
    """缓存条目，带 TTL"""

    endpoints: list[ServiceEndpoint]
    timestamp: float


class ConsulService:
    """Consul 服务注册、注销与发现（httpx 异步实现，带 TTL 缓存）"""

    def __init__(
        self,
        host: str,
        port: int,
        cache_ttl: int = 30,
        timeout: int = 10,
    ):
        self.base_url = f"http://{host}:{port}"
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.service_id: Optional[str] = None
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()

    async def register(
        self,
        service_name: str = "ai-translation",
        service_port: int = 8080,
        health_check_url: Optional[str] = None,
    ) -> None:
        """注册服务到 Consul，附带 HTTP 健康检查"""
        local_ip = _get_local_ip()
        self.service_id = f"{service_name}-{local_ip}-{service_port}"

        if health_check_url is None:
            health_check_url = f"http://{local_ip}:{service_port}/healthz"

        payload = {
            "ID": self.service_id,
            "Name": service_name,
            "Address": local_ip,
            "Port": service_port,
            "Check": {
                "HTTP": health_check_url,
                "Interval": "10s",
                "Timeout": f"{self.timeout}s",
                "DeregisterCriticalServiceAfter": "30s",
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.base_url}/v1/agent/service/register",
                json=payload,
            )
            resp.raise_for_status()

        logger.info(f"Consul 注册成功: {self.service_id} -> {health_check_url}")

    async def deregister(self) -> None:
        """从 Consul 注销当前服务"""
        if not self.service_id:
            return

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.put(
                    f"{self.base_url}/v1/agent/service/deregister/{self.service_id}",
                )
                resp.raise_for_status()
            logger.info(f"Consul 注销成功: {self.service_id}")
        except Exception as e:
            logger.warning(f"Consul 注销失败: {self.service_id}, error: {e}")
        finally:
            self.service_id = None

    async def discover_service(
        self, service_name: str, passing: bool = True
    ) -> list[ServiceEndpoint]:
        """发现服务，带 TTL 缓存和 stale fallback"""
        # 检查缓存是否有效
        with self._lock:
            entry = self._cache.get(service_name)
            if entry and (time.monotonic() - entry.timestamp) < self.cache_ttl:
                return entry.endpoints

        # 缓存过期或不存在，从 Consul 获取
        try:
            params = {"passing": "true"} if passing else {}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/v1/health/service/{service_name}",
                    params=params,
                )
                resp.raise_for_status()

            endpoints = []
            for item in resp.json():
                svc = item.get("Service", {})
                endpoints.append(
                    ServiceEndpoint(
                        address=svc.get("Address", ""),
                        port=svc.get("Port", 0),
                        service_id=svc.get("ID", ""),
                        tags=svc.get("Tags") or [],
                        meta=svc.get("Meta") or {},
                    )
                )

            # 更新缓存
            with self._lock:
                self._cache[service_name] = _CacheEntry(
                    endpoints=endpoints,
                    timestamp=time.monotonic(),
                )
            return endpoints

        except Exception as e:
            # Stale fallback: 发现失败时返回过期缓存
            with self._lock:
                stale = self._cache.get(service_name)
            if stale:
                logger.warning(
                    f"Consul 发现失败，使用 stale 缓存: {service_name}, error: {e}"
                )
                return stale.endpoints
            raise


# ── 模块级单例 ──────────────────────────────────────────────

_consul_service: Optional[ConsulService] = None
_init_lock = threading.Lock()


def get_consul_service() -> Optional[ConsulService]:
    """延迟初始化 ConsulService 单例，读取 Config 中的 consul 配置。
    配置不可用时返回 None。
    """
    global _consul_service
    if _consul_service is not None:
        return _consul_service

    with _init_lock:
        if _consul_service is not None:
            return _consul_service

        try:
            from ..config.configuration import Config

            _consul_service = ConsulService(
                host=Config.consul_host,
                port=Config.consul_port,
                cache_ttl=Config.consul_cache_ttl,
                timeout=Config.consul_timeout,
            )
            return _consul_service
        except Exception as e:
            logger.debug(f"ConsulService 初始化跳过: {e}")
            return None
