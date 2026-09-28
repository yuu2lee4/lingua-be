#!/usr/bin/env python3
"""
测试脚本：创建 job-example 工作表

从 data/en.json 和 data/zh-CN.json 读取待翻译的 key，
创建新工作表 job-example 并写入双源翻译任务数据
"""

import asyncio
import json
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

import pandas as pd

from app.clients.lark_client import LarkSheetsClient
from app.config.configuration import Config


# 默认目标语言列表（移除 zh-CN，因为现在是源语言）
TARGET_LANGUAGES = [
    "zh-TW",  # 繁体中文
    "ja-JP",  # 日语
    "ko-KR",  # 韩语
    "es-ES",  # 西班牙语
    "pt-BR",  # 葡萄牙语
    "vi-VN",  # 越南语
    "fr-FR",  # 法语
    "de-DE",  # 德语
    "ar-SA",  # 阿拉伯语
    "uk-UA",  # 乌克兰语
    "ru-RU",  # 俄语
    "id-ID",  # 印尼语
]

# 默认批次大小
DEFAULT_BATCH_SIZE = 100


def flatten_json(data: dict, parent_key: str = "", sep: str = ".") -> dict[str, str]:
    """
    将嵌套的 JSON 扁平化为 key.subkey.subsubkey -> value 格式

    Args:
        data: 嵌套的 JSON 数据
        parent_key: 父级 key
        sep: 分隔符

    Returns:
        扁平化后的字典
    """
    items = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.update(flatten_json(value, new_key, sep))
        else:
            # 只保留字符串值
            if isinstance(value, str):
                items[new_key] = value
    return items


def load_translation_keys(
    en_json_path: Path,
    zh_json_path: Path,
    count: int = 5,
) -> list[tuple[str, str, str | None]]:
    """
    从英文和中文 JSON 文件加载待翻译的 key

    Args:
        en_json_path: 英文 JSON 文件路径
        zh_json_path: 中文 JSON 文件路径
        count: 要获取的 key 数量

    Returns:
        [(key, en_value, zh_value), ...] 列表
    """
    with open(en_json_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)

    # 扁平化英文 JSON
    en_flat = flatten_json(en_data)

    # 加载中文 JSON（可能不存在）
    zh_flat: dict[str, str] = {}
    if zh_json_path.exists():
        with open(zh_json_path, "r", encoding="utf-8") as f:
            zh_data = json.load(f)
        zh_flat = flatten_json(zh_data)

    # 过滤掉太长的文本（保持简单）
    filtered = [
        (k, v, zh_flat.get(k))
        for k, v in en_flat.items()
        if len(v) < 100 and len(v) > 1
    ]

    # 取前 count 个
    return filtered[:count]


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


