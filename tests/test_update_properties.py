#!/usr/bin/env python3
"""
测试脚本：修改 job-test 表的第一行 properties 为 waiting

用于测试 Lark Sheets 写入功能
"""

import asyncio
import logging
import sys
from pathlib import Path

# 设置日志级别
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpcore").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.clients.lark_client import LarkSheetsClient
from app.config.configuration import Config


async def find_sheet_by_title(client: LarkSheetsClient, title: str) -> dict | None:
    """
    根据标题查找工作表

    Args:
        client: Lark Sheets 客户端
        title: 工作表标题

    Returns:
        工作表信息或 None
    """
    sheet_info = await client.get_sheet_info(Config.lark_spreadsheet_token)
    sheets = sheet_info.get("sheets", [])

    for sheet in sheets:
        if sheet.get("title", "").lower() == title.lower():
            return sheet

    return None


async def update_first_row_properties(sheet_title: str = "job-test", new_value: str = "waiting"):
    """
    更新指定表格第一行的 properties 列

    Args:
        sheet_title: 工作表标题
        new_value: 新的 properties 值
    """
    print(f"\n{'=' * 60}")
    print(f"更新表格 '{sheet_title}' 第一行 properties 为 '{new_value}'")
    print(f"{'=' * 60}")

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        # 查找目标工作表
        sheet = await find_sheet_by_title(client, sheet_title)
        if not sheet:
            print(f"错误: 未找到名为 '{sheet_title}' 的工作表")
            return False

        sheet_id = sheet.get("sheet_id")
        print(f"找到工作表: {sheet_title} (sheet_id: {sheet_id})")

        # 读取表格数据
        df = await client.read_sheet_as_dataframe(
            spreadsheet_token=Config.lark_spreadsheet_token,
            sheet_id=sheet_id,
        )

        if df.empty:
            print("错误: 表格为空")
            return False

        print(f"表格形状: {df.shape[0]} 行 x {df.shape[1]} 列")
        print(f"列名: {list(df.columns)}")

        # 检查 properties 列是否存在
        if "properties" not in df.columns:
            print("错误: 表格缺少 'properties' 列")
            return False

        # 显示当前第一行 properties 值
        current_value = df.iloc[0].get("properties", "")
        print(f"\n当前第一行 properties 值: '{current_value}'")

        # 更新第一行的 properties 值
        df.at[0, "properties"] = new_value
        print(f"更新为: '{new_value}'")

        # 写回表格
        print("\n正在写入表格...")
        success = await client.write_dataframe_to_sheet(
            spreadsheet_token=Config.lark_spreadsheet_token,
            sheet_id=sheet_id,
            df=df,
            include_header=True,
        )

        if success:
            print("写入成功!")

            # 验证写入结果
            print("\n验证写入结果...")
            df_verify = await client.read_sheet_as_dataframe(
                spreadsheet_token=Config.lark_spreadsheet_token,
                sheet_id=sheet_id,
            )
            verified_value = df_verify.iloc[0].get("properties", "")
            print(f"验证: 第一行 properties 值为 '{verified_value}'")

            if verified_value == new_value:
                print("验证通过!")
                return True
            else:
                print(f"验证失败: 期望 '{new_value}', 实际 '{verified_value}'")
                return False
        else:
            print("写入失败!")
            return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="更新 Lark 表格第一行 properties 值")
    parser.add_argument(
        "--sheet",
        type=str,
        default="job-test",
        help="工作表标题 (默认: job-test)",
    )
    parser.add_argument(
        "--value",
        type=str,
        default="waiting",
        help="properties 新值 (默认: waiting)",
    )

    args = parser.parse_args()

    success = asyncio.run(update_first_row_properties(args.sheet, args.value))

    if success:
        print("\n操作成功完成!")
    else:
        print("\n操作失败!")
        sys.exit(1)


if __name__ == "__main__":
    main()
