"""
术语表 API 端点

提供术语表的 CRUD、搜索、AI 提取等功能
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.logger import logger
from app.core.exceptions import (
    GlossaryTermNotFoundError,
    GlossaryTermExistsError,
    DatabaseError,
)
from app.db.connection import DatabasePool
from app.repositories.glossary_repository import glossary_repository
from app.services.glossary_service import glossary_service
from app.agents.glossary_extraction_agent import GlossaryExtractionAgent
from app.schemas.glossary_db import (
    GlossaryTermCreate,
    GlossaryTermUpdate,
    GlossaryTermResponse,
    GlossaryTermListResponse,
    TranslationUpdate,
    GlossaryCandidateListResponse,
    CandidateReviewRequest,
    GlossaryCandidateResponse,
    GlossaryExtractRequest,
    GlossaryExtractResponse,
    GlossaryImportRequest,
    GlossaryImportResponse,
    GlossaryExportResponse,
    TranslationFeedbackRequest,
    TranslationFeedbackResponse,
    MatchGlossaryLookupRequest,
    MatchGlossaryLookupResponse,
    GlossarySyncRequest,
    GlossarySyncResponse,
    TermSource,
)


router = APIRouter(prefix="/glossary", tags=["glossary"])


def _check_db_available() -> None:
    """检查数据库是否可用"""
    if not DatabasePool.is_initialized():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库服务不可用",
        )


# ============ 术语 CRUD ============


@router.post(
    "/terms",
    response_model=GlossaryTermResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建术语",
    description="创建新的术语条目",
)
async def create_term(request: GlossaryTermCreate) -> GlossaryTermResponse:
    """
    创建术语

    - **term_en**: 英文术语（必填）
    - **definition**: 术语定义
    - **part_of_speech**: 词性
    - **do_not_translate**: 是否保持原文不翻译
    - **translations**: 各语言翻译，如 {"ja-JP": "コピートレード"}
    """
    _check_db_available()

    try:
        result = await glossary_repository.create_term(request)
        # 使缓存失效
        glossary_service.invalidate_db_cache()
        logger.info(f"[create_term] 创建术语成功: {result.term_id}")
        return result

    except GlossaryTermExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except DatabaseError as e:
        logger.error(f"[create_term] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建术语失败",
        )


@router.get(
    "/terms",
    response_model=GlossaryTermListResponse,
    summary="列出术语",
    description="分页列出术语，支持按状态筛选和关键词搜索",
)
async def list_terms(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status_filter: str | None = Query(default=None, alias="status", description="状态筛选"),
    search: str | None = Query(default=None, description="搜索关键词"),
) -> GlossaryTermListResponse:
    """列出术语"""
    _check_db_available()

    try:
        items, total = await glossary_repository.list_terms(
            page=page,
            page_size=page_size,
            status=status_filter,
            search=search,
        )
        return GlossaryTermListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size,
        )

    except DatabaseError as e:
        logger.error(f"[list_terms] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取术语列表失败",
        )


@router.get(
    "/terms/search",
    response_model=list[GlossaryTermResponse],
    summary="搜索术语",
    description="根据关键词搜索术语，支持英文术语和定义的模糊匹配",
)
async def search_terms(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量限制"),
) -> list[GlossaryTermResponse]:
    """搜索术语"""
    _check_db_available()

    try:
        return await glossary_repository.search_terms(keyword=keyword, limit=limit)

    except DatabaseError as e:
        logger.error(f"[search_terms] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="搜索术语失败",
        )


@router.get(
    "/terms/{term_id}",
    response_model=GlossaryTermResponse,
    summary="获取术语",
    description="根据术语 ID 获取术语详情",
)
async def get_term(term_id: str) -> GlossaryTermResponse:
    """获取术语"""
    _check_db_available()

    try:
        result = await glossary_repository.get_term_by_id(term_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"术语不存在: {term_id}",
            )
        return result

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"[get_term] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取术语失败",
        )


@router.patch(
    "/terms/{term_id}",
    response_model=GlossaryTermResponse,
    summary="更新术语",
    description="更新术语的定义、词性、状态等信息",
)
async def update_term(term_id: str, request: GlossaryTermUpdate) -> GlossaryTermResponse:
    """更新术语"""
    _check_db_available()

    try:
        result = await glossary_repository.update_term(term_id, request)
        # 使缓存失效
        glossary_service.invalidate_db_cache()
        logger.info(f"[update_term] 更新术语成功: {term_id}")
        return result

    except GlossaryTermNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except DatabaseError as e:
        logger.error(f"[update_term] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新术语失败",
        )


@router.delete(
    "/terms/{term_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除术语",
    description="软删除术语（将状态设为 deleted）",
)
async def delete_term(term_id: str) -> None:
    """删除术语"""
    _check_db_available()

    try:
        success = await glossary_repository.delete_term(term_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"术语不存在: {term_id}",
            )
        # 使缓存失效
        glossary_service.invalidate_db_cache()
        logger.info(f"[delete_term] 删除术语成功: {term_id}")

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"[delete_term] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除术语失败",
        )


# ============ 翻译更新 ============


@router.put(
    "/terms/{term_id}/translations/{lang_code}",
    response_model=dict[str, str],
    summary="更新翻译",
    description="更新或添加术语的某个语言翻译",
)
async def update_translation(
    term_id: str,
    lang_code: str,
    request: TranslationUpdate,
) -> dict[str, str]:
    """更新翻译"""
    _check_db_available()

    try:
        result = await glossary_repository.update_translation(term_id, lang_code, request)
        # 使缓存失效
        glossary_service.invalidate_db_cache()
        logger.info(f"[update_translation] 更新翻译成功: {term_id} [{lang_code}]")
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except GlossaryTermNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except DatabaseError as e:
        logger.error(f"[update_translation] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新翻译失败",
        )


# ============ AI 术语提取 ============


@router.post(
    "/extract",
    response_model=GlossaryExtractResponse,
    summary="AI 术语提取",
    description="基于人工翻译结果，使用 AI 提取潜在的专业术语",
)
async def extract_terms(request: GlossaryExtractRequest) -> GlossaryExtractResponse:
    """
    AI 术语提取

    - **source_text**: 原文
    - **human_translation**: 人工翻译
    - **target_lang**: 目标语言
    - **translation_job_id**: 可选，关联的翻译任务 ID
    """
    _check_db_available()

    try:
        async with GlossaryExtractionAgent() as agent:
            result = await agent.run(request)
        logger.info(
            f"[extract_terms] 提取完成: 术语={len(result.extracted_terms)}, "
            f"入库={result.candidates_created}"
        )
        return result

    except Exception as e:
        logger.error(f"[extract_terms] 提取失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="术语提取失败",
        )


# ============ 候选术语管理 ============


@router.get(
    "/candidates",
    response_model=GlossaryCandidateListResponse,
    summary="列出候选术语",
    description="分页列出 AI 提取的候选术语，支持按状态筛选",
)
async def list_candidates(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status_filter: str | None = Query(
        default=None, alias="status", description="状态筛选: pending/approved/rejected/migrated"
    ),
) -> GlossaryCandidateListResponse:
    """列出候选术语"""
    _check_db_available()

    try:
        items, total = await glossary_repository.list_candidates(
            page=page,
            page_size=page_size,
            status=status_filter,
        )
        return GlossaryCandidateListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size,
        )

    except DatabaseError as e:
        logger.error(f"[list_candidates] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取候选术语列表失败",
        )


@router.post(
    "/candidates/{candidate_id}/review",
    response_model=GlossaryCandidateResponse,
    summary="审核候选术语",
    description="批准或拒绝候选术语。批准后术语将自动入库",
)
async def review_candidate(
    candidate_id: int,
    request: CandidateReviewRequest,
) -> GlossaryCandidateResponse:
    """
    审核候选术语

    - **action**: approved（批准）或 rejected（拒绝）
    - **translations**: 确认的翻译（批准时可选，用于覆盖候选翻译）
    - **migrate_to_match**: 是否迁移到 Match Glossary
    - **migrate_to_business**: 是否迁移到 Business Glossary
    """
    _check_db_available()

    try:
        result = await glossary_repository.review_candidate(
            candidate_id=candidate_id,
            action=request.action,
            translations=request.translations,
            migrate_to_match=request.migrate_to_match,
            migrate_to_business=request.migrate_to_business,
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"候选术语不存在: {candidate_id}",
            )
        # 使缓存失效
        glossary_service.invalidate_db_cache()
        logger.info(
            f"[review_candidate] 审核完成: {candidate_id} -> {request.action.value}"
        )
        return result

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"[review_candidate] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="审核候选术语失败",
        )


# ============ 导入导出 ============


@router.post(
    "/import",
    response_model=GlossaryImportResponse,
    summary="导入术语",
    description="批量导入术语，支持覆盖已存在的术语",
)
async def import_terms(request: GlossaryImportRequest) -> GlossaryImportResponse:
    """
    导入术语

    - **terms**: 术语列表
    - **overwrite**: 是否覆盖已存在的术语
    """
    _check_db_available()

    try:
        imported, skipped, errors = await glossary_repository.import_terms(
            terms=request.terms,
            overwrite=request.overwrite,
        )
        # 使缓存失效
        glossary_service.invalidate_db_cache()
        logger.info(
            f"[import_terms] 导入完成: 成功={imported}, 跳过={skipped}, 错误={len(errors)}"
        )
        return GlossaryImportResponse(
            imported=imported,
            skipped=skipped,
            errors=errors,
        )

    except DatabaseError as e:
        logger.error(f"[import_terms] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="导入术语失败",
        )


@router.get(
    "/export",
    response_model=GlossaryExportResponse,
    summary="导出术语",
    description="导出所有激活状态的术语",
)
async def export_terms() -> GlossaryExportResponse:
    """导出术语"""
    _check_db_available()

    try:
        terms = await glossary_repository.get_all_active_terms()
        logger.info(f"[export_terms] 导出完成: {len(terms)} 条术语")
        return GlossaryExportResponse(
            terms=terms,
            exported_at=datetime.now(),
            total=len(terms),
        )

    except DatabaseError as e:
        logger.error(f"[export_terms] 数据库错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="导出术语失败",
        )


# ============ 缓存管理 ============


@router.post(
    "/cache/invalidate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="清除缓存",
    description="清除术语表缓存，强制下次请求从数据库重新加载",
)
async def invalidate_cache() -> None:
    """清除缓存"""
    glossary_service.invalidate_db_cache()
    logger.info("[invalidate_cache] 缓存已清除")


# ============ Two-Tier Glossary System ============


@router.post(
    "/update-from-translation",
    response_model=TranslationFeedbackResponse,
    summary="Update glossaries from translation",
    description="""
    Update glossaries based on translation feedback.

    This endpoint performs two operations:
    1. Writes source text and its translations to Match Glossary (overwritable)
    2. Optionally extracts business terms via AI to Candidate Glossary

    Use this endpoint after a translation is approved or finalized.
    """,
)
async def update_glossary_from_translation(
    request: TranslationFeedbackRequest,
) -> TranslationFeedbackResponse:
    """
    Update glossaries from translation result.

    - **source_text**: Original English text
    - **translations**: Dict of {lang_code: translated_text}
    - **translation_job_id**: Optional job ID for tracking
    - **extract_business_terms**: Whether to run AI extraction (default: True)
    """
    _check_db_available()

    from app.services.match_glossary_service import match_glossary_service

    errors: list[str] = []
    match_updated = 0
    candidates_created = 0

    # Step 1: Update Match Glossary with direct translations
    try:
        # For Match Glossary, we use the source_text itself as the term
        # This allows direct lookup and replacement
        success = await match_glossary_service.upsert_translations_batch(
            term_en=request.source_text.strip(),
            translations=request.translations,
            source="translation_feedback",
        )
        if success:
            match_updated = 1
            logger.info(
                f"[update_glossary_from_translation] Match glossary updated for: "
                f"{request.source_text[:50]}..."
            )
    except Exception as e:
        error_msg = f"Match glossary update failed: {e}"
        errors.append(error_msg)
        logger.error(f"[update_glossary_from_translation] {error_msg}")

    # Step 2: Extract business terms via AI (optional)
    if request.extract_business_terms:
        try:
            # Use the first available translation for extraction
            if request.translations:
                first_lang = next(iter(request.translations))
                human_translation = request.translations[first_lang]

                extract_request = GlossaryExtractRequest(
                    source_text=request.source_text,
                    human_translation=human_translation,
                    target_lang=first_lang,
                    translation_job_id=request.translation_job_id,
                )

                async with GlossaryExtractionAgent() as agent:
                    result = await agent.run(extract_request)
                    candidates_created = result.candidates_created

                logger.info(
                    f"[update_glossary_from_translation] Extracted {candidates_created} "
                    f"candidate terms"
                )

        except Exception as e:
            error_msg = f"Business term extraction failed: {e}"
            errors.append(error_msg)
            logger.warning(f"[update_glossary_from_translation] {error_msg}")

    # Invalidate caches
    glossary_service.invalidate_db_cache()
    match_glossary_service.invalidate_cache()

    return TranslationFeedbackResponse(
        match_glossary_updated=match_updated,
        candidates_created=candidates_created,
        errors=errors,
    )


@router.get(
    "/match/lookup",
    response_model=MatchGlossaryLookupResponse,
    summary="Look up Match Glossary translation",
    description="Direct lookup for a term translation in the Match Glossary (Level 1)",
)
async def lookup_match_glossary(
    term: str = Query(..., min_length=1, alias="term", description="English term to look up"),
    lang: str = Query(..., min_length=2, alias="lang", description="Target language code"),
) -> MatchGlossaryLookupResponse:
    """
    Look up a direct translation from Match Glossary.

    - **term**: English term to look up
    - **lang**: Target language code (e.g., ja-JP, ko-KR)
    """
    _check_db_available()

    from app.services.match_glossary_service import match_glossary_service

    try:
        translation = await match_glossary_service.lookup_translation(term, lang)
        return MatchGlossaryLookupResponse(
            term_en=term,
            target_lang=lang,
            translation=translation,
            found=translation is not None,
        )

    except Exception as e:
        logger.error(f"[lookup_match_glossary] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Match glossary lookup failed",
        )


# ============ Glossary Sync (Tolgee Integration) ============


@router.post(
    "/sync",
    response_model=GlossarySyncResponse,
    summary="Sync glossary from Tolgee",
    description=(
        "Receive glossary data from Tolgee and upsert into the appropriate "
        "glossary tier (L1 Match or L2 Business)."
    ),
)
async def sync_glossary(request: GlossarySyncRequest) -> GlossarySyncResponse:
    """
    Sync glossary from Tolgee platform.

    - **glossary_level**: L1_MATCH or L2_BUSINESS
    - **organization_id**: Tolgee organization ID
    - **glossary_id**: Tolgee glossary ID
    - **terms**: List of terms with translations
    """
    _check_db_available()

    from app.services.match_glossary_service import match_glossary_service

    errors: list[str] = []
    synced = 0

    for term in request.terms:
        try:
            if request.glossary_level == "L1_MATCH":
                # L1: upsert into match_glossary_terms
                success = await match_glossary_service.upsert_translations_batch(
                    term_en=term.term_text,
                    translations=term.translations,
                    source="tolgee_sync",
                )
                if success:
                    synced += 1
            else:
                # L2: upsert into business_glossary_terms (database terms)
                existing = None
                try:
                    search_results = await glossary_repository.search_terms(
                        keyword=term.term_text, limit=1
                    )
                    if search_results and search_results[0].term_en == term.term_text:
                        existing = search_results[0]
                except Exception:
                    pass

                if existing:
                    # Update translations
                    for lang, text in term.translations.items():
                        try:
                            await glossary_repository.update_translation(
                                existing.term_id,
                                lang,
                                TranslationUpdate(translation=text),
                            )
                        except Exception:
                            pass
                else:
                    # Create new term
                    await glossary_repository.create_term(
                        GlossaryTermCreate(
                            term_en=term.term_text,
                            definition=term.description,
                            translations=term.translations,
                            source=TermSource.IMPORTED,
                        )
                    )
                synced += 1

        except Exception as e:
            error_msg = f"Failed to sync term '{term.term_text}': {e}"
            errors.append(error_msg)
            logger.warning(f"[sync_glossary] {error_msg}")

    # Invalidate caches
    glossary_service.invalidate_db_cache()
    if request.glossary_level == "L1_MATCH":
        match_glossary_service.invalidate_cache()

    logger.info(
        f"[sync_glossary] Sync complete: level={request.glossary_level}, "
        f"synced={synced}, errors={len(errors)}"
    )

    return GlossarySyncResponse(synced=synced, errors=errors)
