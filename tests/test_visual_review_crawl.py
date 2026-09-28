"""
多模态视觉评审爬取测试

从 example.com/en-US/ai 出发遍历所有子路径，
对 14 种目标语言逐一截图评审（含表达准确性维度）。
"""

import asyncio
import base64
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

# 加载 Apollo 配置（设置 API 密钥等环境变量）
try:
    from app.config.configuration import Config  # noqa: F401

    print("[config] Apollo 配置加载成功")
except Exception as e:
    print(f"[config] Apollo 配置加载失败: {e}，将使用环境变量")

import httpx
import pytest
import pytest_asyncio

from app.agents.review.visual_review_agent import VisualReviewAgent
from app.clients.cua_sandbox_client import CuaSandboxClient
from app.core.constants import LanguageCode, get_language_name
from app.core.exceptions import SandboxError
from app.schemas.visual_review import (
    VisualReviewRequest,
    VisualReviewResponse,
    VisualLanguageReview,
    VisualIssue,
)


# ============ 配置 ============

CUA_SANDBOX_URL = os.getenv("CUA_SANDBOX_URL", "http://localhost:8000")
VISUAL_REVIEW_BASE_URL = os.getenv("VISUAL_REVIEW_BASE_URL", "https://www.example.com")
VISUAL_REVIEW_SCROLL_POSITIONS = int(os.getenv("VISUAL_REVIEW_SCROLL_POSITIONS", "2"))
VISUAL_REVIEW_THRESHOLD = int(os.getenv("VISUAL_REVIEW_THRESHOLD", "75"))
VISUAL_REVIEW_OUTPUT_DIR = os.getenv(
    "VISUAL_REVIEW_OUTPUT_DIR", "tests/visual_review_results"
)

# 目标语言（排除 en-US）
ALL_TARGET_LANGUAGES = [
    lang.value for lang in LanguageCode if lang != LanguageCode.EN_US
]

_env_langs = os.getenv("VISUAL_REVIEW_LANGUAGES")
if _env_langs:
    TARGET_LANGUAGES = [lang.strip() for lang in _env_langs.split(",") if lang.strip()]
else:
    TARGET_LANGUAGES = ALL_TARGET_LANGUAGES

# 响应式断点配置（宽度决定 CSS 断点，高度统一 900）
BREAKPOINTS = {
    "sm": (640, 900),
    "md": (768, 900),
    "lg": (1024, 900),
    "xl": (1280, 900),
    "xxl": (1536, 900),
}

LARK_WEBHOOK_URL = os.getenv("LARK_WEBHOOK_URL", "")
LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")


# ============ 工具函数 ============


async def set_viewport_size(
    cua_client: CuaSandboxClient, width: int, height: int
) -> None:
    """通过 xdotool 调整 CUA 容器中浏览器窗口尺寸"""
    await cua_client.run_command(
        f"xdotool getactivewindow windowsize {width} {height}"
    )
    await asyncio.sleep(1.0)  # 等待窗口重绘


def _sanitize_path(url_path: str) -> str:
    """将 URL 路径转为安全的文件目录名"""
    return re.sub(r"[^\w\-]", "_", url_path.strip("/")) or "root"


# ============ A. 链接发现 ============


class LinkExtractor(HTMLParser):
    """从 HTML 中提取所有 <a href> 链接"""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


