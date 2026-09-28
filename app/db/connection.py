"""
MySQL 异步连接池

使用 aiomysql 实现的数据库连接池管理
"""

from typing import Any
from contextlib import asynccontextmanager

import aiomysql

from app.logger import logger
from app.core.exceptions import DatabaseConnectionError, DatabaseQueryError


class DatabasePool:
    """MySQL 异步连接池管理器"""

    _pool: aiomysql.Pool | None = None
    _initialized: bool = False

    @classmethod
    async def initialize(
        cls,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "ai_translation",
        pool_size: int = 10,
        pool_recycle: int = 3600,
    ) -> None:
        """
        初始化数据库连接池

        Args:
            host: MySQL 主机地址
            port: MySQL 端口
            user: 用户名
            password: 密码
            database: 数据库名
            pool_size: 连接池大小
            pool_recycle: 连接回收时间（秒）
        """
        if cls._initialized:
            logger.warning("[DatabasePool.initialize] 连接池已初始化，跳过")
            return

        try:
            cls._pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                db=database,
                minsize=1,
                maxsize=pool_size,
                pool_recycle=pool_recycle,
                autocommit=True,
                charset="utf8mb4",
                cursorclass=aiomysql.DictCursor,
            )
            cls._initialized = True
            logger.info(
                f"[DatabasePool.initialize] 连接池初始化成功: {host}:{port}/{database}"
            )
        except Exception as e:
            logger.error(f"[DatabasePool.initialize] 连接池初始化失败: {e}")
            raise DatabaseConnectionError(str(e))

    @classmethod
    async def close(cls) -> None:
        """关闭连接池"""
        if cls._pool:
            cls._pool.close()
            await cls._pool.wait_closed()
            cls._pool = None
            cls._initialized = False
            logger.info("[DatabasePool.close] 连接池已关闭")

    @classmethod
    def is_initialized(cls) -> bool:
        """检查连接池是否已初始化"""
        return cls._initialized and cls._pool is not None

    @classmethod
    @asynccontextmanager
    async def acquire(cls):
        """
        获取数据库连接

        用法:
            async with DatabasePool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT * FROM table")
        """
        if not cls._initialized or cls._pool is None:
            raise DatabaseConnectionError("数据库连接池未初始化")

        try:
            async with cls._pool.acquire() as conn:
                yield conn
        except Exception as e:
            logger.error(f"[DatabasePool.acquire] 获取连接失败: {e}")
            raise DatabaseConnectionError(str(e))

    @classmethod
    async def execute(
        cls,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> int:
        """
        执行 SQL 语句（INSERT/UPDATE/DELETE）

        Args:
            query: SQL 语句
            params: 参数元组

        Returns:
            影响的行数
        """
        async with cls.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    return cursor.rowcount
            except Exception as e:
                logger.error(f"[DatabasePool.execute] 执行失败: {e}, SQL: {query}")
                raise DatabaseQueryError(query, str(e))

    @classmethod
    async def execute_many(
        cls,
        query: str,
        params_list: list[tuple[Any, ...]],
    ) -> int:
        """
        批量执行 SQL 语句

        Args:
            query: SQL 语句
            params_list: 参数列表

        Returns:
            影响的行数
        """
        async with cls.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.executemany(query, params_list)
                    return cursor.rowcount
            except Exception as e:
                logger.error(f"[DatabasePool.execute_many] 执行失败: {e}, SQL: {query}")
                raise DatabaseQueryError(query, str(e))

    @classmethod
    async def fetch_one(
        cls,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> dict[str, Any] | None:
        """
        查询单条记录

        Args:
            query: SQL 语句
            params: 参数元组

        Returns:
            字典形式的记录，或 None
        """
        async with cls.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    return await cursor.fetchone()
            except Exception as e:
                logger.error(f"[DatabasePool.fetch_one] 查询失败: {e}, SQL: {query}")
                raise DatabaseQueryError(query, str(e))

    @classmethod
    async def fetch_all(
        cls,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """
        查询多条记录

        Args:
            query: SQL 语句
            params: 参数元组

        Returns:
            字典列表
        """
        async with cls.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    result = await cursor.fetchall()
                    return list(result) if result else []
            except Exception as e:
                logger.error(f"[DatabasePool.fetch_all] 查询失败: {e}, SQL: {query}")
                raise DatabaseQueryError(query, str(e))

    @classmethod
    async def insert_and_get_id(
        cls,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> int:
        """
        执行 INSERT 并返回自增 ID

        Args:
            query: INSERT 语句
            params: 参数元组

        Returns:
            自增 ID
        """
        async with cls.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    return cursor.lastrowid
            except Exception as e:
                logger.error(
                    f"[DatabasePool.insert_and_get_id] 执行失败: {e}, SQL: {query}"
                )
                raise DatabaseQueryError(query, str(e))


def get_db_pool() -> DatabasePool:
    """获取数据库连接池实例"""
    return DatabasePool
