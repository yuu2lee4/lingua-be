#!/usr/bin/env python3
"""
Lark Sheets 测试脚本

测试并打印所有表格的内容
"""

import asyncio
import logging
import sys
from pathlib import Path

# 设置日志级别，禁用 DEBUG 日志
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpcore").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.clients.lark_client import LarkSheetsClient
from app.config.configuration import Config


async def test_list_all_sheets():
    """测试获取所有工作表信息"""
    print("\n" + "=" * 60)
    print("测试: 获取所有工作表信息")
    print("=" * 60)

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        sheet_info = await client.get_sheet_info(Config.lark_spreadsheet_token)
        sheets = sheet_info.get("sheets", [])

        print(f"\n找到 {len(sheets)} 个工作表:\n")

        for i, sheet in enumerate(sheets, 1):
            sheet_id = sheet.get("sheet_id", "N/A")
            title = sheet.get("title", "N/A")
            index = sheet.get("index", "N/A")
            row_count = sheet.get("grid_properties", {}).get("row_count", "N/A")
            col_count = sheet.get("grid_properties", {}).get("column_count", "N/A")

            print(f"  {i}. {title}")
            print(f"     - sheet_id: {sheet_id}")
            print(f"     - index: {index}")
            print(f"     - 行数: {row_count}, 列数: {col_count}")
            print()

        return sheets


async def test_read_sheet_content(sheet_id: str, sheet_title: str):
    """测试读取单个工作表内容"""
    print("\n" + "-" * 60)
    print(f"读取工作表: {sheet_title} ({sheet_id})")
    print("-" * 60)

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        # 读取为 DataFrame
        df = await client.read_sheet_as_dataframe(
            spreadsheet_token=Config.lark_spreadsheet_token,
            sheet_id=sheet_id,
        )

        if df.empty:
            print("  [空表格]")
            return df

        print(f"\n  表格形状: {df.shape[0]} 行 x {df.shape[1]} 列")
        print(f"  列名: {list(df.columns)}")
        print()

        # 打印前 10 行数据
        print("  前 10 行数据:")
        print("  " + "-" * 50)

        # 使用 tabulate 格式打印
        for idx, row in df.head(10).iterrows():
            print(f"  Row {idx + 1}:")
            for col in df.columns:
                value = row[col]
                # 截断过长的值
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                print(f"    {col}: {value}")
            print()

        # 如果有 status 列，统计各状态数量
        if "status" in df.columns:
            print("  状态统计:")
            status_counts = df["status"].value_counts()
            for status, count in status_counts.items():
                print(f"    - {status}: {count}")
            print()

        return df


async def test_all_sheets():
    """测试所有工作表"""
    print("\n" + "=" * 60)
    print("Lark Sheets 完整测试")
    print("=" * 60)

    print(f"\nSpreadsheet Token: {Config.lark_spreadsheet_token}")
    print(f"App ID: {Config.lark_app_id[:10]}...")

    # 获取所有工作表
    sheets = await test_list_all_sheets()

    if not sheets:
        print("没有找到任何工作表")
        return

    # 逐个读取工作表内容
    for sheet in sheets:
        sheet_id = sheet.get("sheet_id")
        title = sheet.get("title", "Unknown")

        try:
            await test_read_sheet_content(sheet_id, title)
        except Exception as e:
            print(f"\n  读取失败: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


async def test_filter_sheets():
    """测试过滤 title != 'all' 的工作表"""
    print("\n" + "=" * 60)
    print("测试: 过滤 title != 'all' 的工作表")
    print("=" * 60)

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        sheet_info = await client.get_sheet_info(Config.lark_spreadsheet_token)
        sheets = sheet_info.get("sheets", [])

        # 过滤
        filtered = [s for s in sheets if s.get("title", "").lower() != "all"]

        print(f"\n总工作表数: {len(sheets)}")
        print(f"过滤后 (title != 'all'): {len(filtered)}")
        print("\n符合条件的工作表:")

        for sheet in filtered:
            print(f"  - {sheet.get('title')} ({sheet.get('sheet_id')})")

        return filtered


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Lark Sheets 测试脚本")
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅列出所有工作表",
    )
    parser.add_argument(
        "--filter",
        action="store_true",
        help="测试过滤 title != 'all' 的工作表",
    )
    parser.add_argument(
        "--sheet-id",
        type=str,
        help="指定要读取的工作表 ID",
    )
    parser.add_argument(
        "--sheet-title",
        type=str,
        default="Unknown",
        help="工作表标题 (用于显示)",
    )

    args = parser.parse_args()

    if args.list:
        asyncio.run(test_list_all_sheets())
    elif args.filter:
        asyncio.run(test_filter_sheets())
    elif args.sheet_id:
        asyncio.run(test_read_sheet_content(args.sheet_id, args.sheet_title))
    else:
        # 默认测试所有
        asyncio.run(test_all_sheets())


if __name__ == "__main__":
    main()
