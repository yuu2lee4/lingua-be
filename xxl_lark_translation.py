#!/usr/bin/env python3
"""
XXL 定时任务：Lark 电子表格翻译处理

任务列表：
- sync_lark_translations: 处理 status="new" 的翻译任务
- sync_lark_glossary: 处理 status="reviewed" 的已审核翻译，提取术语
- sync_lark_glossary_tables: 双向同步术语库表到 Lark
- migrate_glossary_candidates: 将已批准的候选术语迁移到正式术语库

翻译流程优化：
- 将相同 source_text 但不同 target_language 的行合并为一个多语言翻译任务
- 默认批次为 1（逐条翻译），可通过配置调整
"""

import asyncio
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from pyxxl import ExecutorConfig, PyxxlRunner

from app.agents.glossary_extraction_agent import GlossaryExtractionAgent
from app.clients.lark_client import LarkSheetsClient
from app.config.configuration import Config
from app.db.connection import DatabasePool
from app.logger import logger
from app.repositories.glossary_repository import glossary_repository
from app.schemas.glossary_db import GlossaryExtractRequest
from app.schemas.lark_job import LarkJobStatus, LarkSyncResult
from app.schemas.translation import TranslationItem, TranslationRequest
from app.services.glossary_service import glossary_service
from app.services.translation_service import translation_service
from app.utils.glossary_columns import TRANSLATION_COLUMNS


# 默认批次大小（每批处理的 source_text 数量）
DEFAULT_BATCH_SIZE = 1

# 单次任务最大翻译条数
MAX_TRANSLATIONS_PER_RUN = 500

# 调试列名
REVIEW_INPUT_COLUMN = "review_input"

# 是否自动在 Lark 表格新增 review_input 列
AUTO_ADD_REVIEW_INPUT_COLUMN = False

# 数据库初始化标志
_db_initialized = False


@dataclass
class TranslationTask:
    """翻译任务：一个源文本对应多个目标语言"""

    source_text_1: str
    source_language_1: str
    source_text_2: str | None = None
    source_language_2: str | None = None
    # 目标语言到行信息的映射: {target_lang: (row_num, idx)}
    targets: dict[str, tuple[int, int]] = field(default_factory=dict)

    def add_target(self, target_lang: str, row_num: int, idx: int) -> None:
        """添加目标语言"""
        self.targets[target_lang] = (row_num, idx)

    @property
    def target_langs(self) -> list[str]:
        """获取所有目标语言列表"""
        return list(self.targets.keys())

    # 向后兼容属性
    @property
    def source_text(self) -> str:
        return self.source_text_1

    @property
    def source_language(self) -> str:
        return self.source_language_1


# XXL-JOB 配置
executor_config = ExecutorConfig(
    xxl_admin_baseurl=Config.xxl_admin_baseurl,
    executor_app_name=Config.xxl_app_name,
    executor_listen_port=int(Config.xxl_listen_port),
    access_token=Config.xxl_access_token,
    debug=False,
    task_timeout=3600,
)

app = PyxxlRunner(executor_config)

# 任务队列（线程池执行异步任务）
_executor = ThreadPoolExecutor(max_workers=4)
_run_lock = threading.Lock()
_shared_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro):
    """在线程池中运行异步协程"""
    global _shared_loop
    with _run_lock:
        if _shared_loop is None or _shared_loop.is_closed():
            _shared_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_shared_loop)
        return _shared_loop.run_until_complete(coro)


# ============ Glossary Sheet Sync ============

GLOSSARY_SHEET_TITLES = {
    "match": "match_glossary_terms（smartling)",
    "business": "business_glossary_terms（业务）",
    "candidates": "glossary_candidates（人工修正）",
}

MATCH_GLOSSARY_COLUMNS = [
    "term_id",
    "term_en",
    *TRANSLATION_COLUMNS,
    "source",
    "status",
    "created_at",
    "updated_at",
]

BUSINESS_GLOSSARY_COLUMNS = [
    "term_id",
    "term_en",
    "definition",
    "part_of_speech",
    "do_not_translate",
    *TRANSLATION_COLUMNS,
    "source",
    "status",
    "created_at",
    "updated_at",
]

CANDIDATE_GLOSSARY_COLUMNS = [
    "term_id",
    "term_en",
    "definition",
    "part_of_speech",
    "do_not_translate",
    *TRANSLATION_COLUMNS,
    "source",
    "status",
    "migrated_to_match_glossary",
    "migrated_to_business_glossary",
    "created_at",
    "updated_at",
]

MATCH_GLOSSARY_EDITABLE_COLUMNS = [
    "term_id",
    "term_en",
    *TRANSLATION_COLUMNS,
    "source",
    "status",
]

BUSINESS_GLOSSARY_EDITABLE_COLUMNS = [
    "term_id",
    "term_en",
    "definition",
    "part_of_speech",
    "do_not_translate",
    *TRANSLATION_COLUMNS,
    "source",
    "status",
]

CANDIDATE_GLOSSARY_EDITABLE_COLUMNS = [
    "term_id",
    "term_en",
    "definition",
    "part_of_speech",
    "do_not_translate",
    *TRANSLATION_COLUMNS,
    "source",
    "status",
    "migrated_to_match_glossary",
    "migrated_to_business_glossary",
]

BOOL_COLUMNS = {
    "do_not_translate",
    "migrated_to_match_glossary",
    "migrated_to_business_glossary",
}


def _generate_term_id(term_en: str) -> str:
    """生成术语 ID（基于英文术语的 MD5 哈希）"""
    return hashlib.md5(term_en.lower().encode()).hexdigest()[:16]


def _normalize_value(value: object) -> str:
    """标准化比较值（用于行差异判断）"""
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip()


def _parse_bool(value: object) -> int:
    """解析布尔值为 0/1"""
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None or pd.isna(value):
        return 0
    text = str(value).strip().lower()
    return 1 if text in {"1", "true", "yes", "y", "t"} else 0


def _ensure_df_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """确保 DataFrame 包含指定列并按顺序返回"""
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


