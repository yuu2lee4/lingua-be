"""
Glossary translation column helpers.

Provides a single mapping between language codes and translation column names
for the glossary tables (match, business, candidates).
"""

from __future__ import annotations

from typing import Any

from app.core.constants import LanguageCode


LANGUAGE_CODES: list[str] = [code.value for code in LanguageCode]

# Translation columns for all supported languages (including en-US if needed).
LANG_CODE_TO_COLUMN: dict[str, str] = {
    code: f"translation_{code.lower().replace('-', '_')}" for code in LANGUAGE_CODES
}

COLUMN_TO_LANG_CODE: dict[str, str] = {v: k for k, v in LANG_CODE_TO_COLUMN.items()}

TRANSLATION_COLUMNS: list[str] = list(LANG_CODE_TO_COLUMN.values())


def normalize_lang_code(lang_code: str) -> str:
    """Normalize language code for lookups."""
    return lang_code.strip()


def get_translation_column(lang_code: str) -> str | None:
    """Return translation column name for a language code."""
    return LANG_CODE_TO_COLUMN.get(normalize_lang_code(lang_code))


def build_translation_columns(translations: dict[str, str]) -> dict[str, str]:
    """
    Convert translation dict {lang_code: translation} to {column: translation}.

    Unsupported language codes are ignored.
    """
    result: dict[str, str] = {}
    for lang_code, value in translations.items():
        column = get_translation_column(lang_code)
        if not column:
            continue
        result[column] = value
    return result


def extract_translations(row: dict[str, Any]) -> dict[str, str]:
    """Extract translations dict from a database row."""
    translations: dict[str, str] = {}
    for lang_code, column in LANG_CODE_TO_COLUMN.items():
        value = row.get(column)
        if value:
            translations[lang_code] = value
    return translations


def require_translation_column(lang_code: str) -> str:
    """Get translation column name, raising ValueError if unsupported."""
    column = get_translation_column(lang_code)
    if not column:
        raise ValueError(f"Unsupported language code: {lang_code}")
    return column
