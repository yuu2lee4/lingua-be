"""
术语表 Repository (Business AI Glossary)

提供业务术语表的数据访问层，封装所有数据库操作。
这是两级术语库系统的 Level 2，用于 AI 提示词增强。

Level 1 (Match Glossary) 由 match_glossary_service 处理。

Tables:
- business_glossary_terms: 业务术语主表
- glossary_candidates: 候选术语表（保留）
"""

import json
import hashlib
from pathlib import Path
from typing import Any

from app.db.connection import DatabasePool
from app.logger import logger
from app.core.exceptions import (
    GlossaryTermNotFoundError,
    GlossaryTermExistsError,
)
from app.schemas.glossary_db import (
    GlossaryTermCreate,
    GlossaryTermUpdate,
    GlossaryTermResponse,
    TranslationUpdate,
    GlossaryCandidateCreate,
    GlossaryCandidateResponse,
    CandidateStatus,
    TermSource,
)
from app.utils.glossary_columns import (
    TRANSLATION_COLUMNS,
    build_translation_columns,
    extract_translations,
    require_translation_column,
)

# 默认术语表文件路径
DEFAULT_GLOSSARY_PATH = Path(__file__).parent.parent.parent / "examples" / "glossary.json"

# 通用列
BUSINESS_TERM_BASE_COLUMNS = [
    "id",
    "term_id",
    "term_en",
    "definition",
    "part_of_speech",
    "do_not_translate",
    "source",
    "status",
    "created_at",
    "updated_at",
]
BUSINESS_TERM_SELECT_COLUMNS = ", ".join([*BUSINESS_TERM_BASE_COLUMNS, *TRANSLATION_COLUMNS])

CANDIDATE_BASE_COLUMNS = [
    "id",
    "term_id",
    "term_en",
    "definition",
    "part_of_speech",
    "do_not_translate",
    "source",
    "status",
    "migrated_to_match_glossary",
    "migrated_to_business_glossary",
    "created_at",
    "updated_at",
]
CANDIDATE_SELECT_COLUMNS = ", ".join([*CANDIDATE_BASE_COLUMNS, *TRANSLATION_COLUMNS])


def _generate_term_id(term_en: str) -> str:
    """生成术语 ID（基于英文术语的 MD5 哈希）"""
    return hashlib.md5(term_en.lower().encode()).hexdigest()[:16]