async def _ensure_sheet_columns(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    sheet_id: str,
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """确保工作表包含指定列（必要时更新表头）"""
    missing = [col for col in columns if col not in df.columns]
    if not missing:
        return df

    for col in missing:
        df[col] = ""

    headers = df.columns.tolist()
    end_col = chr(65 + len(headers) - 1) if len(headers) <= 26 else "Z"
    range_str = f"A1:{end_col}1"
    await client.write_sheet_values(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        values=[headers],
        range_str=range_str,
    )
    logger.info(
        f"[_ensure_sheet_columns] 表格 {sheet_id} 已添加列: {missing}"
    )
    return df


def _format_db_row(row: dict, columns: list[str]) -> dict:
    """格式化数据库行用于写入 Lark"""
    formatted = {}
    for col in columns:
        value = row.get(col)
        if col in BOOL_COLUMNS:
            formatted[col] = _parse_bool(value)
        else:
            formatted[col] = _normalize_value(value)
    return formatted


def _build_df_from_db_rows(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """从数据库行构建 DataFrame"""
    data = [_format_db_row(row, columns) for row in rows]
    return pd.DataFrame(data, columns=columns)


def _pad_dataframe(df: pd.DataFrame, target_rows: int) -> pd.DataFrame:
    """将 DataFrame 填充到指定行数，确保覆盖旧数据"""
    if target_rows <= len(df):
        return df
    padding_rows = target_rows - len(df)
    blank_row = dict.fromkeys(df.columns, "")
    padding = pd.DataFrame([blank_row] * padding_rows, columns=df.columns)
    return pd.concat([df, padding], ignore_index=True)


def _row_differs(lark_row: dict, db_row: dict, columns: list[str]) -> bool:
    """比较 Lark 行与数据库行是否有差异"""
    for col in columns:
        if col in BOOL_COLUMNS:
            if _parse_bool(lark_row.get(col)) != _parse_bool(db_row.get(col)):
                return True
        else:
            if _normalize_value(lark_row.get(col)) != _normalize_value(db_row.get(col)):
                return True
    return False


def _is_empty_row(row: dict) -> bool:
    """判断是否为空行"""
    term_id = _normalize_value(row.get("term_id"))
    term_en = _normalize_value(row.get("term_en"))
    return not term_id and not term_en


async def _ensure_db_initialized():
    """
    确保数据库已初始化

    包括：
    1. 初始化数据库连接池
    2. 初始化两级术语库系统 (Two-Tier Glossary)
       - Level 1: Match Glossary (从 YAML 导入)
       - Level 2: Business AI Glossary (从 JSON 导入)
    3. 预热术语表缓存
    """
    global _db_initialized

    if _db_initialized:
        return

    try:
        # 初始化数据库连接池
        await DatabasePool.initialize(
            host=Config.mysql_host,
            port=Config.mysql_port,
            user=Config.mysql_user,
            password=Config.mysql_password,
            database=Config.mysql_database,
            pool_size=Config.mysql_pool_size,
            pool_recycle=Config.mysql_pool_recycle,
        )
        logger.info("[_ensure_db_initialized] MySQL 连接池初始化成功")

        # ============ Two-Tier Glossary Initialization ============
        from pathlib import Path

        from app.services.match_glossary_service import match_glossary_service

        # Level 1: Initialize Match Glossary from YAML (直接翻译查找)
        yaml_glossary_path = Path(__file__).parent / "examples" / "glossary.yaml"
        match_imported, match_skipped, match_errors = (
            await match_glossary_service.initialize_from_yaml(yaml_glossary_path)
        )
        if match_imported > 0:
            logger.info(
                f"[_ensure_db_initialized] Match Glossary: 已从 YAML 导入 {match_imported} 条术语"
            )
        if match_errors:
            logger.warning(
                f"[_ensure_db_initialized] Match Glossary 初始化存在错误: {match_errors}"
            )

        # Level 2: Initialize Business AI Glossary from JSON (AI 提示词增强)
        business_imported, skipped, errors = (
            await glossary_repository.initialize_from_default_glossary()
        )
        if business_imported > 0:
            logger.info(
                f"[_ensure_db_initialized] Business AI Glossary: 已从 JSON 导入 {business_imported} 条术语"
            )
        if errors:
            logger.warning(
                f"[_ensure_db_initialized] Business AI Glossary 初始化存在错误: {errors}"
            )

        # 预热两级术语表缓存
        await glossary_service.warmup_cache()
        await match_glossary_service.warmup_cache()
        logger.info("[_ensure_db_initialized] 两级术语表缓存预热完成")

        _db_initialized = True

    except Exception as e:
        logger.error(f"[_ensure_db_initialized] 数据库初始化失败: {e}")
        raise


async def _get_translation_sheets(
    client: LarkSheetsClient,
    spreadsheet_token: str,
) -> list[dict]:
    """
    获取所有需要处理的翻译表格

    过滤条件：title != "all"

    Args:
        client: Lark Sheets 客户端
        spreadsheet_token: 电子表格 token

    Returns:
        工作表信息列表 [{"sheet_id": ..., "title": ...}, ...]
    """
    sheet_info = await client.get_sheet_info(spreadsheet_token)
    sheets = sheet_info.get("sheets", [])

    # 过滤掉 title == "all" 的表格
    translation_sheets = [
        {"sheet_id": s.get("sheet_id"), "title": s.get("title")}
        for s in sheets
        if s.get("title", "").lower() != "all"
    ]

    logger.info(
        f"[_get_translation_sheets] 获取到 {len(translation_sheets)} 个翻译表格 "
        f"(总计 {len(sheets)} 个)"
    )

    return translation_sheets


async def _get_or_create_sheet_id(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    title: str,
    index: int = 0,
) -> str:
    """获取或创建指定标题的工作表"""
    sheet_info = await client.get_sheet_info(spreadsheet_token)
    sheets = sheet_info.get("sheets", [])
    for sheet in sheets:
        if sheet.get("title", "").strip().lower() == title.strip().lower():
            return sheet.get("sheet_id")

    return await client.add_sheet(
        spreadsheet_token=spreadsheet_token,
        title=title,
        index=index,
    )


async def _write_glossary_df_to_sheet(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    sheet_id: str,
    df: pd.DataFrame,
    existing_rows: int,
) -> None:
    """写入术语表数据到 Lark（覆盖写）"""
    df_to_write = _pad_dataframe(df, existing_rows)
    await client.write_dataframe_to_sheet(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        df=df_to_write,
        include_header=True,
        start_row=1,
    )


async def _fetch_match_glossary_rows() -> list[dict]:
    columns = ", ".join(MATCH_GLOSSARY_COLUMNS)
    query = f"SELECT {columns} FROM match_glossary_terms ORDER BY term_en"
    return await DatabasePool.fetch_all(query)


async def _fetch_business_glossary_rows() -> list[dict]:
    columns = ", ".join(BUSINESS_GLOSSARY_COLUMNS)
    query = (
        f"SELECT {columns} FROM business_glossary_terms "
        "WHERE status != 'deleted' ORDER BY term_en"
    )
    return await DatabasePool.fetch_all(query)


async def _fetch_candidate_rows() -> list[dict]:
    columns = ", ".join(CANDIDATE_GLOSSARY_COLUMNS)
    query = f"SELECT {columns} FROM glossary_candidates ORDER BY updated_at DESC"
    return await DatabasePool.fetch_all(query)


async def _upsert_match_glossary_row(row: dict) -> None:
    columns = [
        "term_id",
        "term_en",
        *TRANSLATION_COLUMNS,
        "source",
        "status",
    ]
    values = []
    for col in columns:
        if col in BOOL_COLUMNS:
            values.append(_parse_bool(row.get(col)))
        else:
            values.append(_normalize_value(row.get(col)))
    update_cols = [c for c in columns if c != "term_id"]
    update_clause = ", ".join([f"{c} = VALUES({c})" for c in update_cols])
    placeholders = ", ".join(["%s"] * len(columns))
    query = (
        f"INSERT INTO match_glossary_terms ({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    )
    await DatabasePool.execute(query, tuple(values))


async def _upsert_business_glossary_row(row: dict) -> None:
    columns = [
        "term_id",
        "term_en",
        "definition",
        "part_of_speech",
        "do_not_translate",
        *TRANSLATION_COLUMNS,
        "source",
        "status",
    ]
    values = []
    for col in columns:
        if col in BOOL_COLUMNS:
            values.append(_parse_bool(row.get(col)))
        else:
            values.append(_normalize_value(row.get(col)))
    update_cols = [c for c in columns if c != "term_id"]
    update_clause = ", ".join([f"{c} = VALUES({c})" for c in update_cols])
    placeholders = ", ".join(["%s"] * len(columns))
    query = (
        f"INSERT INTO business_glossary_terms ({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    )
    await DatabasePool.execute(query, tuple(values))


async def _upsert_candidate_row(row: dict) -> None:
    columns = [
        "term_id",
        "term_en",
        "definition",
        "part_of_speech",
        "do_not_translate",
        *TRANSLATION_COLUMNS,
        "source",
        "status",
        "migrated_to_match_glossary",
        "migrated_to_business_glossary",
    ]
    values = []
    for col in columns:
        if col in BOOL_COLUMNS or col.startswith("migrated_"):
            values.append(_parse_bool(row.get(col)))
        else:
            values.append(_normalize_value(row.get(col)))
    update_cols = [c for c in columns if c != "term_id"]
    update_clause = ", ".join([f"{c} = VALUES({c})" for c in update_cols])
    placeholders = ", ".join(["%s"] * len(columns))
    query = (
        f"INSERT INTO glossary_candidates ({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    )
    await DatabasePool.execute(query, tuple(values))


def _check_sheet_ready(df: pd.DataFrame, sheet_title: str) -> bool:
    """
    检查表格是否准备好处理

    根据第一行的 properties 列判断:
    - "ready": 可以处理，返回 True
    - "waiting": 跳过，返回 False
    - 空值: 跳过并警告，返回 False

    Args:
        df: 表格 DataFrame
        sheet_title: 表格标题（用于日志）

    Returns:
        是否可以处理
    """
    # 检查 properties 列是否存在
    if "properties" not in df.columns:
        logger.warning(
            f"[_check_sheet_ready] 表格 {sheet_title} 缺少 properties 列，跳过"
        )
        return False

    # 获取第一行的 properties 值
    if df.empty:
        logger.warning(f"[_check_sheet_ready] 表格 {sheet_title} 为空，跳过")
        return False

    first_row_properties = str(df.iloc[0].get("properties", "")).strip().lower()

    if first_row_properties == "ready":
        logger.info(f"[_check_sheet_ready] 表格 {sheet_title} 状态为 ready，开始处理")
        return True
    elif first_row_properties == "waiting":
        logger.info(f"[_check_sheet_ready] 表格 {sheet_title} 状态为 waiting，跳过")
        return False
    else:
        # 空值或其他值
        logger.warning(
            f"[_check_sheet_ready] 表格 {sheet_title} 第一行 properties 为空或无效值 "
            f"('{first_row_properties}')，跳过"
        )
        return False


async def _sync_glossary_table(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    sheet_title: str,
    columns: list[str],
    editable_columns: list[str],
    fetch_rows_fn,
    upsert_fn,
    default_source: str,
    default_status: str,
) -> LarkSyncResult:
    """
    同步单个术语表：
    1. 读取 Lark 表格
    2. 若存在差异，更新数据库
    3. 导出最新数据库内容回写 Lark
    """
    result = LarkSyncResult()

    sheet_id = await _get_or_create_sheet_id(
        client=client,
        spreadsheet_token=spreadsheet_token,
        title=sheet_title,
    )

    lark_df = await client.read_sheet_as_dataframe(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
    )
    existing_rows = len(lark_df)

    if lark_df.empty:
        db_rows = await fetch_rows_fn()
        df = _build_df_from_db_rows(db_rows, columns)
        await _write_glossary_df_to_sheet(
            client=client,
            spreadsheet_token=spreadsheet_token,
            sheet_id=sheet_id,
            df=df,
            existing_rows=existing_rows,
        )
        result.total_records = len(db_rows)
        return result

    lark_df = _ensure_df_columns(lark_df, columns)
    lark_rows = lark_df.to_dict(orient="records")
    result.total_records = len(lark_rows)

    db_rows = await fetch_rows_fn()
    db_map = {row.get("term_id"): row for row in db_rows if row.get("term_id")}

    for row in lark_rows:
        result.processed += 1
        if _is_empty_row(row):
            result.skipped += 1
            continue

        term_en = _normalize_value(row.get("term_en"))
        if not term_en:
            result.skipped += 1
            continue

        term_id = _normalize_value(row.get("term_id"))
        if not term_id:
            term_id = _generate_term_id(term_en)
            row["term_id"] = term_id

        if not _normalize_value(row.get("source")):
            row["source"] = default_source
        if not _normalize_value(row.get("status")):
            row["status"] = default_status

        if term_id not in db_map or _row_differs(
            row, db_map[term_id], editable_columns
        ):
            try:
                await upsert_fn(row)
                result.success += 1
            except Exception as e:
                result.failed += 1
                error_msg = f"{sheet_title} term_id={term_id} 同步失败: {e}"
                result.errors.append(error_msg)
                logger.error(f"[_sync_glossary_table] {error_msg}")
        else:
            result.skipped += 1

    # 回写最新数据到 Lark
    db_rows = await fetch_rows_fn()
    df = _build_df_from_db_rows(db_rows, columns)
    await _write_glossary_df_to_sheet(
        client=client,
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        df=df,
        existing_rows=existing_rows,
    )

    return result


async def _sync_glossary_tables() -> LarkSyncResult:
    """
    同步三张术语表到 Lark，并将 Lark 修改同步回数据库
    扫描所有配置的 spreadsheet_token
    """
    await _ensure_db_initialized()

    total_result = LarkSyncResult()

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        for spreadsheet_token in Config.lark_spreadsheet_tokens:
            logger.info(
                f"[_sync_glossary_tables] 处理电子表格: {spreadsheet_token}"
            )

            # Match Glossary
            match_result = await _sync_glossary_table(
                client=client,
                spreadsheet_token=spreadsheet_token,
                sheet_title=GLOSSARY_SHEET_TITLES["match"],
                columns=MATCH_GLOSSARY_COLUMNS,
                editable_columns=MATCH_GLOSSARY_EDITABLE_COLUMNS,
                fetch_rows_fn=_fetch_match_glossary_rows,
                upsert_fn=_upsert_match_glossary_row,
                default_source="manual",
                default_status="active",
            )

            # Business Glossary
            business_result = await _sync_glossary_table(
                client=client,
                spreadsheet_token=spreadsheet_token,
                sheet_title=GLOSSARY_SHEET_TITLES["business"],
                columns=BUSINESS_GLOSSARY_COLUMNS,
                editable_columns=BUSINESS_GLOSSARY_EDITABLE_COLUMNS,
                fetch_rows_fn=_fetch_business_glossary_rows,
                upsert_fn=_upsert_business_glossary_row,
                default_source="manual",
                default_status="active",
            )

            # Candidate Glossary
            candidate_result = await _sync_glossary_table(
                client=client,
                spreadsheet_token=spreadsheet_token,
                sheet_title=GLOSSARY_SHEET_TITLES["candidates"],
                columns=CANDIDATE_GLOSSARY_COLUMNS,
                editable_columns=CANDIDATE_GLOSSARY_EDITABLE_COLUMNS,
                fetch_rows_fn=_fetch_candidate_rows,
                upsert_fn=_upsert_candidate_row,
                default_source="ai_extracted",
                default_status="pending",
            )

            for result in [match_result, business_result, candidate_result]:
                total_result.total_records += result.total_records
                total_result.processed += result.processed
                total_result.success += result.success
                total_result.failed += result.failed
                total_result.skipped += result.skipped
                total_result.errors.extend(result.errors)

    # 刷新缓存
    try:
        from app.services.match_glossary_service import match_glossary_service

        match_glossary_service.invalidate_cache()
        glossary_service.invalidate_db_cache()
    except Exception as e:
        logger.warning(f"[_sync_glossary_tables] 刷新缓存失败: {e}")

    return total_result


def _group_records_by_source_text(
    new_records: pd.DataFrame,
) -> dict[str, TranslationTask]:
    """
    将记录按 source_text 分组

    相同 source_text 但不同 target_language 的行会被合并为一个翻译任务
    自动检测新旧列格式：source_text_1（新）vs source_text（旧）

    Args:
        new_records: status="new" 的记录 DataFrame

    Returns:
        source_text -> TranslationTask 的映射
    """
    tasks: dict[str, TranslationTask] = {}

    # 自动检测列格式
    use_new_format = "source_text_1" in new_records.columns

    for idx, row in new_records.iterrows():
        row_num = idx + 2  # DataFrame 索引从 0 开始，表格行号从 1 开始，加上表头

        if use_new_format:
            source_text_1 = str(row.get("source_text_1", "")).strip()
            source_language_1 = (
                str(row.get("source_language_1", "en-US")).strip() or "en-US"
            )
            raw_text_2 = row.get("source_text_2", "")
            raw_lang_2 = row.get("source_language_2", "")
            source_text_2 = (
                None if pd.isna(raw_text_2) else (str(raw_text_2).strip() or None)
            )
            source_language_2 = (
                None if pd.isna(raw_lang_2) else (str(raw_lang_2).strip() or None)
            )
        else:
            source_text_1 = str(row.get("source_text", "")).strip()
            source_language_1 = (
                str(row.get("source_language", "en-US")).strip() or "en-US"
            )
            source_text_2 = None
            source_language_2 = None

        target_language = str(row.get("target_language", "")).strip()

        # 跳过无效记录（至少需要一个源文本 + 目标语言）
        if (not source_text_1 and not source_text_2) or not target_language:
            continue

        # 分组键包含双源信息
        task_key = f"{source_text_1}|||{source_language_1}|||{source_text_2 or ''}"

        if task_key not in tasks:
            tasks[task_key] = TranslationTask(
                source_text_1=source_text_1,
                source_language_1=source_language_1,
                source_text_2=source_text_2,
                source_language_2=source_language_2,
            )

        tasks[task_key].add_target(target_language, row_num, idx)

    return tasks


def _build_review_input_cell_value(translation_item: TranslationItem) -> str | None:
    """
    构建写入 Lark 的 review_input 内容

    优先写入质量评审模型输入；若为空，回退为术语匹配摘要，便于排查。
    """
    review_input = (translation_item.review_input or "").strip()
    if review_input:
        return review_input

    found_terms = translation_item.glossary_terms_found or []
    matched_terms = translation_item.glossary_terms_matched or []
    if not found_terms and not matched_terms:
        return None

    found_text = ", ".join(found_terms) if found_terms else "none"
    matched_text = ", ".join(matched_terms) if matched_terms else "none"
    return (
        "Review input unavailable; fallback term matching snapshot:\n"
        f"found_terms: {found_text}\n"
        f"matched_terms: {matched_text}"
    )


async def _execute_translation_task(
    task: TranslationTask,
) -> dict[str, tuple[str | None, int | None, str | None, str | None, str | None]]:
    """
    执行单个翻译任务（一个 source_text 翻译为多个目标语言）

    Args:
        task: 翻译任务

    Returns:
        target_lang -> (translated_text, quality_score, review_summary, review_input, error_msg) 的映射
    """
    results: dict[
        str, tuple[str | None, int | None, str | None, str | None, str | None]
    ] = {}

    try:
        # 构建多语言翻译请求
        request = TranslationRequest(
            source_text_1=task.source_text_1,
            source_lang_1=task.source_language_1,
            source_text_2=task.source_text_2,
            source_lang_2=task.source_language_2,
            target_langs=task.target_langs,
        )

        logger.info(
            f"[_execute_translation_task] 翻译任务: "
            f"source_text_1={task.source_text_1[:50]}..., "
            f"has_source_text_2={task.source_text_2 is not None}, "
            f"target_langs={task.target_langs}"
        )

        # 同步执行翻译
        response = await translation_service.translate_sync(request)

        # 提取各语言的翻译结果（包含质量评分和评审摘要）
        for translation_item in response.translations:
            target_lang = translation_item.target_lang
            translated_text = translation_item.translated_text
            quality_score = translation_item.quality_score
            review_summary = translation_item.quality_feedback
            review_input = _build_review_input_cell_value(translation_item)
            results[target_lang] = (
                translated_text,
                quality_score,
                review_summary,
                review_input,
                None,
            )

        # 检查是否有缺失的语言
        for target_lang in task.target_langs:
            if target_lang not in results:
                results[target_lang] = (
                    None,
                    None,
                    None,
                    None,
                    "翻译响应中缺少该语言",
                )

    except Exception as e:
        error_msg = str(e)[:500]
        logger.error(f"[_execute_translation_task] 翻译失败: {error_msg}")
        # 所有目标语言都标记为失败
        for target_lang in task.target_langs:
            results[target_lang] = (None, None, None, None, error_msg)

    return results


async def _process_sheet_translations(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    sheet_id: str,
    sheet_title: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> LarkSyncResult:
    """
    处理单个表格的翻译任务

    优化流程：将相同 source_text 但不同 target_language 的行合并为一个多语言翻译任务

    Args:
        client: Lark Sheets 客户端
        spreadsheet_token: 电子表格 token
        sheet_id: 工作表 ID
        sheet_title: 工作表标题
        batch_size: 每批处理的 source_text 数量（默认 1）

    Returns:
        处理结果
    """
    result = LarkSyncResult()

    logger.info(f"[_process_sheet_translations] 处理表格: {sheet_title} ({sheet_id})")

    # 读取表格数据为 DataFrame
    df = await client.read_sheet_as_dataframe(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
    )

    if df.empty:
        logger.info(f"[_process_sheet_translations] 表格 {sheet_title} 为空")
        return result

    # 检查表格是否准备好处理
    if not _check_sheet_ready(df, sheet_title):
        return result

    # 检查必要的列是否存在（自动适配新旧格式）
    if "source_text_1" in df.columns:
        required_columns = ["status", "source_text_1", "target_language"]
    else:
        required_columns = ["status", "source_text", "target_language"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.warning(
            f"[_process_sheet_translations] 表格 {sheet_title} 缺少必要列: {missing_columns}"
        )
        return result

    # 可选：自动补充 review_input 调试列
    if AUTO_ADD_REVIEW_INPUT_COLUMN:
        df = await _ensure_sheet_columns(
            client=client,
            spreadsheet_token=spreadsheet_token,
            sheet_id=sheet_id,
            df=df,
            columns=[REVIEW_INPUT_COLUMN],
        )
    elif REVIEW_INPUT_COLUMN not in df.columns:
        logger.info(
            "[_process_sheet_translations] "
            f"已关闭自动加列，且表格 {sheet_title} 无 {REVIEW_INPUT_COLUMN} 列"
        )

    # 过滤 status="new" 的记录
    new_records = df[df["status"] == LarkJobStatus.NEW.value].copy()
    result.total_records = len(new_records)

    logger.info(
        f"[_process_sheet_translations] 表格 {sheet_title} 有 {len(new_records)} 条待翻译记录"
    )

    if new_records.empty:
        return result

    # 限制单次任务最大翻译条数
    if len(new_records) > MAX_TRANSLATIONS_PER_RUN:
        logger.info(
            f"[_process_sheet_translations] 记录数超过上限 {MAX_TRANSLATIONS_PER_RUN}，"
            f"本次只处理前 {MAX_TRANSLATIONS_PER_RUN} 条"
        )
        new_records = new_records.head(MAX_TRANSLATIONS_PER_RUN)

    # 记录要处理的行索引，用于后续只写入这部分数据
    processed_indices = set(new_records.index.tolist())

    # 按 source_text 分组
    tasks = _group_records_by_source_text(new_records)
    logger.info(
        f"[_process_sheet_translations] 合并为 {len(tasks)} 个翻译任务 "
        f"(batch_size={batch_size})"
    )

    # 统计跳过的无效记录
    valid_row_count = sum(len(t.targets) for t in tasks.values())
    result.skipped = result.total_records - valid_row_count
    if result.skipped > 0:
        logger.warning(
            f"[_process_sheet_translations] 跳过 {result.skipped} 条无效记录"
        )

    # 准备更新数据
    updates = []

    # 按批次处理翻译任务
    task_list = list(tasks.values())
    total_tasks = len(task_list)
    completed_tasks = 0

    for batch_idx in range(0, len(task_list), batch_size):
        batch = task_list[batch_idx : batch_idx + batch_size]

        # 并行执行当前批次的翻译任务
        batch_results = await asyncio.gather(
            *[_execute_translation_task(task) for task in batch],
            return_exceptions=True,
        )

        # 处理结果并生成更新
        for task, task_result in zip(batch, batch_results, strict=True):
            completed_tasks += 1
            task_success = 0
            task_failed = 0

            if isinstance(task_result, Exception):
                # 任务整体异常
                error_msg = str(task_result)[:500]
                for _target_lang, (row_num, idx) in task.targets.items():
                    result.processed += 1
                    result.failed += 1
                    task_failed += 1
                    result.errors.append(f"row={row_num} 翻译失败: {error_msg}")
                    updates.append(
                        {
                            "row": row_num,
                            "idx": idx,
                            "status": LarkJobStatus.PROBLEM.value,
                            "problem_desc": error_msg,
                        }
                    )
            else:
                # 处理每个目标语言的结果
                for target_lang, (row_num, idx) in task.targets.items():
                    result.processed += 1
                    (
                        translated_text,
                        quality_score,
                        review_summary,
                        review_input,
                        error_msg,
                    ) = task_result.get(
                        target_lang,
                        (None, None, None, None, "翻译结果缺失"),
                    )

                    if translated_text is not None:
                        # 翻译成功
                        update_data = {
                            "row": row_num,
                            "idx": idx,
                            "target_text": translated_text,
                            "status": LarkJobStatus.TRANSLATED.value,
                        }
                        # 添加 MQM 分数（如果有）
                        if quality_score is not None:
                            update_data["mqm"] = quality_score
                        # 添加评审摘要（如果有）
                        if review_summary is not None:
                            update_data["review_summary"] = review_summary
                        if review_input is not None:
                            update_data[REVIEW_INPUT_COLUMN] = review_input
                        updates.append(update_data)
                        result.success += 1
                        task_success += 1
                    else:
                        # 翻译失败
                        updates.append(
                            {
                                "row": row_num,
                                "idx": idx,
                                "status": LarkJobStatus.PROBLEM.value,
                                "problem_desc": error_msg or "未知错误",
                            }
                        )
                        result.failed += 1
                        task_failed += 1
                        result.errors.append(f"row={row_num} 翻译失败: {error_msg}")

            # 打印进度
            progress_pct = (completed_tasks / total_tasks) * 100
            logger.info(
                f"[_process_sheet_translations] 进度: {completed_tasks}/{total_tasks} "
                f"({progress_pct:.1f}%) | 本次: {len(task.targets)} 语言, "
                f"成功={task_success}, 失败={task_failed} | "
                f"累计: 成功={result.success}, 失败={result.failed}"
            )

        # 批次间延迟（避免请求过于密集）
        if batch_idx + batch_size < len(task_list):
            await asyncio.sleep(0.5)

    # 批量更新表格（只写入处理过的行）
    if updates:
        # 创建只包含处理过的行的子集 DataFrame
        processed_df = df.loc[list(processed_indices)].copy()
        await _batch_update_sheet(
            client=client,
            spreadsheet_token=spreadsheet_token,
            sheet_id=sheet_id,
            df=processed_df,
            updates=updates,
        )

    return result


async def _batch_update_sheet(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    sheet_id: str,
    df: pd.DataFrame,
    updates: list[dict],
) -> None:
    """
    批量更新表格数据（只写入指定的行）

    Args:
        client: Lark Sheets 客户端
        spreadsheet_token: 电子表格 token
        sheet_id: 工作表 ID
        df: 需要更新的 DataFrame（可以是子集）
        updates: 更新列表
    """
    if not updates:
        return

    # 更新 DataFrame
    for update in updates:
        idx = update["idx"]
        if idx not in df.index:
            continue
        if "target_text" in update:
            df.at[idx, "target_text"] = update["target_text"]
        if "status" in update:
            df.at[idx, "status"] = update["status"]
        if "problem_desc" in update:
            if "problem_desc" in df.columns:
                df.at[idx, "problem_desc"] = update["problem_desc"]
        if "mqm" in update:
            if "mqm" in df.columns:
                df.at[idx, "mqm"] = str(update["mqm"])
        if "review_summary" in update:
            if "review_summary" in df.columns:
                df.at[idx, "review_summary"] = update["review_summary"]
        if REVIEW_INPUT_COLUMN in update:
            if REVIEW_INPUT_COLUMN in df.columns:
                df.at[idx, REVIEW_INPUT_COLUMN] = update[REVIEW_INPUT_COLUMN]

    # 按行写回表格（只写入 DataFrame 中的行到对应位置）
    await client.write_rows_to_sheet(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        df=df,
    )

    logger.info(f"[_batch_update_sheet] 已更新 {len(updates)} 条记录")


async def _process_new_translations(
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> LarkSyncResult:
    """
    处理新翻译任务

    优化流程：
    1. 获取所有 title != "all" 的表格
    2. 将相同 source_text 但不同 target_language 的行合并为多语言翻译任务
    3. 按批次处理翻译任务（默认 batch_size=1，逐条翻译）
    4. 更新 target_text 和 status="translated"

    Args:
        batch_size: 每批处理的 source_text 数量（默认 1）
    """
    # 确保数据库已初始化
    await _ensure_db_initialized()

    total_result = LarkSyncResult()

    logger.info(
        f"[sync_lark_translations] 开始处理新翻译任务 (batch_size={batch_size})"
    )

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        for spreadsheet_token in Config.lark_spreadsheet_tokens:
            logger.info(
                f"[sync_lark_translations] 处理电子表格: {spreadsheet_token}"
            )

            # 获取所有需要处理的表格
            sheets = await _get_translation_sheets(
                client=client,
                spreadsheet_token=spreadsheet_token,
            )

            if not sheets:
                logger.info(
                    f"[sync_lark_translations] 电子表格 {spreadsheet_token} "
                    "没有找到需要处理的表格"
                )
                continue

            # 逐个处理表格
            for sheet in sheets:
                sheet_id = sheet["sheet_id"]
                sheet_title = sheet["title"]

                try:
                    sheet_result = await _process_sheet_translations(
                        client=client,
                        spreadsheet_token=spreadsheet_token,
                        sheet_id=sheet_id,
                        sheet_title=sheet_title,
                        batch_size=batch_size,
                    )

                    # 汇总结果
                    total_result.total_records += sheet_result.total_records
                    total_result.processed += sheet_result.processed
                    total_result.success += sheet_result.success
                    total_result.failed += sheet_result.failed
                    total_result.skipped += sheet_result.skipped
                    total_result.errors.extend(sheet_result.errors)

                except Exception as e:
                    logger.error(
                        f"[sync_lark_translations] 处理表格 {sheet_title} 失败: {e}"
                    )
                    total_result.errors.append(f"表格 {sheet_title} 处理失败: {e}")

    logger.info(
        f"[sync_lark_translations] 处理完成, "
        f"总计={total_result.total_records}, 成功={total_result.success}, "
        f"失败={total_result.failed}, 跳过={total_result.skipped}"
    )

    return total_result


async def _process_sheet_glossary(
    client: LarkSheetsClient,
    spreadsheet_token: str,
    sheet_id: str,
    sheet_title: str,
    agent: GlossaryExtractionAgent,
) -> LarkSyncResult:
    """
    处理单个表格的术语提取

    Args:
        client: Lark Sheets 客户端
        spreadsheet_token: 电子表格 token
        sheet_id: 工作表 ID
        sheet_title: 工作表标题
        agent: 术语提取 Agent

    Returns:
        处理结果
    """
    result = LarkSyncResult()

    logger.info(f"[_process_sheet_glossary] 处理表格: {sheet_title} ({sheet_id})")

    # 读取表格数据为 DataFrame
    df = await client.read_sheet_as_dataframe(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
    )

    if df.empty:
        logger.info(f"[_process_sheet_glossary] 表格 {sheet_title} 为空")
        return result

    # 检查表格是否准备好处理
    if not _check_sheet_ready(df, sheet_title):
        return result

    # 检查必要的列是否存在（自动适配新旧格式）
    if "source_text_1" in df.columns:
        required_columns = ["status", "source_text_1", "target_text", "target_language"]
    else:
        required_columns = ["status", "source_text", "target_text", "target_language"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.warning(
            f"[_process_sheet_glossary] 表格 {sheet_title} 缺少必要列: {missing_columns}"
        )
        return result

    # 过滤 status="reviewed" 的记录
    reviewed_records = df[df["status"] == LarkJobStatus.REVIEWED.value].copy()
    result.total_records = len(reviewed_records)

    logger.info(
        f"[_process_sheet_glossary] 表格 {sheet_title} 有 {len(reviewed_records)} 条已审核记录"
    )

    if reviewed_records.empty:
        return result

    # 准备更新数据
    updates = []

    # 检测列格式
    use_new_format = "source_text_1" in df.columns

    for idx, row in reviewed_records.iterrows():
        result.processed += 1
        row_num = idx + 2

        if use_new_format:
            source_text = str(row.get("source_text_1", "")).strip()
        else:
            source_text = str(row.get("source_text", "")).strip()
        target_text = str(row.get("target_text", "")).strip()
        target_language = str(row.get("target_language", "")).strip()

        # 跳过无效记录
        if not source_text or not target_text:
            logger.warning(
                f"[_process_sheet_glossary] 跳过无效记录: row={row_num}, "
                f"source_text={bool(source_text)}, target_text={bool(target_text)}"
            )
            result.skipped += 1
            continue

        try:
            # 构建术语提取请求
            extract_request = GlossaryExtractRequest(
                source_text=source_text,
                human_translation=target_text,
                target_lang=target_language,
                translation_job_id=f"{sheet_id}_{row_num}",
            )

            # 执行术语提取
            extract_response = await agent.run(extract_request)

            # 记录更新
            updates.append(
                {
                    "row": row_num,
                    "idx": idx,
                    "status": LarkJobStatus.COMPLETED.value,
                }
            )

            result.success += 1
            logger.info(
                f"[_process_sheet_glossary] 处理成功: row={row_num}, "
                f"提取术语={extract_response.candidates_created}"
            )

        except Exception as e:
            result.failed += 1
            error_msg = f"row={row_num} 术语提取失败: {e}"
            result.errors.append(error_msg)
            logger.error(f"[_process_sheet_glossary] {error_msg}")

    # 批量更新表格（只写入处理过的行）
    if updates:
        processed_indices = {u["idx"] for u in updates}
        processed_df = df.loc[list(processed_indices)].copy()
        await _batch_update_sheet(
            client=client,
            spreadsheet_token=spreadsheet_token,
            sheet_id=sheet_id,
            df=processed_df,
            updates=updates,
        )

    return result


async def _process_reviewed_translations() -> LarkSyncResult:
    """
    处理已审核翻译，提取术语

    1. 获取所有 title != "all" 的表格
    2. 逐个处理每个表格中 status="reviewed" 的记录
    3. 使用 GlossaryExtractionAgent 提取术语
    4. 更新 status="completed"
    """
    # 确保数据库已初始化
    await _ensure_db_initialized()

    total_result = LarkSyncResult()

    logger.info("[sync_lark_glossary] 开始处理已审核翻译")

    async with LarkSheetsClient(
        app_id=Config.lark_app_id,
        app_secret=Config.lark_app_secret,
    ) as client:
        # 使用术语提取 Agent
        async with GlossaryExtractionAgent() as agent:
            for spreadsheet_token in Config.lark_spreadsheet_tokens:
                logger.info(
                    f"[sync_lark_glossary] 处理电子表格: {spreadsheet_token}"
                )

                # 获取所有需要处理的表格
                sheets = await _get_translation_sheets(
                    client=client,
                    spreadsheet_token=spreadsheet_token,
                )

                if not sheets:
                    logger.info(
                        f"[sync_lark_glossary] 电子表格 {spreadsheet_token} "
                        "没有找到需要处理的表格"
                    )
                    continue

                # 逐个处理表格
                for sheet in sheets:
                    sheet_id = sheet["sheet_id"]
                    sheet_title = sheet["title"]

                    try:
                        sheet_result = await _process_sheet_glossary(
                            client=client,
                            spreadsheet_token=spreadsheet_token,
                            sheet_id=sheet_id,
                            sheet_title=sheet_title,
                            agent=agent,
                        )

                        # 汇总结果
                        total_result.total_records += sheet_result.total_records
                        total_result.processed += sheet_result.processed
                        total_result.success += sheet_result.success
                        total_result.failed += sheet_result.failed
                        total_result.skipped += sheet_result.skipped
                        total_result.errors.extend(sheet_result.errors)

                    except Exception as e:
                        logger.error(
                            f"[sync_lark_glossary] 处理表格 {sheet_title} 失败: {e}"
                        )
                        total_result.errors.append(f"表格 {sheet_title} 处理失败: {e}")

        # 刷新术语表缓存
        if total_result.success > 0:
            try:
                glossary_service.invalidate_db_cache()
                logger.info("[sync_lark_glossary] 已刷新术语表缓存")
            except Exception as e:
                logger.warning(f"[sync_lark_glossary] 刷新缓存失败: {e}")

    logger.info(
        f"[sync_lark_glossary] 处理完成, "
        f"总计={total_result.total_records}, 成功={total_result.success}, "
        f"失败={total_result.failed}, 跳过={total_result.skipped}"
    )

    return total_result


@app.register(name="sync_lark_translations")
def sync_lark_translations() -> str:
    """
    定时任务：处理 Lark 电子表格中的翻译任务

    优化流程：
    1. 获取所有 title != "all" 的表格
    2. 将相同 source_text 但不同 target_language 的行合并为多语言翻译任务
    3. 按批次处理翻译任务（默认 batch_size=1，逐条翻译）
    4. 更新 target_text 和 status="translated"

    Returns:
        执行结果摘要
    """
    logger.info("[sync_lark_translations] 任务开始执行")

    try:
        # 可通过配置调整 batch_size，默认为 1（逐条翻译）
        batch_size = getattr(Config, "lark_translation_batch_size", DEFAULT_BATCH_SIZE)
        result = run_async(_process_new_translations(batch_size=batch_size))
        summary = (
            f"翻译任务处理完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        logger.info(f"[sync_lark_translations] {summary}")
        return summary
    except Exception as e:
        error_msg = f"翻译任务执行失败: {e}"
        logger.error(f"[sync_lark_translations] {error_msg}")
        raise


@app.register(name="sync_lark_glossary_tables")
def sync_lark_glossary_tables() -> str:
    """
    定时任务：同步三张术语库表到 Lark（双向同步）

    1. 读取 Lark 表格，若存在修改则更新数据库
    2. 导出最新数据库内容回写 Lark

    Returns:
        执行结果摘要
    """
    logger.info("[sync_lark_glossary_tables] 任务开始执行")

    try:
        result = run_async(_sync_glossary_tables())
        summary = (
            f"术语库同步完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        logger.info(f"[sync_lark_glossary_tables] {summary}")
        return summary
    except Exception as e:
        error_msg = f"术语库同步失败: {e}"
        logger.error(f"[sync_lark_glossary_tables] {error_msg}")
        raise


@app.register(name="migrate_glossary_candidates")
def migrate_glossary_candidates() -> str:
    """
    定时任务：将已批准的候选术语迁移到正式术语库

    1. 查询所有 status="approved" 的候选术语
    2. 将其迁移到 business_glossary_terms 表
    3. 更新候选状态为 status="migrated"
    4. 刷新术语表缓存

    Returns:
        执行结果摘要
    """
    logger.info("[migrate_glossary_candidates] 任务开始执行")

    try:
        result = run_async(_migrate_approved_candidates())
        summary = (
            f"候选术语迁移完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        logger.info(f"[migrate_glossary_candidates] {summary}")
        return summary
    except Exception as e:
        error_msg = f"候选术语迁移失败: {e}"
        logger.error(f"[migrate_glossary_candidates] {error_msg}")
        raise


async def _migrate_approved_candidates() -> LarkSyncResult:
    """
    迁移已批准的候选术语到正式术语库

    1. 获取所有 status="approved" 的候选术语
    2. 逐个迁移到 business_glossary_terms 表
    3. 更新候选状态为 status="migrated"
    4. 刷新术语表缓存
    """
    # 确保数据库已初始化
    await _ensure_db_initialized()

    result = LarkSyncResult()

    logger.info("[migrate_glossary_candidates] 开始迁移已批准的候选术语")

    try:
        # 获取已批准的候选术语
        candidates = await glossary_repository.get_approved_candidates(limit=500)
        result.total_records = len(candidates)

        if not candidates:
            logger.info("[migrate_glossary_candidates] 没有待迁移的候选术语")
            return result

        logger.info(
            f"[migrate_glossary_candidates] 找到 {len(candidates)} 个待迁移的候选术语"
        )

        # 逐个迁移
        for candidate in candidates:
            result.processed += 1

            try:
                success = await glossary_repository.migrate_candidate_to_glossary(
                    candidate
                )
                if success:
                    result.success += 1
                    logger.info(
                        f"[migrate_glossary_candidates] 迁移成功: "
                        f"{candidate.id} ({candidate.term_en})"
                    )
                else:
                    result.failed += 1
                    result.errors.append(f"id={candidate.id} 迁移失败")

            except Exception as e:
                result.failed += 1
                error_msg = f"id={candidate.id} 迁移异常: {e}"
                result.errors.append(error_msg)
                logger.error(f"[migrate_glossary_candidates] {error_msg}")

        # 刷新术语表缓存
        if result.success > 0:
            try:
                glossary_service.invalidate_db_cache()
                logger.info("[migrate_glossary_candidates] 已刷新术语表缓存")
            except Exception as e:
                logger.warning(f"[migrate_glossary_candidates] 刷新缓存失败: {e}")

    except Exception as e:
        logger.error(f"[migrate_glossary_candidates] 迁移过程异常: {e}")
        result.errors.append(str(e))

    logger.info(
        f"[migrate_glossary_candidates] 迁移完成, "
        f"总计={result.total_records}, 成功={result.success}, "
        f"失败={result.failed}"
    )

    return result


@app.register(name="sync_lark_glossary")
def sync_lark_glossary() -> str:
    """
    定时任务：处理 Lark 电子表格中已审核的翻译

    1. 获取所有 title != "all" 的表格
    2. 查询每个表格中 status="reviewed" 的记录
    3. 提取术语并更新到 glossary 数据库
    4. 更新 status="completed"

    Returns:
        执行结果摘要
    """
    logger.info("[sync_lark_glossary] 任务开始执行")

    try:
        result = run_async(_process_reviewed_translations())
        summary = (
            f"术语提取任务处理完成: "
            f"总计={result.total_records}, 成功={result.success}, "
            f"失败={result.failed}, 跳过={result.skipped}"
        )
        logger.info(f"[sync_lark_glossary] {summary}")
        return summary
    except Exception as e:
        error_msg = f"术语提取任务执行失败: {e}"
        logger.error(f"[sync_lark_glossary] {error_msg}")
        raise


if __name__ == "__main__":
    logger.info("[xxl_lark_translation] 启动 XXL 执行器")
    app.run_executor()
