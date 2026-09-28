"""
API v1 路由聚合
"""

from fastapi import APIRouter

from .endpoints.translation import router as translation_router
from .endpoints.glossary import router as glossary_router
from .endpoints.visual_review import router as visual_review_router


# 创建 v1 路由器
router = APIRouter(prefix="/api/v1")

# 包含各模块路由
router.include_router(translation_router)
router.include_router(glossary_router)
router.include_router(visual_review_router)
