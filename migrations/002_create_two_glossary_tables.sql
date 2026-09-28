-- Migration: Create two-tier glossary system tables
--
-- Match Glossary (匹配术语库): Direct translation lookup with exact matches
-- Business AI Glossary (业务AI术语库): AI-curated professional terms for prompt enrichment
-- Glossary Candidates (术语候选池): AI-extracted term candidates for human review
--
-- Supported 14 target languages:
--   ar, de-DE, en-US, es-ES, fr-FR, id-ID, ja-JP, ko-KR, pt-BR, ru-RU, uk-UA, vi-VN, zh-CN, zh-TW
--
-- Run this migration after 001_create_glossary_tables.sql

-- ============ Match Glossary Tables (direct translation lookup) ============

CREATE TABLE IF NOT EXISTS match_glossary_terms (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    term_id VARCHAR(128) NOT NULL DEFAULT '' COMMENT '术语唯一标识(MD5)',
    term_en VARCHAR(512) NOT NULL DEFAULT '' COMMENT '英文原文术语',
    translation_ar VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '阿拉伯语翻译',
    translation_de_de VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '德语翻译',
    translation_en_us VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '英语(美国)翻译',
    translation_es_es VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '西班牙语翻译',
    translation_fr_fr VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '法语翻译',
    translation_id_id VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '印尼语翻译',
    translation_ja_jp VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '日语翻译',
    translation_ko_kr VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '韩语翻译',
    translation_pt_br VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '葡萄牙语(巴西)翻译',
    translation_ru_ru VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '俄语翻译',
    translation_uk_ua VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '乌克兰语翻译',
    translation_vi_vn VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '越南语翻译',
    translation_zh_cn VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '简体中文翻译',
    translation_zh_tw VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '繁体中文翻译',
    `source` VARCHAR(64) NOT NULL DEFAULT 'imported' COMMENT '来源: imported/ai_extracted/manual',
    `status` VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '状态: active/inactive',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uniq_term_id (term_id),
    INDEX idx_term_en (term_en),
    INDEX idx_status (`status`)
) COMMENT='匹配术语库-L1直接翻译查找表';

-- ============ Business AI Glossary Tables (AI-curated terms for prompt enrichment) ============

CREATE TABLE IF NOT EXISTS business_glossary_terms (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    term_id VARCHAR(128) NOT NULL DEFAULT '' COMMENT '术语唯一标识(MD5)',
    term_en VARCHAR(512) NOT NULL DEFAULT '' COMMENT '英文原文术语',
    `definition` TEXT COMMENT '术语定义/上下文说明',
    part_of_speech VARCHAR(32) NOT NULL DEFAULT '' COMMENT '词性: noun/verb/adjective等',
    do_not_translate TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否禁止翻译: 0=可翻译, 1=保留原文',
    translation_ar VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '阿拉伯语翻译',
    translation_de_de VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '德语翻译',
    translation_en_us VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '英语(美国)翻译',
    translation_es_es VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '西班牙语翻译',
    translation_fr_fr VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '法语翻译',
    translation_id_id VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '印尼语翻译',
    translation_ja_jp VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '日语翻译',
    translation_ko_kr VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '韩语翻译',
    translation_pt_br VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '葡萄牙语(巴西)翻译',
    translation_ru_ru VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '俄语翻译',
    translation_uk_ua VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '乌克兰语翻译',
    translation_vi_vn VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '越南语翻译',
    translation_zh_cn VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '简体中文翻译',
    translation_zh_tw VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '繁体中文翻译',
    `source` VARCHAR(64) NOT NULL DEFAULT 'imported' COMMENT '来源: imported/ai_extracted/manual',
    `status` VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '状态: active/inactive/deleted',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uniq_term_id (term_id),
    INDEX idx_term_en (term_en),
    INDEX idx_status (`status`)
) COMMENT='业务AI术语库-L2 AI策编术语表';

-- ============ Glossary Candidates Table (AI-extracted term candidates for review) ============

CREATE TABLE IF NOT EXISTS glossary_candidates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    term_id VARCHAR(128) NOT NULL DEFAULT '' COMMENT '术语唯一标识(MD5)',
    term_en VARCHAR(512) NOT NULL DEFAULT '' COMMENT '英文原文术语',
    `definition` TEXT COMMENT '术语定义/上下文说明',
    part_of_speech VARCHAR(32) NOT NULL DEFAULT '' COMMENT '词性: noun/verb/adjective等',
    do_not_translate TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否禁止翻译: 0=可翻译, 1=保留原文',
    translation_ar VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '阿拉伯语翻译',
    translation_de_de VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '德语翻译',
    translation_en_us VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '英语(美国)翻译',
    translation_es_es VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '西班牙语翻译',
    translation_fr_fr VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '法语翻译',
    translation_id_id VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '印尼语翻译',
    translation_ja_jp VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '日语翻译',
    translation_ko_kr VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '韩语翻译',
    translation_pt_br VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '葡萄牙语(巴西)翻译',
    translation_ru_ru VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '俄语翻译',
    translation_uk_ua VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '乌克兰语翻译',
    translation_vi_vn VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '越南语翻译',
    translation_zh_cn VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '简体中文翻译',
    translation_zh_tw VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '繁体中文翻译',
    `source` VARCHAR(64) NOT NULL DEFAULT 'ai_extracted' COMMENT '来源: ai_extracted',
    `status` VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/approved/rejected/migrated',
    migrated_to_match_glossary TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已迁移到匹配术语库: 0=否, 1=是',
    migrated_to_business_glossary TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已迁移到业务术语库: 0=否, 1=是',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uniq_term_id (term_id),
    INDEX idx_status (`status`),
    INDEX idx_term_en (term_en),
    INDEX idx_created_at (created_at)
) COMMENT='术语候选池-AI提取待人工审核';
