"""Log config"""

import os
import json
import sys
import logging
import traceback
from loguru import logger
from pathlib import Path


class LogConfig:
    @staticmethod
    def init_logger(project_root: str = None):
        """初始化JSON格式日志配置

        Args:
            project_root: 项目根目录路径（用于生成相对路径）
        """
        # 设置第三方库日志级别，禁用 DEBUG 日志
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("httpcore").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.INFO)

        # 获取项目根目录（如果未指定则自动推断）
        if not project_root:
            project_root = str(Path(__file__).parent.parent)

        def formatter(record):
            """自定义JSON格式化函数"""
            # 时间格式化（保留毫秒）
            timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            # 获取相对路径
            abs_path = record["file"].path
            try:
                rel_path = os.path.relpath(abs_path, start=project_root)
            except ValueError:
                rel_path = abs_path

            # 构建调用位置信息
            caller = f"{rel_path}:{record['line']}"

            # 异常堆栈处理
            stacktrace = ""
            exception = record.get("exception")
            if exception:
                stacktrace = "".join(
                    traceback.format_exception(
                        exception.value,  # 获取实际的异常对象
                        limit=None,
                        chain=True,
                    )
                )
            # 构建完整日志结构
            log_data = {
                "level": record["level"].name,
                "time": timestamp,
                "caller": caller,
                "msg": record["message"],
                "stacktrace": stacktrace,
                "tid": record["extra"].get("tid", ""),
                "event": record["extra"].get("event", ""),
                "biz_monitor_ctx": record["extra"].get("biz_monitor_ctx", {}),
            }
            record["extra"]["_json_"] = json.dumps(log_data, ensure_ascii=False)

        # 清除默认配置并添加新配置
        logger.remove()
        log_path = "logs/app.log"
        json_stdout = os.environ.get("LOG_JSON_STDOUT", "").lower() in ("1", "true")

        # 文件日志 (JSON 格式)
        logger.add(
            sink=log_path,
            format=lambda _: "{extra[_json_]}\n",
            rotation="500 MB",
            retention="7 days",
            compression="zip",
            level="INFO",
            enqueue=True,  # 线程安全
            backtrace=True,  # 记录异常堆栈
            diagnose=True,  # 显示变量值
        )

        if json_stdout:
            # K8s 环境: JSON 格式直接输出到 stdout，供 Loki 采集
            logger.add(
                sink=sys.stdout,
                format=lambda _: "{extra[_json_]}\n",
                level="INFO",
                enqueue=True,
                colorize=False,
            )
        else:
            # 本地开发: 人类可读格式
            logger.add(
                sink=sys.stdout,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                       "<level>{level: <8}</level> | "
                       "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                       "<level>{message}</level>",
                level="INFO",
                colorize=True,
            )

        logger.configure(patcher=formatter)


try:
    # 初始化日志
    LogConfig.init_logger()
    logger.info("Logger init...")

except Exception as e:
    logger.error(f"Failed init logger: {str(e)}")