async def discover_sub_paths(
    base_url: str = VISUAL_REVIEW_BASE_URL,
    base_lang: str = "en-US",
    base_path: str = "/ai",
    cua_client: CuaSandboxClient | None = None,
) -> list[str]:
    """
    发现 base_path 下的所有子路径

    优先使用 CUA 浏览器渲染页面后提取链接（绕过反爬），
    若无 CUA 客户端则 fallback 到 httpx GET。

    Args:
        base_url: 网站基础 URL
        base_lang: 基础语言代码
        base_path: 基础路径
        cua_client: CUA 沙盒客户端（可选）

    Returns:
        去重排序后的路径列表（不含语言前缀）
    """
    entry_url = f"{base_url}/{base_lang}{base_path}"
    parsed_base = urlparse(base_url)
    raw_links: list[str] = []

    if cua_client:
        # 使用 CUA 容器内 python3 获取页面并提取链接（绕过反爬）
        try:
            # 先将 Python 脚本写入容器临时文件，避免 shell 转义问题
            py_script = (
                "import urllib.request, json\n"
                "from html.parser import HTMLParser\n"
                "class E(HTMLParser):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.links = []\n"
                "    def handle_starttag(self, tag, attrs):\n"
                "        if tag == 'a':\n"
                "            for name, value in attrs:\n"
                "                if name == 'href' and value:\n"
                "                    self.links.append(value)\n"
                f"r = urllib.request.urlopen(urllib.request.Request(\n"
                f"    '{entry_url}',\n"
                "    headers={'User-Agent': 'Mozilla/5.0'}))\n"
                "e = E()\n"
                "e.feed(r.read().decode())\n"
                "print(json.dumps(e.links))\n"
            )
            # 写入临时文件
            script_b64 = base64.b64encode(py_script.encode()).decode()
            await cua_client.run_command(
                f"echo {script_b64} | base64 -d > /tmp/_extract_links.py"
            )
            result = await cua_client.run_command("python3 /tmp/_extract_links.py")
            stdout = result.get("stdout", "").strip()
            if stdout:
                raw_links = json.loads(stdout)
            print(
                f"[discover_sub_paths] CUA 容器提取到 {len(raw_links)} 个链接"
            )
        except Exception as e:
            print(f"[discover_sub_paths] CUA 提取链接失败: {e}")
    else:
        # Fallback: httpx GET
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            ) as client:
                response = await client.get(entry_url)
                response.raise_for_status()
                extractor = LinkExtractor()
                extractor.feed(response.text)
                raw_links = extractor.links
        except Exception as e:
            print(f"[discover_sub_paths] HTTP 请求失败: {e}")

    # 解析链接 → 提取路径
    paths: set[str] = set()
    for link in raw_links:
        full_url = urljoin(entry_url, link)
        parsed = urlparse(full_url)

        # 只保留同站链接
        if parsed.hostname and parsed.hostname != parsed_base.hostname:
            if not parsed.hostname.endswith(f".{parsed_base.hostname}"):
                continue

        path = parsed.path.rstrip("/")
        if not path:
            continue

        # 去除语言前缀，提取实际路径
        for lang in LanguageCode:
            prefix = f"/{lang.value}"
            if path.startswith(prefix):
                path = path[len(prefix):]
                break

        # 只保留以 base_path 开头的路径
        if path.startswith(base_path):
            paths.add(path)

    # 保证至少包含 base_path
    paths.add(base_path)

    return sorted(paths)


# ============ B. 增强评审 Agent ============


