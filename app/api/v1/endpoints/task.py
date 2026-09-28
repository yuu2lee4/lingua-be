"""
Task API Endpoints

异步任务 API 端点，保持与 Go ai-api 相同的接口。
路由注册在 /ai-api/v1/task 前缀下。
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.exceptions import InvalidTaskParamsError, TaskNotFoundError
from app.logger import logger
from app.schemas.task import (
    BatchGetTaskRequest,
    BatchGetTaskResponse,
    CreateTaskRequest,
    CreateTaskResponse,
)
from app.services.task_service import task_service


def _get_expected_token() -> str:
    """从 Apollo 配置获取预期的 bearer token"""
    try:
        from app.config.configuration import Config

        return getattr(Config, "task_api_bearer_token", "") or ""
    except Exception:
        return ""


async def verify_bearer_token(request: Request) -> None:
    """验证 Bearer Token"""
    expected = _get_expected_token()
    if not expected:
        # 未配置 token 则跳过鉴权
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or invalid Authorization header")

    token = auth_header[7:]  # len("Bearer ") == 7
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid bearer token")


router = APIRouter(prefix="/task", tags=["task"], dependencies=[Depends(verify_bearer_token)])


@router.post("", response_model=CreateTaskResponse)
async def create_task(request: CreateTaskRequest) -> CreateTaskResponse:
    """创建异步 AI 任务"""
    try:
        return await task_service.create_task(request)
    except InvalidTaskParamsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[create_task] 创建任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal server error")


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    """获取任务状态和结果"""
    try:
        resp = await task_service.get_task(task_id)
        return resp.to_dict()
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    except Exception as e:
        logger.error(f"[get_task] 获取任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal server error")


@router.post("/batch", response_model=BatchGetTaskResponse)
async def batch_get_tasks(request: BatchGetTaskRequest) -> BatchGetTaskResponse:
    """批量获取多个任务的状态和结果"""
    try:
        return await task_service.batch_get_tasks(request.task_ids)
    except Exception as e:
        logger.error(f"[batch_get_tasks] 批量获取任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal server error")
