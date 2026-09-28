"""
Binance 多语言术语爬取工具

从 Binance 网站提取多语言翻译内容，构建交易所业务术语库。

策略:
  Phase 1 — 网络拦截：通过 Playwright 拦截页面加载时的 i18n/翻译 API 请求
  Phase 2 — 资源下载：对发现的翻译 API，请求所有支持语言的版本
  Phase 3 — DOM 提取：遍历关键页面，在不同语言下提取导航/按钮/标题等可见文本
  Phase 4 — 合并输出：去重合并为标准术语库 JSON

用法:
  uv run python scripts/crawl_binance_glossary.py [--languages en,zh-CN,ja] [--pages 5]
"""

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from playwright.async_api import async_playwright, Page, BrowserContext, Response


# ============ 配置 ============

BASE_URL = "https://www.binance.com"

# Binance 支持的语言（Binance URL locale code → 显示名称）
BINANCE_LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt-BR": "Português (Brasil)",
    "vi": "Tiếng Việt",
    "ar": "العربية",
    "id": "Bahasa Indonesia",
    "uk-UA": "Українська",
}

# 关键页面路径（不含语言前缀）
BINANCE_KEY_PATHS: list[str] = [
    "/",
    "/markets/overview",
    "/trade/BTCUSDT",
    "/futures/BTCUSDT",
    "/earn",
    "/copy-trading",
    "/square",
    "/nft",
    "/pay",
    "/gift-card",
    "/convert",
    "/otc",
    "/support/faq",
]

OUTPUT_DIR = Path("data/binance_glossary")


# ============ Phase 1: 网络拦截发现 i18n 资源 ============


class I18nResourceDiscoverer:
    """通过拦截网络请求发现 Binance 的 i18n 翻译资源"""

    def __init__(self) -> None:
        self.captured_urls: list[str] = []
        self.captured_responses: dict[str, dict] = {}  # url -> json body
        # i18n 相关的 URL 模式
        self._patterns = [
            r"/bapi/composite/v1/.*translat",
            r"/bapi/composite/v1/.*i18n",
            r"/bapi/composite/v1/.*locale",
            r"/bapi/composite/v1/.*language",
            r"i18n",
            r"locale",
            r"translation",
            r"messages",
            r"lang.*\.json",
        ]

    def matches_i18n_pattern(self, url: str) -> bool:
        """检查 URL 是否匹配 i18n 模式"""
        for pattern in self._patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    async def on_response(self, response: Response) -> None:
        """拦截网络响应"""
        url = response.url
        if not self.matches_i18n_pattern(url):
            return

        content_type = response.headers.get("content-type", "")
        if "json" not in content_type and "javascript" not in content_type:
            return

        try:
            body = await response.json()
            self.captured_urls.append(url)
            self.captured_responses[url] = body
            print(f"  [i18n] 捕获翻译资源: {url[:120]}...")
        except Exception:
            pass