class EnhancedVisualReviewAgent(VisualReviewAgent):
    """
    增强视觉评审 Agent

    在原有 3 个评审维度基础上新增第 4 维度：表达准确性（Expression Accuracy）
    支持将截图保存到磁盘。
    """

    def __init__(
        self,
        *,
        screenshot_dir: Path | None = None,
        breakpoint_name: str = "default",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._screenshot_dir = screenshot_dir
        self._breakpoint_name = breakpoint_name

    async def _capture_language_screenshots(
        self,
        base_url: str,
        url_path: str,
        lang_code: str,
        scroll_positions: int,
    ) -> list[str]:
        """截图并可选保存到磁盘"""
        screenshots = await super()._capture_language_screenshots(
            base_url, url_path, lang_code, scroll_positions,
        )
        if self._screenshot_dir and screenshots:
            save_dir = (
                self._screenshot_dir
                / self._breakpoint_name
                / _sanitize_path(url_path)
                / lang_code
            )
            save_dir.mkdir(parents=True, exist_ok=True)
            for i, b64_str in enumerate(screenshots):
                filepath = save_dir / f"scroll_{i}.png"
                filepath.write_bytes(base64.b64decode(b64_str))
                print(f"[screenshot] saved {filepath}")
        return screenshots

    def _build_review_prompt(self, lang_code: str, lang_name: str) -> str:
        """构建增强评审提示词，新增表达准确性维度"""
        return f"""Compare the reference (English) screenshots with the \
{lang_name} ({lang_code}) translation screenshots above.

Evaluate the translation's visual quality on these dimensions:

1. **Layout Quality** (layout_score: 0-100):
   - Text overflow beyond containers
   - Text truncation with ellipsis or cut-off
   - Broken layout or misaligned elements
   - Buttons/labels that are too wide or too narrow

2. **Text Rendering** (text_rendering_score: 0-100):
   - Encoding issues (garbled characters, mojibake)
   - Font rendering problems
   - Incorrect character display
   - Missing glyphs or placeholder boxes

3. **Translation Completeness** (translation_completeness_score: 0-100):
   - Untranslated English text remaining
   - Placeholder strings (e.g., {{{{key}}}}) visible
   - Mixed language content that shouldn't be mixed
   - Missing translations leaving blank spaces

4. **Expression Accuracy** (expression_accuracy_score: 0-100):
   - Ambiguous expressions that may confuse users
   - Inaccurate translation of financial/trading terminology
   - Literal translations that lose the original meaning
   - Inconsistent terminology within the same page
   - Culturally inappropriate expressions for the target language

For each issue found, classify it as:
- **issue_type**: truncation|overflow|encoding|layout|untranslated|mistranslation|style|ambiguous_expression|inaccurate_translation
- **severity**: critical (breaks usability), major (noticeable problem), minor (cosmetic)

Respond in this exact JSON format:
{{
    "overall_score": <0-100>,
    "layout_score": <0-100>,
    "text_rendering_score": <0-100>,
    "translation_completeness_score": <0-100>,
    "expression_accuracy_score": <0-100>,
    "issues": [
        {{
            "issue_type": "<type>",
            "severity": "<severity>",
            "location": "<where on the page>",
            "description": "<description in Chinese>",
            "suggestion": "<suggestion in Chinese>"
        }}
    ],
    "feedback": "<用中文撰写整体评估总结，包括主要问题和改进建议>"
}}

IMPORTANT: The "feedback", "description", and "suggestion" fields MUST be written in Simplified Chinese.

Return ONLY the JSON object, no additional text."""

    def _parse_review_response(
        self,
        response: str,
        lang_code: str,
        lang_name: str,
        screenshots_count: int,
    ) -> VisualLanguageReview:
        """解析增强版 LLM 评审响应，提取 expression_accuracy_score"""
        import json
        import re

        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            return self._default_review(lang_code, lang_name, screenshots_count)

        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            return self._default_review(lang_code, lang_name, screenshots_count)

        overall_score = int(parsed.get("overall_score", 70))
        expression_accuracy_score = int(
            parsed.get("expression_accuracy_score", 70)
        )

        issues = [
            VisualIssue(
                issue_type=issue.get("issue_type", "layout"),
                severity=issue.get("severity", "minor"),
                location=issue.get("location", "unknown"),
                description=issue.get("description", ""),
                suggestion=issue.get("suggestion", ""),
            )
            for issue in parsed.get("issues", [])
        ]

        # 将 expression_accuracy_score 嵌入 feedback
        feedback = parsed.get("feedback", "")
        if expression_accuracy_score < 100:
            feedback = (
                f"{feedback} [Expression Accuracy: {expression_accuracy_score}/100]"
            )

        return VisualLanguageReview(
            lang_code=lang_code,
            lang_name=lang_name,
            overall_score=overall_score,
            layout_score=int(parsed.get("layout_score", 70)),
            text_rendering_score=int(parsed.get("text_rendering_score", 70)),
            translation_completeness_score=int(
                parsed.get("translation_completeness_score", 70)
            ),
            expression_accuracy_score=expression_accuracy_score,
            passed=overall_score >= self._visual_quality_threshold,
            issues=issues,
            screenshots_count=screenshots_count,
            feedback=feedback,
        )

    def _default_review(
        self,
        lang_code: str,
        lang_name: str,
        screenshots_count: int,
    ) -> VisualLanguageReview:
        """LLM 解析失败时返回默认评审结果"""
        return VisualLanguageReview(
            lang_code=lang_code,
            lang_name=lang_name,
            overall_score=70,
            layout_score=70,
            text_rendering_score=70,
            translation_completeness_score=70,
            expression_accuracy_score=70,
            passed=70 >= self._visual_quality_threshold,
            issues=[],
            screenshots_count=screenshots_count,
            feedback="Unable to parse visual review response",
        )


# ============ C. 爬取编排器 ============


@dataclass
class CrawlPageResult:
    """单页面单语言评审结果"""

    url_path: str
    lang_code: str
    lang_name: str
    overall_score: int
    layout_score: int
    text_rendering_score: int
    translation_completeness_score: int
    expression_accuracy_score: int
    passed: bool
    issues_count: int
    feedback: str


@dataclass
class CrawlReport:
    """爬取评审报告"""

    base_url: str
    reference_lang: str
    target_languages: list[str]
    paths_discovered: list[str]
    total_pages: int
    total_reviews: int
    passed_count: int
    failed_count: int
    average_score: float
    total_latency_seconds: float
    results: list[CrawlPageResult] = field(default_factory=list)


class VisualReviewCrawler:
    """
    视觉评审爬取编排器

    发现子路径 → 初始化 CUA + Agent → 逐路径串行评审 → 汇总报告
    """

    def __init__(
        self,
        cua_url: str = CUA_SANDBOX_URL,
        base_url: str = VISUAL_REVIEW_BASE_URL,
        base_lang: str = "en-US",
        base_path: str = "/ai",
        target_languages: list[str] | None = None,
        scroll_positions: int = VISUAL_REVIEW_SCROLL_POSITIONS,
        quality_threshold: int = VISUAL_REVIEW_THRESHOLD,
        output_dir: str = VISUAL_REVIEW_OUTPUT_DIR,
    ):
        self._cua_url = cua_url
        self._base_url = base_url
        self._base_lang = base_lang
        self._base_path = base_path
        self._target_languages = target_languages or TARGET_LANGUAGES
        self._scroll_positions = scroll_positions
        self._quality_threshold = quality_threshold
        self._output_dir = Path(output_dir)

    async def run(self) -> CrawlReport:
        """
        执行完整爬取评审

        每个路径评审前重建沙盒，确保浏览器状态干净。

        Returns:
            CrawlReport 评审报告
        """
        start_time = time.time()

        # 1. 初始化 CUA 客户端（链接发现和评审共用）
        cua_client = CuaSandboxClient(base_url=self._cua_url)
        try:
            # 2. 使用 CUA 浏览器发现子路径
            paths = await discover_sub_paths(
                self._base_url, self._base_lang, self._base_path,
                cua_client=cua_client,
            )
            print(f"[VisualReviewCrawler] 发现 {len(paths)} 个路径: {paths}")

            # 3. 逐路径评审（每次重建沙盒）
            all_results: list[CrawlPageResult] = []
            for i, path in enumerate(paths):
                print(
                    f"[VisualReviewCrawler] === 路径 {i + 1}/{len(paths)}: "
                    f"{path} ==="
                )
                agent = EnhancedVisualReviewAgent(
                    sandbox_client=cua_client,
                    sandbox_base_url=self._cua_url,
                    visual_quality_threshold=self._quality_threshold,
                )
                async with agent:
                    results = await self._review_path(agent, path)
                    all_results.extend(results)

            # 4. 生成报告
            elapsed = time.time() - start_time
            report = self._generate_report(paths, all_results, elapsed)
            self._save_report(report)
            return report
        finally:
            await cua_client.close()

    async def _review_path(
        self,
        agent: EnhancedVisualReviewAgent,
        url_path: str,
    ) -> list[CrawlPageResult]:
        """
        评审单个路径的所有目标语言

        Args:
            agent: 增强评审 Agent
            url_path: URL 路径（不含语言前缀）

        Returns:
            该路径下所有语言的评审结果
        """
        print(f"[VisualReviewCrawler] 评审路径: {url_path}")

        request = VisualReviewRequest(
            target_langs=self._target_languages,
            base_url=self._base_url,
            url_path=url_path,
            reference_lang=self._base_lang,
            scroll_positions=self._scroll_positions,
        )

        try:
            response = await agent.run(request)
        except Exception as e:
            print(f"[VisualReviewCrawler] 路径评审失败 [{url_path}]: {e}")
            return []

        results: list[CrawlPageResult] = []
        for review in response.reviews:
            results.append(
                CrawlPageResult(
                    url_path=url_path,
                    lang_code=review.lang_code,
                    lang_name=review.lang_name,
                    overall_score=review.overall_score,
                    layout_score=review.layout_score,
                    text_rendering_score=review.text_rendering_score,
                    translation_completeness_score=review.translation_completeness_score,
                    expression_accuracy_score=review.expression_accuracy_score,
                    passed=review.passed,
                    issues_count=len(review.issues),
                    feedback=review.feedback,
                )
            )

        passed = sum(1 for r in results if r.passed)
        print(
            f"[VisualReviewCrawler] 路径 {url_path} 完成: "
            f"{passed}/{len(results)} 通过"
        )
        return results

    def _generate_report(
        self,
        paths: list[str],
        results: list[CrawlPageResult],
        elapsed_seconds: float,
    ) -> CrawlReport:
        """生成爬取报告"""
        scores = [r.overall_score for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        passed_count = sum(1 for r in results if r.passed)

        return CrawlReport(
            base_url=self._base_url,
            reference_lang=self._base_lang,
            target_languages=self._target_languages,
            paths_discovered=paths,
            total_pages=len(paths),
            total_reviews=len(results),
            passed_count=passed_count,
            failed_count=len(results) - passed_count,
            average_score=round(avg_score, 2),
            total_latency_seconds=round(elapsed_seconds, 2),
            results=results,
        )

    def _save_report(self, report: CrawlReport) -> Path:
        """保存报告到 JSON 文件"""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filepath = self._output_dir / f"report_{timestamp}.json"

        report_dict = asdict(report)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

        print(f"[VisualReviewCrawler] 报告已保存: {filepath}")
        return filepath


# ============ D. Lark 通知 ============


# Lark tenant_access_token 缓存
_lark_tenant_token: str = ""
_lark_token_expires_at: float = 0.0


async def _get_lark_tenant_token() -> str:
    """获取 Lark tenant_access_token（带缓存，提前 5 分钟刷新）"""
    global _lark_tenant_token, _lark_token_expires_at
    if _lark_tenant_token and time.time() < _lark_token_expires_at:
        return _lark_tenant_token

    if not LARK_APP_ID or not LARK_APP_SECRET:
        print("[lark] LARK_APP_ID / LARK_APP_SECRET 未配置，跳过图片上传")
        return ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(
                "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
            )
            data = resp.json()
            _lark_tenant_token = data.get("tenant_access_token", "")
            expire = data.get("expire", 7200)
            _lark_token_expires_at = time.time() + expire - 300
            return _lark_tenant_token
    except Exception as e:
        print(f"[lark] 获取 tenant_access_token 失败: {e}")
        return ""


async def _upload_lark_image(token: str, image_data: bytes) -> str:
    """上传图片到 Lark，返回 image_key"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                "https://open.larksuite.com/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                data={"image_type": "message"},
                files={"image": ("screenshot.png", image_data, "image/png")},
            )
            data = resp.json()
            image_key = data.get("data", {}).get("image_key", "")
            if image_key:
                print(f"[lark] 图片上传成功: {image_key}")
            else:
                print(f"[lark] 图片上传失败: {data}")
            return image_key
    except Exception as e:
        print(f"[lark] 图片上传异常: {e}")
        return ""


async def _build_screenshot_elements(
    breakpoint_name: str,
    url_path: str,
    lang_code: str,
    screenshot_dir: Path | None,
) -> list[dict]:
    """查找已保存的截图，上传到 Lark 并返回卡片 img 元素列表"""
    if not screenshot_dir:
        return []

    img_dir = screenshot_dir / breakpoint_name / _sanitize_path(url_path) / lang_code
    if not img_dir.exists():
        print(f"[lark] 截图目录不存在，跳过: {img_dir}")
        return []

    png_files = sorted(img_dir.glob("scroll_*.png"))
    if not png_files:
        return []

    token = await _get_lark_tenant_token()
    if not token:
        return []

    elements: list[dict] = []
    for png_file in png_files:
        image_key = await _upload_lark_image(token, png_file.read_bytes())
        if image_key:
            elements.append({
                "tag": "img",
                "img_key": image_key,
                "alt": {
                    "tag": "plain_text",
                    "content": f"{lang_code} — {png_file.name}",
                },
            })
    return elements


async def _post_lark_card(card: dict) -> None:
    """发送单条 Lark 卡片消息，失败仅打印日志不抛异常"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(LARK_WEBHOOK_URL, json=card)
            print(f"[lark] 消息已发送, status={resp.status_code}")
    except Exception as e:
        print(f"[lark] 发送失败: {e}")


def _pass_rate_color(rate: float) -> str:
    """根据通过率返回 Lark 卡片头部颜色"""
    if rate >= 80:
        return "green"
    return "yellow" if rate >= 50 else "red"


async def send_lark_report(
    report: CrawlReport,
    breakpoint_name: str = "",
    viewport_size: tuple[int, int] | None = None,
    screenshot_dir: Path | None = None,
) -> None:
    """
    发送单断点评审报告到 Lark 机器人

    1. 先发一条汇总卡片
    2. 再为每个未通过的评审单独发送一条详情卡片（含截图）
    """
    size_label = f"{viewport_size[0]}x{viewport_size[1]}" if viewport_size else ""
    header_title = (
        f"视觉评审报告 — {breakpoint_name} ({size_label})"
        if breakpoint_name
        else "视觉评审报告"
    )

    pass_rate = (
        report.passed_count / report.total_reviews * 100
        if report.total_reviews
        else 0
    )

    failed_items = [r for r in report.results if not r.passed]

    # 失败项列表（Lark 卡片不支持 markdown 表格）
    failed_section = ""
    if failed_items:
        lines = [f"\n\n**未通过项（{len(failed_items)}项）**"]
        for i, r in enumerate(failed_items, 1):
            lines.append(
                f"{i}. {r.url_path} — {r.lang_code} — {r.overall_score}分 — {r.issues_count}个问题"
            )
        failed_section = "\n".join(lines)

    # ---- 汇总卡片 ----
    summary_card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": _pass_rate_color(pass_rate),
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**页面数**: {report.total_pages}  |  "
                        f"**评审数**: {report.total_reviews}  |  "
                        f"**通过**: {report.passed_count}  |  "
                        f"**未通过**: {report.failed_count}\n"
                        f"**平均分**: {report.average_score}  |  "
                        f"**通过率**: {pass_rate:.1f}%  |  "
                        f"**耗时**: {report.total_latency_seconds:.1f}s"
                        f"{failed_section}"
                    ),
                }
            ],
        },
    }
    await _post_lark_card(summary_card)

    # ---- 逐条推送未通过项详情（含截图） ----
    for r in failed_items:
        img_elements = await _build_screenshot_elements(
            breakpoint_name, r.url_path, r.lang_code, screenshot_dir,
        )
        detail_elements: list[dict] = [
            {
                "tag": "markdown",
                "content": (
                    f"**断点**: {breakpoint_name} ({size_label})\n"
                    f"**路径**: {r.url_path}\n"
                    f"**综合分**: {r.overall_score}  |  "
                    f"**布局**: {r.layout_score}  |  "
                    f"**文字渲染**: {r.text_rendering_score}\n"
                    f"**翻译完整性**: {r.translation_completeness_score}  |  "
                    f"**表达准确性**: {r.expression_accuracy_score}\n"
                    f"**问题数**: {r.issues_count}\n\n"
                    f"**评审总结**\n{r.feedback}"
                ),
            }
        ]
        detail_elements.extend(img_elements)

        detail_card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"未通过详情 — {r.lang_name}（{r.lang_code}）",
                    },
                    "template": "red",
                },
                "elements": detail_elements,
            },
        }
        await _post_lark_card(detail_card)


