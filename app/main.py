"""
AI Translation Service - FastAPI 应用入口

基于 Claude Agent SDK 的智能翻译服务
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
from datetime import datetime
from typing import Dict, Any

# 导入日志系统
from .logger import logger

# 导入配置（可能会失败，做异常处理）
try:
    from .config.configuration import Config

    CONFIG_AVAILABLE = True
    logger.info("Apollo 配置加载成功")
except Exception as e:
    CONFIG_AVAILABLE = False
    logger.warning(f"Apollo 配置加载失败，使用默认配置: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=== AI Translation Service 启动 ===")
    logger.info(f"配置状态: {'Apollo配置可用' if CONFIG_AVAILABLE else '使用默认配置'}")

    # 初始化数据库连接池
    db_initialized = False
    if CONFIG_AVAILABLE:
        try:
            from .db.connection import DatabasePool

            await DatabasePool.initialize(
                host=Config.mysql_host,
                port=Config.mysql_port,
                user=Config.mysql_user,
                password=Config.mysql_password,
                database=Config.mysql_database,
                pool_size=Config.mysql_pool_size,
                pool_recycle=Config.mysql_pool_recycle,
            )
            db_initialized = True
            logger.info("MySQL 连接池初始化成功")

            # ============ Two-Tier Glossary Initialization ============
            from pathlib import Path

            # Initialize Match Glossary from YAML (Level 1: Direct translation lookup)
            from .services.match_glossary_service import match_glossary_service

            yaml_glossary_path = Path(__file__).parent.parent / "examples" / "glossary.yaml"
            match_imported, match_skipped, match_errors = await match_glossary_service.initialize_from_yaml(
                yaml_glossary_path
            )
            if match_imported > 0:
                logger.info(f"Match Glossary: 已从 YAML 导入 {match_imported} 条术语")
            if match_errors:
                logger.warning(f"Match Glossary 初始化存在错误: {match_errors}")

            # Initialize Business AI Glossary from JSON (Level 2: AI-curated terms for prompt enrichment)
            from .repositories.glossary_repository import glossary_repository

            business_imported, business_skipped, business_errors = await glossary_repository.initialize_from_default_glossary()
            if business_imported > 0:
                logger.info(f"Business AI Glossary: 已从 JSON 导入 {business_imported} 条术语")
            if business_errors:
                logger.warning(f"Business AI Glossary 初始化存在错误: {business_errors}")

            # Warm up glossary caches
            from .services.glossary_service import glossary_service

            await glossary_service.warmup_cache()
            await match_glossary_service.warmup_cache()

            logger.info("Two-tier glossary system initialized")
        except Exception as e:
            logger.warning(f"MySQL 连接池初始化失败，术语表将使用文件模式: {e}")

    # Binance 术语库初始化（不依赖数据库，从本地 JSON 加载）
    try:
        from .services.binance_glossary_service import binance_glossary_service

        await binance_glossary_service.load()
        logger.info(
            f"Binance glossary loaded: L1={binance_glossary_service.l1_count}, "
            f"L2={binance_glossary_service.l2_count}"
        )
    except Exception as e:
        logger.warning(f"Binance glossary load failed: {e}")

    # Consul 服务注册
    consul_service = None
    if CONFIG_AVAILABLE:
        try:
            from .services.consul_service import get_consul_service

            consul_service = get_consul_service()
            if consul_service:
                await consul_service.register()
        except Exception as e:
            logger.warning(f"Consul 注册失败，服务将继续运行: {e}")

    # 启动任务存储清理任务
    from .storage.job_store import job_store
    await job_store.start_cleanup_task()

    # Task API: 恢复未完成的异步任务
    if db_initialized:
        try:
            from .services.task_service import task_service

            await task_service.initialize()
            logger.info("Task Service 初始化完成")
        except Exception as e:
            logger.warning(f"Task Service 初始化失败: {e}")

    yield

    # 关闭时执行
    await job_store.stop_cleanup_task()

    # Consul 服务注销
    if consul_service:
        await consul_service.deregister()

    # 关闭数据库连接池
    if db_initialized:
        try:
            from .db.connection import DatabasePool

            await DatabasePool.close()
            logger.info("MySQL 连接池已关闭")
        except Exception as e:
            logger.warning(f"MySQL 连接池关闭失败: {e}")

    logger.info("=== AI Translation Service 关闭 ===")


# 创建 FastAPI 应用
app = FastAPI(
    title="AI Translation Service",
    description="基于 Claude Agent SDK 构建的智能化 AI 翻译服务",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error(f"未处理异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "内部服务器错误", "message": "服务暂时不可用，请稍后重试"},
    )


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "AI Translation Service",
        "version": "0.1.0",
        "description": "基于 Claude Agent SDK 的智能翻译服务",
        "docs": "/docs",
    }


@app.get("/healthz")
async def healthz():
    """内部规定的健康检查端点"""
    health_status = {"msg": "OK"}
    http_status = status.HTTP_200_OK
    return JSONResponse(content=health_status, status_code=http_status)


@app.get("/api/v1/info")
async def service_info():
    """服务信息端点"""
    try:
        info = {
            "name": "AI Translation Service",
            "version": "0.1.0",
            "framework": "FastAPI + Claude Agent SDK",
            "features": [
                "智能翻译策略",
                "多翻译引擎支持",
                "Claude Agent SDK 驱动",
                "高性能异步处理",
                "Apollo 配置中心",
                "Loguru 结构化日志",
            ],
            "status": {
                "running": True,
                "config_loaded": CONFIG_AVAILABLE,
                "uptime": datetime.now().isoformat(),
            },
        }

        if CONFIG_AVAILABLE:
            try:
                # 尝试获取一些配置信息（不暴露敏感信息）
                info["config"] = {
                    "environment": getattr(Config, "application_name", "unknown"),
                    "timezone": getattr(Config, "timezone", "UTC"),
                }
            except Exception as e:
                logger.warning(f"无法获取配置信息: {str(e)}")

        logger.info("服务信息查询成功")
        return info

    except Exception as e:
        logger.error(f"获取服务信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# 导入并注册 API 路由
from .api.v1.router import router as v1_router
app.include_router(v1_router)

# Task API 路由（使用 /ai-api/v1 前缀，与 Go ai-api 保持一致）
from .api.v1.endpoints.task import router as task_router
app.include_router(task_router, prefix="/ai-api/v1")


if __name__ == "__main__":
    logger.info("直接运行模式启动")
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8080, reload=True, log_level="info"
    )
