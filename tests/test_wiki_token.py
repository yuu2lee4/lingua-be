"""
Lark Wiki Token 解析测试脚本

从 wiki 链接中获取底层文档的 obj_token（如 spreadsheet_token）

用法:
    python tests/test_wiki_token.py <wiki_url_or_token>

示例:
    python tests/test_wiki_token.py https://g471ooa6k2a.sg.larksuite.com/wiki/YzAOwkwlkiVoCrksUaUlqa82gAb
    python tests/test_wiki_token.py YzAOwkwlkiVoCrksUaUlqa82gAb
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ============ 配置 ============

LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")
LARK_BASE_URL = "https://open.larksuite.com/open-apis"


# ============ 核心函数 ============


def parse_wiki_token(wiki_url_or_token: str) -> str:
    """从 wiki URL 或直接的 token 中提取 wiki token"""
    wiki_url_or_token = wiki_url_or_token.strip().rstrip("/")

    if "/wiki/" in wiki_url_or_token:
        # URL 格式: https://xxx.larksuite.com/wiki/TOKEN
        token = wiki_url_or_token.split("/wiki/")[-1]
        # 去掉可能的 query params
        token = token.split("?")[0]
        return token
    else:
        # 直接传入 token
        return wiki_url_or_token


async def get_tenant_token() -> str:
    """获取 tenant_access_token"""
    print("=" * 60)
    print("[步骤 1] 获取 tenant_access_token")

    if not LARK_APP_ID or not LARK_APP_SECRET:
        print("  请设置 LARK_APP_ID 和 LARK_APP_SECRET 环境变量")
        return ""

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(
            f"{LARK_BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
        )
        data = resp.json()

    code = data.get("code", -1)
    token = data.get("tenant_access_token", "")

    if code == 0 and token:
        print(f"  获取成功, token={token[:16]}..., 有效期={data.get('expire', 0)}s")
    else:
        print(f"  获取失败: code={code}, msg={data.get('msg', '')}")

    return token


async def get_wiki_node(tenant_token: str, wiki_token: str) -> dict:
    """调用 wiki/v2/spaces/get_node 获取节点信息"""
    print("=" * 60)
    print("[步骤 2] 获取 Wiki 节点信息")
    print(f"  wiki_token: {wiki_token}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.get(
            f"{LARK_BASE_URL}/wiki/v2/spaces/get_node",
            params={"token": wiki_token},
            headers={"Authorization": f"Bearer {tenant_token}"},
        )
        data = resp.json()

    code = data.get("code", -1)

    if code != 0:
        print(f"  API 失败: code={code}, msg={data.get('msg', '')}")
        print(f"  完整响应: {data}")
        return {}

    node = data.get("data", {}).get("node", {})
    if not node:
        print("  响应中没有 node 数据")
        print(f"  完整响应: {data}")
        return {}

    print(f"  获取成功!")
    return node


def print_node_info(node: dict) -> None:
    """打印节点详细信息"""
    print("=" * 60)
    print("[结果] Wiki 节点信息")
    print(f"  node_token:  {node.get('node_token', 'N/A')}")
    print(f"  obj_type:    {node.get('obj_type', 'N/A')}")
    print(f"  obj_token:   {node.get('obj_token', 'N/A')}")
    print(f"  title:       {node.get('title', 'N/A')}")
    print(f"  space_id:    {node.get('space_id', 'N/A')}")
    print(f"  parent_node: {node.get('parent_node_token', 'N/A')}")
    print(f"  has_child:   {node.get('has_child', 'N/A')}")
    print(f"  creator:     {node.get('creator', 'N/A')}")
    print(f"  owner:       {node.get('owner', 'N/A')}")

    obj_type = node.get("obj_type", "")
    obj_token = node.get("obj_token", "")

    print("=" * 60)
    if obj_type == "sheet":
        print(f"  --> spreadsheet_token = {obj_token}")
        print("  该 wiki 页面底层是电子表格，obj_token 即为 spreadsheet_token")
    elif obj_type == "doc":
        print(f"  --> doc_token = {obj_token}")
        print("  该 wiki 页面底层是文档")
    elif obj_type == "docx":
        print(f"  --> document_id = {obj_token}")
        print("  该 wiki 页面底层是新版文档")
    elif obj_type == "bitable":
        print(f"  --> app_token = {obj_token}")
        print("  该 wiki 页面底层是多维表格")
    else:
        print(f"  --> obj_token = {obj_token} (type: {obj_type})")


# ============ 主流程 ============


async def main(wiki_url_or_token: str) -> None:
    print(f"\n{'=' * 60}")
    print("  Lark Wiki Token 解析")
    print(f"{'=' * 60}\n")

    # 解析 wiki token
    wiki_token = parse_wiki_token(wiki_url_or_token)
    print(f"输入: {wiki_url_or_token}")
    print(f"解析后 wiki_token: {wiki_token}\n")

    # 步骤 1: 获取 tenant token
    tenant_token = await get_tenant_token()
    if not tenant_token:
        sys.exit(1)

    # 步骤 2: 获取 wiki 节点信息
    node = await get_wiki_node(tenant_token, wiki_token)
    if not node:
        sys.exit(1)

    # 打印结果
    print_node_info(node)
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {__file__} <wiki_url_or_token>")
        print(f"示例: python {__file__} https://g471ooa6k2a.sg.larksuite.com/wiki/YzAOwkwlkiVoCrksUaUlqa82gAb")
        sys.exit(1)

    asyncio.run(main(sys.argv[1]))