async def send_lark_aggregate_report(
    reports: list[tuple[str, CrawlReport]],
    screenshot_dir: Path | None = None,
) -> None:
    """
    发送多断点汇总报告到 Lark 机器人

    1. 先发一条全断点汇总卡片
    2. 再为所有断点中未通过的评审逐条发送详情卡片
    """
    bp_lines: list[str] = []
    total_reviews = 0
    total_passed = 0
    score_sum = 0.0
    all_failed: list[tuple[str, tuple[int, int], CrawlPageResult]] = []

    for bp_name, report in reports:
        width, height = BREAKPOINTS.get(bp_name, (0, 0))
        bp_pass_rate = (
            report.passed_count / report.total_reviews * 100
            if report.total_reviews
            else 0
        )
        bp_lines.append(
            f"- **{bp_name}** ({width}x{height}): "
            f"{report.total_reviews}条评审, "
            f"通过 {report.passed_count}/{report.total_reviews} ({bp_pass_rate:.0f}%), "
            f"平均分 {report.average_score}"
        )
        total_reviews += report.total_reviews
        total_passed += report.passed_count
        score_sum += report.average_score * report.total_reviews

        for r in report.results:
            if not r.passed:
                all_failed.append((bp_name, (width, height), r))

    overall_avg = score_sum / total_reviews if total_reviews else 0
    overall_pass_rate = total_passed / total_reviews * 100 if total_reviews else 0

    # ---- 汇总卡片 ----
    bp_detail = "\n".join(bp_lines)
    summary_card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "多分辨率视觉评审汇总",
                },
                "template": _pass_rate_color(overall_pass_rate),
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**总评审数**: {total_reviews}  |  "
                        f"**通过**: {total_passed}/{total_reviews}  |  "
                        f"**总平均分**: {overall_avg:.1f}  |  "
                        f"**通过率**: {overall_pass_rate:.1f}%\n\n"
                        f"**各断点明细**\n{bp_detail}"
                    ),
                }
            ],
        },
    }
    await _post_lark_card(summary_card)

    # ---- 逐条推送未通过项详情（含截图） ----
    for bp_name, (width, height), r in all_failed:
        size_label = f"{width}x{height}"
        img_elements = await _build_screenshot_elements(
            bp_name, r.url_path, r.lang_code, screenshot_dir,
        )
        detail_elements: list[dict] = [
            {
                "tag": "markdown",
                "content": (
                    f"**断点**: {bp_name} ({size_label})\n"
                    f"**路径**: {r.url_path}\n"
                    f"**综合分**: {r.overall_score}  |  "
                    f"**布局**: {r.layout_score}  |  "
                    f"**文字渲染**: {r.text_rendering_score}\n"
                    f"**翻译完整性**: {r.translation_completeness_score}  |  "
                    f"**表达准确性**: {r.expression_accuracy_score}\n"
                    f"**问题数**: {r.issues_count}\n\n"
                    f"**评审总结**\n{r.feedback}"
                ),
            }
        ]
        detail_elements.extend(img_elements)

        detail_card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"未通过详情 — {r.lang_name}（{r.lang_code}）",
                    },
                    "template": "red",
                },
                "elements": detail_elements,
            },
        }
        await _post_lark_card(detail_card)


