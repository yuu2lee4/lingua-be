#!/usr/bin/env python3
"""
手动测试脚本：Lark 电子表格翻译任务

直接触发 XXL 任务，无需连接 XXL-JOB 服务
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.logger import logger  # noqa: E402


async def test_sync_lark_translations():
    """测试翻译任务"""
    logger.info("=" * 60)
    logger.info("[测试] 开始执行翻译任务 (sync_lark_translations)")
    logger.info("=" * 60)

    # 导入任务函数
    from xxl_lark_translation import _process_new_translations

    try:
        result = await _process_new_translations()
        logger.info(
            f"[测试] 翻译任务完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        if result.errors:
            logger.warning(f"[测试] 错误列表: {result.errors}")
        return result
    except Exception as e:
        logger.error(f"[测试] 翻译任务失败: {e}")
        raise


async def test_sync_lark_glossary():
    """测试术语提取任务"""
    logger.info("=" * 60)
    logger.info("[测试] 开始执行术语提取任务 (sync_lark_glossary)")
    logger.info("=" * 60)

    # 导入任务函数
    from xxl_lark_translation import _process_reviewed_translations

    try:
        result = await _process_reviewed_translations()
        logger.info(
            f"[测试] 术语提取任务完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        if result.errors:
            logger.warning(f"[测试] 错误列表: {result.errors}")
        return result
    except Exception as e:
        logger.error(f"[测试] 术语提取任务失败: {e}")
        raise


async def test_sync_lark_glossary_tables():
    """测试术语库表同步任务"""
    logger.info("=" * 60)
    logger.info("[测试] 开始执行术语库表同步任务 (sync_lark_glossary_tables)")
    logger.info("=" * 60)

    from xxl_lark_translation import _sync_glossary_tables

    try:
        result = await _sync_glossary_tables()
        logger.info(
            f"[测试] 术语库同步完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        if result.errors:
            logger.warning(f"[测试] 错误列表: {result.errors}")
        return result
    except Exception as e:
        logger.error(f"[测试] 术语库同步失败: {e}")
        raise


async def test_get_sheets():
    """测试获取表格列表"""
    logger.info("=" * 60)
    logger.info("[测试] 获取 Lark 电子表格列表")
    logger.info("=" * 60)

    from app.clients.lark_client import LarkSheetsClient
    from app.config.configuration import Config

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        sheet_info = await client.get_sheet_info(Config.lark_spreadsheet_token)
        sheets = sheet_info.get("sheets", [])

        logger.info(f"[测试] 获取到 {len(sheets)} 个工作表:")
        for i, sheet in enumerate(sheets):
            logger.info(
                f"  [{i + 1}] sheet_id={sheet.get('sheet_id')}, "
                f"title={sheet.get('title')}"
            )

        return sheets


async def test_read_sheet(sheet_id: str | None = None):
    """测试读取单个表格内容"""
    from app.clients.lark_client import LarkSheetsClient
    from app.config.configuration import Config

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        # 如果没有指定 sheet_id，获取第一个非 "all" 的表格
        if not sheet_id:
            sheet_info = await client.get_sheet_info(Config.lark_spreadsheet_token)
            sheets = sheet_info.get("sheets", [])
            for sheet in sheets:
                if sheet.get("title", "").lower() != "all":
                    sheet_id = sheet.get("sheet_id")
                    logger.info(f"[测试] 使用表格: {sheet.get('title')} ({sheet_id})")
                    break

        if not sheet_id:
            logger.warning("[测试] 没有找到可用的表格")
            return None

        logger.info("=" * 60)
        logger.info(f"[测试] 读取表格内容: {sheet_id}")
        logger.info("=" * 60)

        df = await client.read_sheet_as_dataframe(
            spreadsheet_token=Config.lark_spreadsheet_token,
            sheet_id=sheet_id,
        )

        logger.info(f"[测试] DataFrame shape: {df.shape}")
        logger.info(f"[测试] 列名: {df.columns.tolist()}")

        if not df.empty:
            logger.info("[测试] 前 5 行数据:")
            print(df.head().to_string())

        return df


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="手动测试 Lark 翻译任务")
    parser.add_argument(
        "task",
        choices=["translate", "glossary", "glossary_tables", "sheets", "read", "all"],
        help=(
            "要执行的任务: translate=翻译, glossary=术语提取, "
            "glossary_tables=术语库同步, sheets=列出表格, read=读取表格, all=全部"
        ),
    )
    parser.add_argument(
        "--sheet-id",
        type=str,
        default=None,
        help="指定要读取的 sheet_id (仅用于 read 任务)",
    )

    args = parser.parse_args()

    async def run_tasks():
        if args.task == "translate":
            await test_sync_lark_translations()
        elif args.task == "glossary":
            await test_sync_lark_glossary()
        elif args.task == "glossary_tables":
            await test_sync_lark_glossary_tables()
        elif args.task == "sheets":
            await test_get_sheets()
        elif args.task == "read":
            await test_read_sheet(args.sheet_id)
        elif args.task == "all":
            await test_get_sheets()
            await test_sync_lark_translations()
            await test_sync_lark_glossary()
            await test_sync_lark_glossary_tables()

    asyncio.run(run_tasks())


if __name__ == "__main__":
    main()
