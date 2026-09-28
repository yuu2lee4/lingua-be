"""
Task Repository

异步任务表 (ai_task) 的数据访问层。
"""

import json
from datetime import datetime
from typing import Any

from app.db.connection import DatabasePool
from app.logger import logger


class TaskRepository:
    """ai_task 表的数据库操作"""

    async def create(
        self,
        task_id: str,
        task_type: int,
        status: int,
        model: str,
        user_group: str,
        params_json: str,
    ) -> int:
        """创建任务，返回自增 ID"""
        sql = """
            INSERT INTO ai_task (task_id, task_type, status, model, user_group, params)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        return await DatabasePool.insert_and_get_id(
            sql, (task_id, task_type, status, model, user_group, params_json)
        )

    async def get_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        """根据 task_id 获取任务"""
        sql = """
            SELECT id, task_id, task_type, status, model, user_group,
                   params, output, error_message, finished_at, created_at, updated_at
            FROM ai_task
            WHERE task_id = %s AND deleted_at = '1970-01-01 00:00:00'
        """
        return await DatabasePool.fetch_one(sql, (task_id,))

    async def get_by_task_ids(self, task_ids: list[str]) -> list[dict[str, Any]]:
        """根据多个 task_id 批量获取任务"""
        if not task_ids:
            return []
        placeholders = ", ".join(["%s"] * len(task_ids))
        sql = f"""
            SELECT id, task_id, task_type, status, model, user_group,
                   params, output, error_message, finished_at, created_at, updated_at
            FROM ai_task
            WHERE task_id IN ({placeholders}) AND deleted_at = '1970-01-01 00:00:00'
        """
        return await DatabasePool.fetch_all(sql, tuple(task_ids))

    async def update_status(self, task_id: str, status: int) -> None:
        """更新任务状态，FINISH(4)/ERROR(5) 时同时设置 finished_at"""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if status in (4, 5):
            sql = """
                UPDATE ai_task SET status = %s, updated_at = %s, finished_at = %s
                WHERE task_id = %s AND deleted_at = '1970-01-01 00:00:00'
            """
            await DatabasePool.execute(sql, (status, now, now, task_id))
        else:
            sql = """
                UPDATE ai_task SET status = %s, updated_at = %s
                WHERE task_id = %s AND deleted_at = '1970-01-01 00:00:00'
            """
            await DatabasePool.execute(sql, (status, now, task_id))

    async def set_output(self, task_id: str, output_json: str) -> None:
        """设置任务输出"""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            UPDATE ai_task SET output = %s, updated_at = %s
            WHERE task_id = %s AND deleted_at = '1970-01-01 00:00:00'
        """
        await DatabasePool.execute(sql, (output_json, now, task_id))

    async def set_error(self, task_id: str, error_msg: str) -> None:
        """设置任务错误：error_message + status=ERROR(5) + finished_at"""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            UPDATE ai_task
            SET error_message = %s, status = 5, finished_at = %s, updated_at = %s
            WHERE task_id = %s AND deleted_at = '1970-01-01 00:00:00'
        """
        await DatabasePool.execute(sql, (error_msg, now, now, task_id))

    async def list_pending(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """获取未完成任务（status IN 0,1,2,3），按创建时间升序"""
        sql = """
            SELECT id, task_id, task_type, status, model, user_group,
                   params, output, error_message, finished_at, created_at, updated_at
            FROM ai_task
            WHERE status IN (0, 1, 2, 3) AND deleted_at = '1970-01-01 00:00:00'
            ORDER BY created_at ASC
            LIMIT %s OFFSET %s
        """
        return await DatabasePool.fetch_all(sql, (limit, offset))


# 全局单例
task_repository = TaskRepository()