# ============ E. 多分辨率爬取编排器 ============


class MultiResolutionVisualReviewCrawler(VisualReviewCrawler):
    """
    多分辨率视觉评审爬取编排器

    在标准爬取流程基础上：
    1. 设置浏览器视口到指定断点尺寸
    2. 使用 EnhancedVisualReviewAgent 保存截图到磁盘
    3. 完成后发送 Lark 通知
    """

    def __init__(
        self,
        breakpoint_name: str = "default",
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._breakpoint_name = breakpoint_name
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        self._screenshot_dir = self._output_dir / "screenshots"

    async def run(self) -> CrawlReport:
        start_time = time.time()

        cua_client = CuaSandboxClient(base_url=self._cua_url)
        try:
            # 1. 设置视口尺寸
            print(
                f"[MultiRes] 设置视口: {self._breakpoint_name} "
                f"({self._viewport_width}x{self._viewport_height})"
            )
            await set_viewport_size(
                cua_client, self._viewport_width, self._viewport_height
            )

            # 2. 发现子路径
            paths = await discover_sub_paths(
                self._base_url, self._base_lang, self._base_path,
                cua_client=cua_client,
            )
            print(f"[MultiRes] 发现 {len(paths)} 个路径: {paths}")

            # 3. 逐路径评审
            all_results: list[CrawlPageResult] = []
            for i, path in enumerate(paths):
                print(
                    f"[MultiRes] === [{self._breakpoint_name}] "
                    f"路径 {i + 1}/{len(paths)}: {path} ==="
                )
                agent = EnhancedVisualReviewAgent(
                    sandbox_client=cua_client,
                    sandbox_base_url=self._cua_url,
                    visual_quality_threshold=self._quality_threshold,
                    screenshot_dir=self._screenshot_dir,
                    breakpoint_name=self._breakpoint_name,
                )
                async with agent:
                    results = await self._review_path(agent, path)
                    all_results.extend(results)

            # 4. 生成报告
            elapsed = time.time() - start_time
            report = self._generate_report(paths, all_results, elapsed)
            self._save_report(report)

            # 5. 发送 Lark 通知（含截图）
            await send_lark_report(
                report,
                breakpoint_name=self._breakpoint_name,
                viewport_size=(self._viewport_width, self._viewport_height),
                screenshot_dir=self._screenshot_dir,
            )

            return report
        finally:
            await cua_client.close()


# ============ F. Pytest 测试用例 ============


class TestVisualReviewCrawl:
    """视觉评审爬取测试"""

    @pytest.mark.asyncio
    async def test_cua_sandbox_connectivity(self):
        """验证 CUA 服务器连通性"""
        client = CuaSandboxClient(base_url=CUA_SANDBOX_URL)
        try:
            sandbox_id = await client.create_sandbox()
            assert sandbox_id == CuaSandboxClient.DUMMY_SANDBOX_ID
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_discover_sub_paths(self):
        """验证链接发现功能（通过 CUA 浏览器）"""
        cua_client = CuaSandboxClient(base_url=CUA_SANDBOX_URL)
        try:
            paths = await discover_sub_paths(
                VISUAL_REVIEW_BASE_URL, "en-US", "/ai",
                cua_client=cua_client,
            )
        finally:
            await cua_client.close()
        assert len(paths) >= 1
        assert "/ai" in paths
        print(f"发现路径: {paths}")

    @pytest.mark.asyncio
    async def test_single_page_single_language(self):
        """单页面 zh-CN 评审（smoke test）"""
        crawler = VisualReviewCrawler(
            target_languages=["zh-CN"],
            scroll_positions=1,
        )
        # 只评审 /ai 路径
        cua_client = CuaSandboxClient(base_url=CUA_SANDBOX_URL)
        try:
            agent = EnhancedVisualReviewAgent(
                sandbox_client=cua_client,
                sandbox_base_url=CUA_SANDBOX_URL,
                visual_quality_threshold=VISUAL_REVIEW_THRESHOLD,
            )
            async with agent:
                request = VisualReviewRequest(
                    target_langs=["zh-CN"],
                    base_url=VISUAL_REVIEW_BASE_URL,
                    url_path="/ai",
                    reference_lang="en-US",
                    scroll_positions=1,
                )
                response = await agent.run(request)

            assert len(response.reviews) == 1
            review = response.reviews[0]
            assert review.lang_code == "zh-CN"
            assert 0 <= review.overall_score <= 100
            print(
                f"zh-CN 评审结果: overall={review.overall_score}, "
                f"expression_accuracy={review.expression_accuracy_score}, "
                f"passed={review.passed}"
            )
        finally:
            await cua_client.close()

    @pytest.mark.asyncio
    async def test_crawl_subset_languages(self):
        """zh-CN + ja-JP 子集爬取"""
        crawler = VisualReviewCrawler(
            target_languages=["zh-CN", "ja-JP"],
            scroll_positions=1,
        )
        report = await crawler.run()

        assert report.total_reviews > 0
        assert report.total_pages >= 1
        print(
            f"子集爬取完成: {report.total_reviews} 条评审, "
            f"平均分 {report.average_score}, "
            f"通过 {report.passed_count}/{report.total_reviews}"
        )

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_crawl(self):
        """全部路径 x 全部语言完整爬取"""
        crawler = VisualReviewCrawler()
        report = await crawler.run()

        assert report.total_reviews > 0
        assert report.total_pages >= 1
        print(
            f"完整爬取完成: {report.total_pages} 页 x "
            f"{len(report.target_languages)} 语言 = "
            f"{report.total_reviews} 条评审"
        )
        print(
            f"平均分: {report.average_score}, "
            f"通过: {report.passed_count}/{report.total_reviews}, "
            f"耗时: {report.total_latency_seconds:.1f}s"
        )


class TestMultiResolutionVisualReview:
    """多分辨率视觉评审测试"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bp_name", ["sm", "md", "lg", "xl", "xxl"])
    async def test_breakpoint(self, bp_name: str):
        """单个断点独立评审（全部 14 种语言）"""
        width, height = BREAKPOINTS[bp_name]
        crawler = MultiResolutionVisualReviewCrawler(
            breakpoint_name=bp_name,
            viewport_width=width,
            viewport_height=height,
        )
        report = await crawler.run()
        assert report.total_reviews > 0
        print(
            f"[{bp_name}] {width}x{height} 完成: "
            f"{report.passed_count}/{report.total_reviews} 通过, "
            f"平均分 {report.average_score}"
        )

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_all_breakpoints_aggregate(self):
        """全断点完整测试 + 汇总 Lark 通知"""
        all_reports: list[tuple[str, CrawlReport]] = []
        for bp_name, (width, height) in BREAKPOINTS.items():
            print(f"\n{'='*60}")
            print(f"[aggregate] 开始断点: {bp_name} ({width}x{height})")
            print(f"{'='*60}")
            crawler = MultiResolutionVisualReviewCrawler(
                breakpoint_name=bp_name,
                viewport_width=width,
                viewport_height=height,
            )
            report = await crawler.run()
            all_reports.append((bp_name, report))

        # 发送汇总 Lark 通知（含截图）
        screenshot_dir = Path(VISUAL_REVIEW_OUTPUT_DIR) / "screenshots"
        await send_lark_aggregate_report(all_reports, screenshot_dir=screenshot_dir)

        # 验证每个断点都有评审结果
        for bp_name, report in all_reports:
            assert report.total_reviews > 0, f"{bp_name} 没有评审结果"
