"""
术语表格式转换脚本

将 data/glossary.csv 转换为 YAML 和 JSON 格式
结构：术语（英文） -> 语言代码 -> 翻译
"""

import csv
import json
import yaml
from pathlib import Path


# CSV 列名到语言代码的映射（12 种目标语言）
LANG_COLUMN_MAPPING: dict[str, str] = {
    "Term English (United States) [en-US] en-US": "en-US",
    "Term Arabic (International) [ar] ar": "ar",
    "Term French (France) [fr-FR] fr-FR": "fr-FR",
    "Term German (Germany) [de-DE] de-DE": "de-DE",
    "Term Indonesian (Indonesia) [id-ID] id-ID": "id-ID",
    "Term Japanese (Japan) [ja-JP] ja-JP": "ja-JP",
    "Term Korean (South Korea) [ko-KR] ko-KR": "ko-KR",
    "Term Russian (Russia) [ru-RU] ru-RU": "ru-RU",
    "Term Spanish (Spain) [es-ES] es-ES": "es-ES",
    "Term Vietnamese (Vietnam) [vi-VN] vi-VN": "vi-VN",
    "Term Portuguese (Brazil) [pt-BR] pt-BR": "pt-BR",
}

# Do Not Translate 列名映射
DO_NOT_TRANSLATE_COLUMNS: dict[str, str] = {
    "Do Not Translate English (United States) [en-US] en-US": "en-US",
    "Do Not Translate Arabic (International) [ar] ar": "ar",
    "Do Not Translate French (France) [fr-FR] fr-FR": "fr-FR",
    "Do Not Translate German (Germany) [de-DE] de-DE": "de-DE",
    "Do Not Translate Indonesian (Indonesia) [id-ID] id-ID": "id-ID",
    "Do Not Translate Japanese (Japan) [ja-JP] ja-JP": "ja-JP",
    "Do Not Translate Korean (South Korea) [ko-KR] ko-KR": "ko-KR",
    "Do Not Translate Russian (Russia) [ru-RU] ru-RU": "ru-RU",
    "Do Not Translate Spanish (Spain) [es-ES] es-ES": "es-ES",
    "Do Not Translate Vietnamese (Vietnam) [vi-VN] vi-VN": "vi-VN",
    "Do Not Translate Portuguese (Brazil) [pt-BR] pt-BR": "pt-BR",
}


def convert_glossary(csv_path: Path, output_dir: Path) -> dict[str, dict[str, str]]:
    """
    转换术语表 CSV 为字典结构

    Args:
        csv_path: CSV 文件路径
        output_dir: 输出目录

    Returns:
        术语字典 {term_en: {lang_code: translation}}
    """
    glossary: dict[str, dict[str, str]] = {}

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # 获取英文术语
            term_en = ""
            for col_name, lang_code in LANG_COLUMN_MAPPING.items():
                if lang_code == "en-US" and col_name in row:
                    term_en = row[col_name].strip()
                    break

            if not term_en:
                continue

            # 跳过重复术语（保留第一个）
            if term_en in glossary:
                continue

            translations: dict[str, str] = {}

            # 检查全局 Do Not Translate 标记（英文列）
            global_dnt = False
            for col_name, lang_code in DO_NOT_TRANSLATE_COLUMNS.items():
                if lang_code == "en-US" and col_name in row:
                    global_dnt = row[col_name].strip().upper() == "TRUE"
                    break

            # 获取各语言翻译
            for col_name, lang_code in LANG_COLUMN_MAPPING.items():
                if col_name not in row:
                    continue

                term_value = row[col_name].strip()

                # 检查该语言是否标记为 Do Not Translate
                dnt_col = None
                for dnt_col_name, dnt_lang in DO_NOT_TRANSLATE_COLUMNS.items():
                    if dnt_lang == lang_code:
                        dnt_col = dnt_col_name
                        break

                is_dnt = False
                if dnt_col and dnt_col in row:
                    is_dnt = row[dnt_col].strip().upper() == "TRUE"

                # 如果是 Do Not Translate 或全局 DNT，使用英文术语
                if is_dnt or global_dnt:
                    translations[lang_code] = term_en
                elif term_value:
                    translations[lang_code] = term_value
                else:
                    # 没有翻译时，如果全局 DNT 则用英文，否则留空
                    if global_dnt:
                        translations[lang_code] = term_en

            # 确保 en-US 始终存在
            if "en-US" not in translations:
                translations["en-US"] = term_en

            glossary[term_en] = translations

    return glossary


def save_glossary(glossary: dict[str, dict[str, str]], output_dir: Path) -> None:
    """保存术语表为 YAML 和 JSON 格式"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存 JSON
    json_path = output_dir / "glossary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2)
    print(f"已保存 JSON: {json_path}")

    # 保存 YAML
    yaml_path = output_dir / "glossary.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            glossary,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    print(f"已保存 YAML: {yaml_path}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="转换术语表 CSV 为 JSON/YAML 格式")
    parser.add_argument(
        "--input",
        "-i",
        default="data/glossary.csv",
        help="输入 CSV 文件路径 (默认: data/glossary.csv)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data",
        help="输出目录 (默认: data)",
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    csv_path = base_dir / args.input
    output_dir = base_dir / args.output

    if not csv_path.exists():
        print(f"错误: CSV 文件不存在: {csv_path}")
        return

    print(f"正在转换: {csv_path}")
    glossary = convert_glossary(csv_path, output_dir)
    print(f"共转换 {len(glossary)} 个术语")

    save_glossary(glossary, output_dir)
    print("转换完成!")


if __name__ == "__main__":
    main()