async def create_job_example_sheet(
    keys_count: int = 5,
    sheet_title: str = "job-example",
    target_langs: list[str] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
):
    """
    创建 job-example 工作表并写入翻译任务

    Args:
        keys_count: 要写入的 key 数量
        sheet_title: 工作表标题
        target_langs: 目标语言列表
        batch_size: 每批写入的行数
    """
    if target_langs is None:
        target_langs = TARGET_LANGUAGES

    print(f"\n{'=' * 60}")
    print(f"创建工作表 '{sheet_title}' 并写入 {keys_count} 个翻译任务")
    print(f"目标语言: {target_langs}")
    print(f"{'=' * 60}")

    # 读取 en.json 和 zh-CN.json
    en_json_path = project_root / "examples" / "en.json"
    zh_json_path = project_root / "examples" / "zh-CN.json"

    if not en_json_path.exists():
        print(f"错误: 文件不存在 {en_json_path}")
        return False

    keys = load_translation_keys(en_json_path, zh_json_path, keys_count)
    print(f"\n从 en.json + zh-CN.json 读取了 {len(keys)} 个 key:")
    for key, en_value, zh_value in keys:
        zh_display = f" | zh: {zh_value[:30]}..." if zh_value else ""
        print(
            f"  - {key}: {en_value[:50]}{'...' if len(en_value) > 50 else ''}{zh_display}"
        )

    # 构建 DataFrame — 双源列结构
    rows = []
    for i, (key, en_value, zh_value) in enumerate(keys):
        for j, target_lang in enumerate(target_langs):
            row = {
                "file": "en.json",
                "key": key,
                "source_language_1": "en-US",
                "source_text_1": en_value,
                "source_language_2": "zh-CN" if zh_value else "",
                "source_text_2": zh_value or "",
                "target_language": target_lang,
                "target_text": "",
                "status": "new",
                "reviewer": "",
                "mqm": "",
                "review_summary": "",
                "multimodal_review": "",
                "problem_desc": "",
                "updated_at": "",
                "properties": "ready" if i == 0 and j == 0 else "",
            }
            rows.append(row)

    # 按指定列顺序创建 DataFrame
    columns = [
        "file",
        "key",
        "source_language_1",
        "source_text_1",
        "source_language_2",
        "source_text_2",
        "target_language",
        "target_text",
        "status",
        "reviewer",
        "mqm",
        "review_summary",
        "multimodal_review",
        "problem_desc",
        "updated_at",
        "properties",
    ]
    df = pd.DataFrame(rows, columns=columns)
    print(f"\n构建 DataFrame: {df.shape[0]} 行 x {df.shape[1]} 列")
    print(f"列: {list(df.columns)}")

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        # 检查工作表是否已存在
        existing_sheet = await find_sheet_by_title(client, sheet_title)
        if existing_sheet:
            print(f"\n工作表 '{sheet_title}' 已存在，将覆盖内容")
            sheet_id = existing_sheet.get("sheet_id")
        else:
            # 创建新工作表
            print(f"\n创建新工作表 '{sheet_title}'...")
            sheet_id = await client.add_sheet(
                spreadsheet_token=Config.lark_spreadsheet_token,
                title=sheet_title,
            )
            print(f"创建成功: sheet_id={sheet_id}")

        # 分批写入数据
        total_rows = len(df)
        total_batches = (total_rows + batch_size - 1) // batch_size
        print(
            f"\n正在分批写入数据 (共 {total_rows} 行，每批 {batch_size} 行，共 {total_batches} 批)..."
        )

        success = True
        for batch_idx in range(total_batches):
            start_row = batch_idx * batch_size
            end_row = min(start_row + batch_size, total_rows)
            batch_df = df.iloc[start_row:end_row]

            # 第一批包含表头，后续批次不包含
            include_header = batch_idx == 0
            # 计算写入的起始行（飞书行号从1开始，第1行是表头）
            if batch_idx == 0:
                start_row_in_sheet = None  # 从头开始写
            else:
                # 表头占1行，数据从第2行开始，所以第N批数据的起始行是 1 + start_row + 1
                start_row_in_sheet = start_row + 2  # +2 因为: +1 表头, +1 行号从1开始

            print(
                f"  批次 {batch_idx + 1}/{total_batches}: 写入第 {start_row + 1}-{end_row} 行..."
            )

            batch_success = await client.write_dataframe_to_sheet(
                spreadsheet_token=Config.lark_spreadsheet_token,
                sheet_id=sheet_id,
                df=batch_df,
                include_header=include_header,
                start_row=start_row_in_sheet,
            )

            if not batch_success:
                print(f"  批次 {batch_idx + 1} 写入失败!")
                success = False
                break

            print(f"  批次 {batch_idx + 1} 写入成功")

            # 批次间添加短暂延迟，避免 API 限流
            if batch_idx < total_batches - 1:
                await asyncio.sleep(3)

        if success:
            print(f"\n全部 {total_batches} 批次写入成功!")

            # 验证写入结果
            print("\n验证写入结果...")
            df_verify = await client.read_sheet_as_dataframe(
                spreadsheet_token=Config.lark_spreadsheet_token,
                sheet_id=sheet_id,
            )
            print(f"验证: 读取到 {df_verify.shape[0]} 行数据")

            # 显示前几行
            print("\n前 5 行数据:")
            for idx, row in df_verify.head(5).iterrows():
                print(
                    f"  [{idx}] status={row.get('status', '')}, "
                    f"source_text_1={str(row.get('source_text_1', ''))[:30]}..., "
                    f"source_text_2={str(row.get('source_text_2', ''))[:20]}..., "
                    f"target_lang={row.get('target_language', '')}"
                )

            return True
        else:
            print("写入失败!")
            return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="创建 job-example 工作表")
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="要写入的 key 数量 (默认: 5)",
    )
    parser.add_argument(
        "--sheet",
        type=str,
        default="job-example",
        help="工作表标题 (默认: job-example)",
    )
    parser.add_argument(
        "--langs",
        type=str,
        nargs="+",
        default=None,
        help="目标语言列表 (默认: 12 种语言)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"每批写入的行数 (默认: {DEFAULT_BATCH_SIZE})",
    )

    args = parser.parse_args()

    success = asyncio.run(
        create_job_example_sheet(
            keys_count=args.count,
            sheet_title=args.sheet,
            target_langs=args.langs,
            batch_size=args.batch_size,
        )
    )

    if success:
        print("\n操作成功完成!")
    else:
        print("\n操作失败!")
        sys.exit(1)


if __name__ == "__main__":
    main()