class GlossaryRepository:
    """术语表 Repository"""

    # ============ 术语 CRUD ============

    async def create_term(self, term: GlossaryTermCreate) -> GlossaryTermResponse:
        """
        创建术语

        Args:
            term: 创建请求

        Returns:
            创建的术语

        Raises:
            GlossaryTermExistsError: 术语已存在
        """
        term_id = _generate_term_id(term.term_en)

        # 检查是否已存在
        existing = await self.get_term_by_id(term_id)
        if existing:
            raise GlossaryTermExistsError(term.term_en)

        translation_columns = build_translation_columns(term.translations)
        column_names = [
            "term_id",
            "term_en",
            "definition",
            "part_of_speech",
            "do_not_translate",
            "source",
            "status",
            *translation_columns.keys(),
        ]
        values = [
            term_id,
            term.term_en,
            term.definition,
            term.part_of_speech,
            1 if term.do_not_translate else 0,
            term.source.value,
            "active",
            *translation_columns.values(),
        ]
        placeholders = ", ".join(["%s"] * len(column_names))
        query = f"""
            INSERT INTO business_glossary_terms
            ({", ".join(column_names)})
            VALUES ({placeholders})
        """
        await DatabasePool.execute(query, tuple(values))

        logger.info(f"[create_term] 创建术语成功: {term_id} ({term.term_en})")
        return await self.get_term_by_id(term_id)  # type: ignore

    async def get_term_by_id(self, term_id: str) -> GlossaryTermResponse | None:
        """
        根据 ID 获取术语

        Args:
            term_id: 术语 ID

        Returns:
            术语信息，或 None
        """
        # 查询术语主表
        query = f"""
            SELECT {BUSINESS_TERM_SELECT_COLUMNS}
            FROM business_glossary_terms
            WHERE term_id = %s AND status != 'deleted'
        """
        row = await DatabasePool.fetch_one(query, (term_id,))
        if not row:
            return None
        translations = extract_translations(row)

        return GlossaryTermResponse(
            term_id=row["term_id"],
            term_en=row["term_en"],
            definition=row["definition"] or "",
            part_of_speech=row["part_of_speech"] or "",
            do_not_translate=bool(row["do_not_translate"]),
            translations=translations,
            source=row["source"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_term_by_en(self, term_en: str) -> GlossaryTermResponse | None:
        """
        根据英文术语获取

        Args:
            term_en: 英文术语

        Returns:
            术语信息，或 None
        """
        term_id = _generate_term_id(term_en)
        return await self.get_term_by_id(term_id)

    async def update_term(
        self, term_id: str, update: GlossaryTermUpdate
    ) -> GlossaryTermResponse:
        """
        更新术语

        Args:
            term_id: 术语 ID
            update: 更新请求

        Returns:
            更新后的术语

        Raises:
            GlossaryTermNotFoundError: 术语不存在
        """
        existing = await self.get_term_by_id(term_id)
        if not existing:
            raise GlossaryTermNotFoundError(term_id)

        # 构建更新语句
        updates = []
        params: list[Any] = []

        if update.definition is not None:
            updates.append("definition = %s")
            params.append(update.definition)
        if update.part_of_speech is not None:
            updates.append("part_of_speech = %s")
            params.append(update.part_of_speech)
        if update.do_not_translate is not None:
            updates.append("do_not_translate = %s")
            params.append(1 if update.do_not_translate else 0)
        if update.status is not None:
            updates.append("status = %s")
            params.append(update.status.value)

        if updates:
            query = f"UPDATE business_glossary_terms SET {', '.join(updates)} WHERE term_id = %s"
            params.append(term_id)
            await DatabasePool.execute(query, tuple(params))
            logger.info(f"[update_term] 更新术语成功: {term_id}")

        return await self.get_term_by_id(term_id)  # type: ignore

    async def delete_term(self, term_id: str) -> bool:
        """
        删除术语（软删除）

        Args:
            term_id: 术语 ID

        Returns:
            是否删除成功
        """
        query = "UPDATE business_glossary_terms SET status = 'deleted' WHERE term_id = %s"
        affected = await DatabasePool.execute(query, (term_id,))
        if affected > 0:
            logger.info(f"[delete_term] 删除术语成功: {term_id}")
            return True
        return False

    async def list_terms(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[GlossaryTermResponse], int]:
        """
        列出术语

        Args:
            page: 页码
            page_size: 每页数量
            status: 状态筛选
            search: 搜索关键词

        Returns:
            (术语列表, 总数)
        """
        # 构建查询条件
        conditions = ["status != 'deleted'"]
        params: list[Any] = []

        if status:
            conditions.append("status = %s")
            params.append(status)
        if search:
            conditions.append("(term_en LIKE %s OR definition LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_clause = " AND ".join(conditions)

        # 查询总数
        count_query = f"SELECT COUNT(*) as total FROM business_glossary_terms WHERE {where_clause}"
        count_result = await DatabasePool.fetch_one(count_query, tuple(params))
        total = count_result["total"] if count_result else 0

        # 分页查询
        offset = (page - 1) * page_size
        query = f"""
            SELECT {BUSINESS_TERM_SELECT_COLUMNS}
            FROM business_glossary_terms
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        rows = await DatabasePool.fetch_all(query, tuple(params))

        terms = []
        for row in rows:
            translations = extract_translations(row)
            terms.append(
                GlossaryTermResponse(
                    term_id=row["term_id"],
                    term_en=row["term_en"],
                    definition=row["definition"] or "",
                    part_of_speech=row["part_of_speech"] or "",
                    do_not_translate=bool(row["do_not_translate"]),
                    translations=translations,
                    source=row["source"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return terms, total

    async def search_terms(
        self, keyword: str, limit: int = 20
    ) -> list[GlossaryTermResponse]:
        """
        搜索术语

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的术语列表
        """
        query = f"""
            SELECT {BUSINESS_TERM_SELECT_COLUMNS}
            FROM business_glossary_terms
            WHERE status = 'active'
              AND (term_en LIKE %s OR definition LIKE %s)
            ORDER BY
                CASE WHEN term_en = %s THEN 0
                     WHEN term_en LIKE %s THEN 1
                     ELSE 2 END,
                term_en
            LIMIT %s
        """
        params = (
            f"%{keyword}%",
            f"%{keyword}%",
            keyword,
            f"{keyword}%",
            limit,
        )
        rows = await DatabasePool.fetch_all(query, params)

        terms = []
        for row in rows:
            translations = extract_translations(row)
            terms.append(
                GlossaryTermResponse(
                    term_id=row["term_id"],
                    term_en=row["term_en"],
                    definition=row["definition"] or "",
                    part_of_speech=row["part_of_speech"] or "",
                    do_not_translate=bool(row["do_not_translate"]),
                    translations=translations,
                    source=row["source"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return terms

    async def count_terms(self) -> int:
        """
        获取术语总数

        Returns:
            术语总数
        """
        query = "SELECT COUNT(*) as total FROM business_glossary_terms WHERE status != 'deleted'"
        result = await DatabasePool.fetch_one(query)
        return result["total"] if result else 0

    async def is_empty(self) -> bool:
        """
        检查术语表是否为空

        Returns:
            是否为空
        """
        count = await self.count_terms()
        return count == 0

    async def get_all_active_terms(self) -> list[GlossaryTermResponse]:
        """
        获取所有激活的术语（用于缓存预热）

        Returns:
            所有激活的术语列表
        """
        query = f"""
            SELECT {BUSINESS_TERM_SELECT_COLUMNS}
            FROM business_glossary_terms
            WHERE status = 'active'
            ORDER BY term_en
        """
        rows = await DatabasePool.fetch_all(query)

        terms = []
        for row in rows:
            term_id = row["term_id"]
            translations = extract_translations(row)
            terms.append(
                GlossaryTermResponse(
                    term_id=term_id,
                    term_en=row["term_en"],
                    definition=row["definition"] or "",
                    part_of_speech=row["part_of_speech"] or "",
                    do_not_translate=bool(row["do_not_translate"]),
                    translations=translations,
                    source=row["source"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return terms

    # ============ 翻译更新 ============

    async def update_translation(
        self, term_id: str, lang_code: str, update: TranslationUpdate
    ) -> dict[str, str]:
        """
        更新术语翻译

        Args:
            term_id: 术语 ID
            lang_code: 语言代码
            update: 更新请求

        Returns:
            更新后的所有翻译

        Raises:
            GlossaryTermNotFoundError: 术语不存在
        """
        existing = await self.get_term_by_id(term_id)
        if not existing:
            raise GlossaryTermNotFoundError(term_id)

        column = require_translation_column(lang_code)
        query = f"""
            UPDATE business_glossary_terms
            SET {column} = %s
            WHERE term_id = %s
        """
        await DatabasePool.execute(query, (update.translation, term_id))

        logger.info(
            f"[update_translation] 更新翻译成功: {term_id} [{lang_code}] = {update.translation}"
        )

        updated = await self.get_term_by_id(term_id)
        return updated.translations if updated else {}

    async def _update_term_translations(
        self, term_id: str, translations: dict[str, str]
    ) -> None:
        """批量更新术语翻译列"""
        translation_columns = build_translation_columns(translations)
        if not translation_columns:
            return
        set_clause = ", ".join([f"{col} = %s" for col in translation_columns.keys()])
        values = [*translation_columns.values(), term_id]
        query = f"""
            UPDATE business_glossary_terms
            SET {set_clause}
            WHERE term_id = %s
        """
        await DatabasePool.execute(query, tuple(values))

    # ============ 候选术语 CRUD ============

    async def create_candidate(
        self, candidate: GlossaryCandidateCreate
    ) -> GlossaryCandidateResponse:
        """
        创建候选术语

        Args:
            candidate: 创建请求

        Returns:
            创建的候选术语
        """
        term_id = _generate_term_id(candidate.term_en)
        translation_columns = build_translation_columns(candidate.translations)
        column_names = [
            "term_id",
            "term_en",
            "definition",
            "part_of_speech",
            "do_not_translate",
            "source",
            "status",
            "migrated_to_match_glossary",
            "migrated_to_business_glossary",
            *translation_columns.keys(),
        ]
        values = [
            term_id,
            candidate.term_en,
            candidate.definition,
            candidate.part_of_speech,
            1 if candidate.do_not_translate else 0,
            candidate.source.value,
            "pending",
            0,
            0,
            *translation_columns.values(),
        ]
        placeholders = ", ".join(["%s"] * len(column_names))
        update_parts = [
            "definition = VALUES(definition)",
            "part_of_speech = VALUES(part_of_speech)",
            "do_not_translate = VALUES(do_not_translate)",
            "source = VALUES(source)",
        ]
        update_parts.extend([f"{col} = VALUES({col})" for col in translation_columns.keys()])
        query = f"""
            INSERT INTO glossary_candidates
            ({", ".join(column_names)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {", ".join(update_parts)}
        """
        await DatabasePool.execute(query, tuple(values))

        candidate_row = await DatabasePool.fetch_one(
            "SELECT id FROM glossary_candidates WHERE term_id = %s",
            (term_id,),
        )
        candidate_id = candidate_row["id"] if candidate_row else None

        logger.info(
            f"[create_candidate] 创建候选术语成功: {candidate_id} ({candidate.term_en})"
        )
        return await self.get_candidate_by_id(candidate_id)  # type: ignore

    async def get_candidate_by_id(
        self, candidate_id: int
    ) -> GlossaryCandidateResponse | None:
        """
        根据 ID 获取候选术语

        Args:
            candidate_id: 候选术语 ID

        Returns:
            候选术语信息，或 None
        """
        query = f"""
            SELECT {CANDIDATE_SELECT_COLUMNS}
            FROM glossary_candidates
            WHERE id = %s
        """
        row = await DatabasePool.fetch_one(query, (candidate_id,))
        if not row:
            return None
        translations = extract_translations(row)

        return GlossaryCandidateResponse(
            id=row["id"],
            term_id=row["term_id"],
            term_en=row["term_en"],
            definition=row["definition"] or "",
            part_of_speech=row["part_of_speech"] or "",
            do_not_translate=bool(row["do_not_translate"]),
            translations=translations,
            source=row["source"],
            status=row["status"],
            migrated_to_match_glossary=bool(row["migrated_to_match_glossary"]),
            migrated_to_business_glossary=bool(row["migrated_to_business_glossary"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list_candidates(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[GlossaryCandidateResponse], int]:
        """
        列出候选术语

        Args:
            page: 页码
            page_size: 每页数量
            status: 状态筛选

        Returns:
            (候选术语列表, 总数)
        """
        conditions = ["1=1"]
        params: list[Any] = []

        if status:
            conditions.append("status = %s")
            params.append(status)

        where_clause = " AND ".join(conditions)

        # 查询总数
        count_query = f"SELECT COUNT(*) as total FROM glossary_candidates WHERE {where_clause}"
        count_result = await DatabasePool.fetch_one(count_query, tuple(params))
        total = count_result["total"] if count_result else 0

        # 分页查询
        offset = (page - 1) * page_size
        query = f"""
            SELECT {CANDIDATE_SELECT_COLUMNS}
            FROM glossary_candidates
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        rows = await DatabasePool.fetch_all(query, tuple(params))

        candidates = []
        for row in rows:
            translations = extract_translations(row)
            candidates.append(
                GlossaryCandidateResponse(
                    id=row["id"],
                    term_id=row["term_id"],
                    term_en=row["term_en"],
                    definition=row["definition"] or "",
                    part_of_speech=row["part_of_speech"] or "",
                    do_not_translate=bool(row["do_not_translate"]),
                    translations=translations,
                    source=row["source"],
                    status=row["status"],
                    migrated_to_match_glossary=bool(row["migrated_to_match_glossary"]),
                    migrated_to_business_glossary=bool(
                        row["migrated_to_business_glossary"]
                    ),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return candidates, total

    async def get_approved_candidates(
        self,
        limit: int = 100,
    ) -> list[GlossaryCandidateResponse]:
        """
        获取所有已批准但未迁移的候选术语

        Args:
            limit: 返回数量限制

        Returns:
            候选术语列表
        """
        query = f"""
            SELECT {CANDIDATE_SELECT_COLUMNS}
            FROM glossary_candidates
            WHERE status = %s
              AND migrated_to_business_glossary = 0
            ORDER BY created_at ASC
            LIMIT %s
        """
        rows = await DatabasePool.fetch_all(
            query, (CandidateStatus.APPROVED.value, limit)
        )

        candidates = []
        for row in rows:
            translations = extract_translations(row)
            candidates.append(
                GlossaryCandidateResponse(
                    id=row["id"],
                    term_id=row["term_id"],
                    term_en=row["term_en"],
                    definition=row["definition"] or "",
                    part_of_speech=row["part_of_speech"] or "",
                    do_not_translate=bool(row["do_not_translate"]),
                    translations=translations,
                    source=row["source"],
                    status=row["status"],
                    migrated_to_match_glossary=bool(row["migrated_to_match_glossary"]),
                    migrated_to_business_glossary=bool(
                        row["migrated_to_business_glossary"]
                    ),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return candidates

    async def migrate_candidate_to_glossary(
        self,
        candidate: GlossaryCandidateResponse,
    ) -> bool:
        """
        将单个候选术语迁移到正式术语库

        Args:
            candidate: 候选术语

        Returns:
            是否迁移成功
        """
        try:
            # 创建正式术语
            term_create = GlossaryTermCreate(
                term_en=candidate.term_en,
                definition=candidate.definition,
                translations=candidate.translations,
                source=TermSource.AI_EXTRACTED,
            )

            try:
                await self.create_term(term_create)
                logger.info(
                    f"[migrate_candidate_to_glossary] 创建术语成功: {candidate.term_en}"
                )
            except GlossaryTermExistsError:
                # 术语已存在，更新翻译
                term_id = _generate_term_id(candidate.term_en)
                await self._update_term_translations(
                    term_id, candidate.translations
                )
                logger.info(
                    f"[migrate_candidate_to_glossary] 术语已存在，更新翻译: {candidate.term_en}"
                )

            # 更新候选状态为已迁移
            update_query = """
                UPDATE glossary_candidates
                SET status = %s,
                    migrated_to_business_glossary = 1
                WHERE id = %s
            """
            await DatabasePool.execute(
                update_query, (CandidateStatus.MIGRATED.value, candidate.id)
            )

            return True

        except Exception as e:
            logger.error(
                f"[migrate_candidate_to_glossary] 迁移失败: {candidate.term_en}, 错误: {e}"
            )
            return False

    async def review_candidate(
        self,
        candidate_id: int,
        action: CandidateStatus,
        translations: dict[str, str] | None = None,
        migrate_to_match: bool = False,
        migrate_to_business: bool = True,
    ) -> GlossaryCandidateResponse | None:
        """
        审核候选术语

        Args:
            candidate_id: 候选术语 ID
            action: 审核操作
            translations: 确认的翻译（批准时使用）
            migrate_to_match: 是否迁移到 Match Glossary
            migrate_to_business: 是否迁移到 Business Glossary

        Returns:
            更新后的候选术语
        """
        candidate = await self.get_candidate_by_id(candidate_id)
        if not candidate:
            return None

        # 更新状态（先写入审核结果）
        new_status = action.value
        query = """
            UPDATE glossary_candidates
            SET status = %s
            WHERE id = %s
        """
        await DatabasePool.execute(query, (new_status, candidate_id))

        # 如果提供了确认翻译，先更新候选翻译列
        if translations:
            translation_columns = build_translation_columns(translations)
            if translation_columns:
                set_clause = ", ".join(
                    [f"{col} = %s" for col in translation_columns.keys()]
                )
                values = [*translation_columns.values(), candidate_id]
                update_trans_query = f"""
                    UPDATE glossary_candidates
                    SET {set_clause}
                    WHERE id = %s
                """
                await DatabasePool.execute(update_trans_query, tuple(values))

        # 如果批准，创建正式术语
        migrated_any = False

        if action == CandidateStatus.APPROVED:
            final_translations = translations or candidate.translations

            if migrate_to_business:
                term_create = GlossaryTermCreate(
                    term_en=candidate.term_en,
                    definition=candidate.definition,
                    translations=final_translations,
                    source=TermSource.AI_EXTRACTED,
                )
                try:
                    await self.create_term(term_create)
                    logger.info(
                        f"[review_candidate] 候选术语已批准并入库: {candidate.term_en}"
                    )
                except GlossaryTermExistsError:
                    # 术语已存在，更新翻译
                    term_id = _generate_term_id(candidate.term_en)
                    await self._update_term_translations(term_id, final_translations)
                    logger.info(
                        f"[review_candidate] 术语已存在，更新翻译: {candidate.term_en}"
                    )

                await DatabasePool.execute(
                    """
                        UPDATE glossary_candidates
                        SET migrated_to_business_glossary = 1
                        WHERE id = %s
                    """,
                    (candidate_id,),
                )
                migrated_any = True

            if migrate_to_match:
                try:
                    from app.services.match_glossary_service import (
                        match_glossary_service,
                    )

                    await match_glossary_service.upsert_translations_batch(
                        term_en=candidate.term_en,
                        translations=final_translations,
                        source="ai_extracted",
                    )
                    await DatabasePool.execute(
                        """
                            UPDATE glossary_candidates
                            SET migrated_to_match_glossary = 1
                            WHERE id = %s
                        """,
                        (candidate_id,),
                    )
                    migrated_any = True
                except Exception as e:
                    logger.warning(
                        f"[review_candidate] 迁移到 Match Glossary 失败: {candidate.term_en}, 错误: {e}"
                    )

        if migrated_any and action == CandidateStatus.APPROVED:
            await DatabasePool.execute(
                "UPDATE glossary_candidates SET status = %s WHERE id = %s",
                (CandidateStatus.MIGRATED.value, candidate_id),
            )

        return await self.get_candidate_by_id(candidate_id)

    # ============ 初始化 ============

    async def initialize_from_default_glossary(
        self, glossary_path: Path | None = None
    ) -> tuple[int, int, list[str]]:
        """
        从默认术语表文件初始化数据库

        仅当 business_glossary_terms 表为空时执行导入

        Args:
            glossary_path: 术语表文件路径，默认使用 examples/glossary.json

        Returns:
            (导入成功数, 跳过数, 错误列表)
        """
        # 检查是否为空
        if not await self.is_empty():
            logger.info("[initialize_from_default_glossary] 术语表非空，跳过初始化")
            return 0, 0, []

        # 确定文件路径
        file_path = glossary_path or DEFAULT_GLOSSARY_PATH
        if not file_path.exists():
            logger.warning(
                f"[initialize_from_default_glossary] 默认术语表文件不存在: {file_path}"
            )
            return 0, 0, [f"文件不存在: {file_path}"]

        # 读取 JSON 文件
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"[initialize_from_default_glossary] JSON 解析失败: {e}")
            return 0, 0, [f"JSON 解析失败: {e}"]

        # 解析术语列表
        terms_data = data.get("terms", [])
        if not terms_data:
            logger.warning("[initialize_from_default_glossary] 术语表文件为空")
            return 0, 0, []

        # 转换为 GlossaryTermCreate 对象
        terms: list[GlossaryTermCreate] = []
        for item in terms_data:
            try:
                term = GlossaryTermCreate(
                    term_en=item.get("term_en", ""),
                    definition=item.get("definition", ""),
                    part_of_speech=item.get("part_of_speech", ""),
                    do_not_translate=item.get("do_not_translate", False),
                    translations=item.get("translations", {}),
                    source=TermSource.IMPORTED,
                )
                terms.append(term)
            except Exception as e:
                logger.warning(
                    f"[initialize_from_default_glossary] 解析术语失败: {item.get('term_en', 'unknown')} - {e}"
                )

        if not terms:
            logger.warning("[initialize_from_default_glossary] 没有有效的术语可导入")
            return 0, 0, []

        # 执行导入
        imported, skipped, errors = await self.import_terms(terms, overwrite=False)
        logger.info(
            f"[initialize_from_default_glossary] 初始化完成: "
            f"导入={imported}, 跳过={skipped}, 错误={len(errors)}"
        )
        return imported, skipped, errors

    # ============ 导入导出 ============

    async def import_terms(
        self, terms: list[GlossaryTermCreate], overwrite: bool = False
    ) -> tuple[int, int, list[str]]:
        """
        批量导入术语

        Args:
            terms: 术语列表
            overwrite: 是否覆盖已存在的术语

        Returns:
            (导入成功数, 跳过数, 错误列表)
        """
        imported = 0
        skipped = 0
        errors: list[str] = []

        for term in terms:
            try:
                existing = await self.get_term_by_en(term.term_en)
                if existing:
                    if overwrite:
                        term_id = _generate_term_id(term.term_en)
                        # 更新术语
                        update = GlossaryTermUpdate(
                            definition=term.definition,
                            part_of_speech=term.part_of_speech,
                            do_not_translate=term.do_not_translate,
                        )
                        await self.update_term(term_id, update)
                        # 更新翻译
                        if term.translations:
                            await self._update_term_translations(
                                term_id, term.translations
                            )
                        imported += 1
                    else:
                        skipped += 1
                else:
                    await self.create_term(term)
                    imported += 1
            except Exception as e:
                errors.append(f"{term.term_en}: {str(e)}")

        logger.info(
            f"[import_terms] 导入完成: 成功={imported}, 跳过={skipped}, 错误={len(errors)}"
        )
        return imported, skipped, errors


# 全局单例
glossary_repository = GlossaryRepository()