async def discover_i18n_resources(
    context: BrowserContext,
    pages_to_visit: int = 3,
) -> I18nResourceDiscoverer:
    """
    Phase 1: 访问 Binance 关键页面，拦截网络请求发现 i18n 翻译资源

    Args:
        context: Playwright 浏览器上下文
        pages_to_visit: 访问的页面数量（用于发现更多资源）

    Returns:
        I18nResourceDiscoverer 包含捕获的翻译资源
    """
    discoverer = I18nResourceDiscoverer()
    page = await context.new_page()
    page.on("response", discoverer.on_response)

    paths_to_try = BINANCE_KEY_PATHS[:pages_to_visit]

    for path in paths_to_try:
        url = f"{BASE_URL}/en{path}" if path != "/" else f"{BASE_URL}/en"
        print(f"[Phase1] 访问 {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # 等待 WAF challenge 通过 + SPA 渲染
            await page.wait_for_timeout(8000)
            # 检查是否通过了 WAF challenge（页面应该有正常内容）
            title = await page.title()
            print(f"  页面标题: {title}")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  [warn] 页面加载超时或失败: {e}")
            try:
                await page.wait_for_timeout(8000)
            except Exception:
                pass

    await page.close()
    print(
        f"[Phase1] 共捕获 {len(discoverer.captured_urls)} 个 i18n 资源 URL"
    )
    return discoverer


# ============ Phase 2: 下载所有语言的翻译资源 ============


async def download_i18n_for_all_languages(
    context: BrowserContext,
    discoverer: I18nResourceDiscoverer,
    target_languages: list[str],
) -> dict[str, dict[str, str]]:
    """
    Phase 2: 基于发现的 i18n API，下载所有语言版本

    从捕获的 URL 中提取 i18n 模块名，然后请求所有语言版本。

    Returns:
        {translation_key: {lang_code: translated_text}}
    """
    glossary: dict[str, dict[str, str]] = {}

    if not discoverer.captured_urls:
        print("[Phase2] 未发现 i18n API，跳过")
        return glossary

    # 提取去重的 i18n 模块名和基础 URL 模式
    modules: dict[str, str] = {}  # module_name -> template_url (with {lang})
    for url in discoverer.captured_urls:
        # https://bin.bnbstatic.com/api/i18n/-/web/cms/en/ModuleName
        match = re.search(r"/api/i18n/-/web/cms/([^/]+)/(.+?)(?:\?|$)", url)
        if match:
            lang_in_url = match.group(1)
            module_name = match.group(2)
            template = url.replace(f"/{lang_in_url}/", "/{lang}/")
            modules[module_name] = template

    print(f"[Phase2] 发现 {len(modules)} 个去重模块: {list(modules.keys())}")

    page = await context.new_page()

    for module_name, url_template in modules.items():
        print(f"[Phase2] 模块: {module_name}")

        # 先获取英文版本
        en_url = url_template.replace("{lang}", "en")
        original_data = discoverer.captured_responses.get(en_url)
        if not original_data:
            # 从捕获的响应中找到这个模块的数据
            for captured_url, data in discoverer.captured_responses.items():
                if module_name in captured_url:
                    original_data = data
                    break

        if original_data:
            flat_en = _flatten_json(original_data, prefix="")
            if flat_en:
                print(f"  英文: {len(flat_en)} 个翻译键")
                for key, value in flat_en.items():
                    if isinstance(value, str) and value.strip():
                        if key not in glossary:
                            glossary[key] = {}
                        glossary[key]["en"] = value

        # 获取其他语言版本
        for lang in target_languages:
            if lang == "en":
                continue

            lang_url = url_template.replace("{lang}", lang)

            try:
                resp = await page.goto(lang_url, wait_until="load", timeout=15000)
                if resp and resp.ok:
                    try:
                        data = await resp.json()
                        flat = _flatten_json(data, prefix="")
                        for key, value in flat.items():
                            if isinstance(value, str) and value.strip():
                                if key not in glossary:
                                    glossary[key] = {}
                                glossary[key][lang] = value
                        print(f"  [{lang}] {len(flat)} 个翻译")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  [{lang}] 请求失败: {e}")

    await page.close()
    print(f"[Phase2] 共获取 {len(glossary)} 个翻译键")
    return glossary


def _replace_language_in_url(url: str, from_lang: str, to_lang: str) -> str:
    """尝试替换 URL 中的语言代码"""
    # 替换路径中的语言前缀
    new_url = url.replace(f"/{from_lang}/", f"/{to_lang}/")
    # 替换查询参数中的语言
    new_url = re.sub(
        rf"(lang|locale|language)={re.escape(from_lang)}",
        rf"\1={to_lang}",
        new_url,
    )
    return new_url


def _flatten_json(
    data: dict | list | str, prefix: str = ""
) -> dict[str, str]:
    """将嵌套 JSON 展平为 {key_path: value} 字典"""
    result: dict[str, str] = {}

    if isinstance(data, dict):
        # 跳过 Binance API 的外层包装 (code, data, message 等)
        if "data" in data and isinstance(data["data"], (dict, list)):
            return _flatten_json(data["data"], prefix)

        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str):
                result[new_key] = value
            elif isinstance(value, dict):
                result.update(_flatten_json(value, new_key))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    result.update(_flatten_json(item, f"{new_key}[{i}]"))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            result.update(_flatten_json(item, f"{prefix}[{i}]"))

    return result


# ============ Phase 3: DOM 文本提取 ============


async def extract_page_texts(
    context: BrowserContext,
    target_languages: list[str],
    key_paths: list[str],
    max_pages: int = 5,
) -> dict[str, dict[str, dict[str, str]]]:
    """
    Phase 3: 遍历关键页面，在不同语言下提取可见文本

    使用元素的语言无关属性（href、data-testid、id、aria-label）作为对齐键，
    避免按索引位置对齐导致的跨语言错位问题。

    Returns:
        {path: {lang: {alignment_key: text}}}
    """
    all_texts: dict[str, dict[str, dict[str, str]]] = {}
    page = await context.new_page()

    paths = key_paths[:max_pages]

    for path in paths:
        all_texts[path] = {}

        for lang in target_languages:
            url_path = path if path != "/" else ""
            url = f"{BASE_URL}/{lang}{url_path}"
            print(f"[Phase3] 提取文本: {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # 等待 WAF challenge + SPA 渲染
                await page.wait_for_timeout(8000)

                # 提取关键 UI 文本元素（基于属性对齐）
                texts = await page.evaluate("""() => {
                    const result = {};
                    const langPrefix = location.pathname.split('/')[1] || 'en';

                    function addEntry(el, type) {
                        const text = el.textContent?.trim();
                        if (!text || text.length < 2 || text.length > 200) return;

                        let key = null;

                        // 优先用 href（链接元素最可靠的跨语言标识）
                        if (el.tagName === 'A' && el.getAttribute('href')) {
                            const href = el.getAttribute('href');
                            // 去除语言前缀: /en/trade -> /trade, /zh-CN/earn -> /earn
                            key = 'href:' + href.replace(new RegExp('^/' + langPrefix + '(/|$)'), '/');
                        }

                        // data-testid / data-bn-type（React 组件稳定标识）
                        if (!key) {
                            const testId = el.getAttribute('data-testid') || el.getAttribute('data-bn-type');
                            if (testId) key = 'tid:' + testId;
                        }

                        // id 属性
                        if (!key && el.id) {
                            key = 'id:' + el.id;
                        }

                        // aria-label（通常是英文固定值）
                        if (!key) {
                            const ariaLabel = el.getAttribute('aria-label');
                            if (ariaLabel) key = 'aria:' + ariaLabel;
                        }

                        // 无法获取稳定 key 的元素直接跳过（避免错位）
                        if (!key) return;

                        // 加上元素类型前缀防止不同类型元素 key 冲突
                        const fullKey = type + '|' + key;
                        if (!result[fullKey]) {
                            result[fullKey] = text;
                        }
                    }

                    // 导航栏链接
                    document.querySelectorAll('nav a, header a, [class*="nav"] a, [class*="Nav"] a').forEach(el => addEntry(el, 'nav'));
                    // 按钮
                    document.querySelectorAll('button, [role="button"]').forEach(el => addEntry(el, 'btn'));
                    // 标题
                    document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(el => addEntry(el, 'heading'));
                    // 链接
                    document.querySelectorAll('a[href]').forEach(el => addEntry(el, 'link'));
                    // Tab
                    document.querySelectorAll('[role="tab"]').forEach(el => addEntry(el, 'tab'));
                    // 表头
                    document.querySelectorAll('th, [role="columnheader"]').forEach(el => addEntry(el, 'th'));

                    return result;
                }""")

                all_texts[path][lang] = texts
                total = len(texts)
                print(f"  [{lang}] 提取到 {total} 个带 key 的文本片段")

            except Exception as e:
                print(f"  [{lang}] 提取失败: {e}")
                all_texts[path][lang] = {}

    await page.close()
    return all_texts


# ============ Phase 4: 合并构建术语库 ============


def build_glossary_from_dom_texts(
    page_texts: dict[str, dict[str, dict[str, str]]],
    reference_lang: str = "en",
) -> list[dict]:
    """
    从 DOM 提取的文本中构建术语对照表，基于元素属性对齐

    策略：以英文文本为基准，通过相同的 alignment_key 匹配其他语言的翻译，
    避免按索引位置对齐导致的错位问题（如 APR→四月）。
    """
    terms: dict[str, dict[str, str]] = {}  # {en_text: {lang: text}}

    for path, lang_data in page_texts.items():
        ref_texts = lang_data.get(reference_lang, {})
        if not ref_texts:
            continue

        for key, en_text in ref_texts.items():
            en_clean = en_text.strip()
            if not en_clean or len(en_clean) < 2:
                continue

            if en_clean not in terms:
                terms[en_clean] = {"en": en_clean}

            # 用相同的 key 在其他语言中查找翻译
            for lang, lang_texts in lang_data.items():
                if lang == reference_lang:
                    continue
                lang_text = lang_texts.get(key, "").strip()
                if lang_text and lang_text != en_clean:
                    terms[en_clean][lang] = lang_text

    return [
        {"term_en": en_text, "translations": translations}
        for en_text, translations in terms.items()
        if len(translations) > 1  # 至少有一个翻译
    ]


def _clean_text(text: str) -> str:
    """清理文本：去除 HTML 标签、多余空白"""
    # 去除 HTML 标签
    cleaned = re.sub(r"<[^>]+>", "", text)
    # 合并多余空白
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _is_noise(text: str) -> bool:
    """判断文本是否为噪音数据"""
    # 纯数字/符号/价格
    if re.match(r"^[\d\s\.\-\+\*\/\%\$\#\@\!\?\,\;\:\(\)]+$", text):
        return True
    # 价格模式 $123.45
    if re.match(r"^\$[\d\.,]+[KMBT]?$", text):
        return True
    # 百分比
    if re.match(r"^[\+\-]?\d+\.?\d*%$", text):
        return True
    # 纯加密货币代码拼接（如 BNBBNB628.53...）
    if re.match(r"^[A-Z]{2,}[A-Z]{2,}\d", text):
        return True
    # 太短（单个字符或数字）
    if len(text) < 2:
        return True
    # 太长（超过 300 字符可能是整段内容）
    if len(text) > 300:
        return True
    # URL
    if text.startswith("http://") or text.startswith("https://"):
        return True
    # 变量占位符：$name$, {amount}, {{var}}
    if re.search(r"\$\w+\$|\{\w+\}", text):
        return True
    # 区块链地址
    if re.search(r"0x[0-9a-fA-F]{8,}", text):
        return True
    # Emoji 开头（营销/活动文案）
    if re.match(r"^[\U0001F300-\U0001FAFF]", text):
        return True
    # 残留 HTML 标签
    if re.search(r"<[a-zA-Z/]", text):
        return True
    return False


# 非拉丁语系语言（翻译不应与英文完全一致）
_NON_LATIN_LANGUAGES = {"zh-CN", "zh-TW", "ja", "ko", "ru", "ar", "uk-UA", "vi"}


def _is_suspicious_translation(lang: str, en_text: str, translated: str) -> bool:
    """检测低质量翻译"""
    # 非拉丁语系翻译与英文完全相同
    if lang in _NON_LATIN_LANGUAGES and translated == en_text:
        return True
    # 长度比例异常（< 0.1 或 > 10）
    en_len = len(en_text)
    tr_len = len(translated)
    if en_len > 0 and tr_len > 0:
        ratio = tr_len / en_len
        if ratio < 0.1 or ratio > 10:
            return True
    return False


# 最低语言覆盖率：翻译不足此数量的术语将被丢弃
MIN_LANGUAGE_COVERAGE = 3


def merge_glossaries(
    i18n_glossary: dict[str, dict[str, str]],
    dom_terms: list[dict],
) -> list[dict]:
    """合并 i18n 资源和 DOM 提取的术语，并清理噪音"""
    merged: dict[str, dict[str, str]] = {}

    # 先加入 i18n 资源的术语
    for key, translations in i18n_glossary.items():
        en_text = _clean_text(translations.get("en", ""))
        if not en_text or _is_noise(en_text):
            continue
        if en_text not in merged:
            merged[en_text] = {}
        for lang, text in translations.items():
            cleaned = _clean_text(text)
            if cleaned:
                merged[en_text][lang] = cleaned

    # 加入 DOM 提取的术语
    for term in dom_terms:
        en_text = _clean_text(term.get("term_en", ""))
        if not en_text or _is_noise(en_text):
            continue
        if en_text not in merged:
            merged[en_text] = {}
        for lang, text in term.get("translations", {}).items():
            cleaned = _clean_text(text)
            if cleaned:
                merged[en_text][lang] = cleaned

    # 转换为标准术语库格式
    result: list[dict] = []
    for en_text, translations in sorted(merged.items()):
        # 过滤掉噪音翻译和可疑翻译
        clean_translations = {
            lang: text
            for lang, text in translations.items()
            if lang != "en"
            and text != en_text
            and not _is_noise(text)
            and not _is_suspicious_translation(lang, en_text, text)
        }

        # 最低语言覆盖率过滤
        if len(clean_translations) < MIN_LANGUAGE_COVERAGE:
            continue

        # 生成 term_id
        term_id = re.sub(r"[^a-zA-Z0-9]+", "_", en_text.lower()).strip("_")
        if len(term_id) > 60:
            term_id = term_id[:60].rstrip("_")

        entry = {
            "term_id": term_id,
            "term_en": en_text,
            "source": "binance.com",
            "translations": clean_translations,
        }
        result.append(entry)

    return result


# ============ 语言代码映射 ============

# Binance 语言代码 → 项目标准语言代码（14 种目标语言）
LANG_CODE_MAP: dict[str, str] = {
    "en": "en-US",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "ru": "ru-RU",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "pt-BR": "pt-BR",
    "vi": "vi-VN",
    "ar": "ar",
    "id": "id-ID",
    "uk-UA": "uk-UA",
}


def normalize_lang_codes(terms: list[dict]) -> list[dict]:
    """将 Binance 语言代码转换为项目标准语言代码，过滤非目标语言"""
    result: list[dict] = []
    for term in terms:
        new_translations = {}
        for lang, text in term.get("translations", {}).items():
            standard_code = LANG_CODE_MAP.get(lang)
            if not standard_code:
                continue  # 非目标语言，丢弃
            if standard_code == "en-US":
                continue  # 英文已在 term_en 字段
            new_translations[standard_code] = text
        if new_translations:
            term["translations"] = new_translations
            result.append(term)
    return result


# ============ 主流程 ============


async def main(
    languages: list[str] | None = None,
    max_pages: int = 5,
    discovery_pages: int = 3,
) -> None:
    """主爬取流程"""
    start_time = time.time()
    target_languages = languages or list(BINANCE_LANGUAGES.keys())

    print("=" * 60)
    print(f"Binance 多语言术语爬取")
    print(f"目标语言: {', '.join(target_languages)}")
    print(f"最大页面数: {max_pages}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # headed 模式绕过 WAF challenge
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--no-proxy-server",  # 绕过系统代理
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        # Phase 1: 发现 i18n 翻译资源
        print("\n--- Phase 1: 发现 i18n 翻译资源 ---")
        discoverer = await discover_i18n_resources(context, discovery_pages)

        # 保存发现的 i18n URL
        if discoverer.captured_urls:
            urls_path = OUTPUT_DIR / "discovered_i18n_urls.json"
            with open(urls_path, "w", encoding="utf-8") as f:
                json.dump(discoverer.captured_urls, f, ensure_ascii=False, indent=2)
            print(f"已保存 {len(discoverer.captured_urls)} 个 i18n URL 到 {urls_path}")

            # 保存原始 i18n 响应
            raw_path = OUTPUT_DIR / "raw_i18n_responses.json"
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(
                    discoverer.captured_responses,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            print(f"已保存原始 i18n 响应到 {raw_path}")

        # Phase 2: 下载所有语言版本的 i18n 资源
        print("\n--- Phase 2: 下载多语言 i18n 资源 ---")
        i18n_glossary = await download_i18n_for_all_languages(
            context, discoverer, target_languages
        )

        # Phase 3: DOM 文本提取
        print("\n--- Phase 3: DOM 文本提取 ---")
        page_texts = await extract_page_texts(
            context, target_languages, BINANCE_KEY_PATHS, max_pages
        )

        # 保存原始 DOM 提取结果
        dom_path = OUTPUT_DIR / "raw_dom_texts.json"
        with open(dom_path, "w", encoding="utf-8") as f:
            json.dump(page_texts, f, ensure_ascii=False, indent=2)
        print(f"已保存 DOM 提取结果到 {dom_path}")

        await browser.close()

    # Phase 4: 合并构建术语库
    print("\n--- Phase 4: 合并构建术语库 ---")
    dom_terms = build_glossary_from_dom_texts(page_texts)
    print(f"DOM 提取术语: {len(dom_terms)} 条")

    all_terms = merge_glossaries(i18n_glossary, dom_terms)
    print(f"合并后术语: {len(all_terms)} 条")

    # 标准化语言代码
    all_terms = normalize_lang_codes(all_terms)

    # 保存最终术语库
    glossary_output = {
        "metadata": {
            "source": "binance.com",
            "description": "Binance 交易所多语言术语库",
            "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "languages": sorted(LANG_CODE_MAP.values()),
            "total_terms": len(all_terms),
        },
        "terms": all_terms,
    }

    output_path = OUTPUT_DIR / "binance_glossary.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(glossary_output, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"爬取完成!")
    print(f"术语总数: {len(all_terms)}")
    print(f"输出文件: {output_path}")
    print(f"耗时: {elapsed:.1f}s")
    print("=" * 60)

    # 打印一些示例术语
    if all_terms:
        print("\n示例术语 (前 10 条):")
        for term in all_terms[:10]:
            langs = ", ".join(
                f"{k}: {v}" for k, v in list(term["translations"].items())[:3]
            )
            print(f"  - {term['term_en']} → {langs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binance 多语言术语爬取工具")
    parser.add_argument(
        "--languages",
        type=str,
        default=None,
        help="目标语言，逗号分隔（默认全部）。例: en,zh-CN,ja,ko",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="最大爬取页面数（默认 5）",
    )
    parser.add_argument(
        "--discovery-pages",
        type=int,
        default=3,
        help="i18n 发现阶段访问的页面数（默认 3）",
    )
    args = parser.parse_args()

    langs = None
    if args.languages:
        langs = [l.strip() for l in args.languages.split(",")]

    asyncio.run(main(languages=langs, max_pages=args.pages, discovery_pages=args.discovery_pages))
