"""
Lark API 客户端

提供飞书多维表格 (Bitable) 和电子表格 (Sheets) 的 API 操作
"""

from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from app.logger import logger


def _convert_cell_value_for_write(value: Any) -> Any:
    """
    将 Lark 单元格值转换为可写入的格式

    处理特殊类型如 @ 提及、链接等，将复杂对象转换为简单值

    Args:
        value: 单元格值

    Returns:
        转换后的值
    """
    if value is None:
        return ""

    # 处理字典类型（如 @ 提及、链接等）
    if isinstance(value, dict):
        # @ 提及类型：返回 text 字段（如 "@Naomi Wen"）
        if value.get("type") == "mention" or value.get("category") == "at-user-block":
            return value.get("text", "")

        # 链接类型
        if value.get("type") == "url" or "link" in value:
            return value.get("link") or value.get("url") or value.get("text", "")

        # 其他字典类型：尝试获取 text 或转为字符串
        if "text" in value:
            return value.get("text", "")

        # 无法识别的字典，转为空字符串避免错误
        logger.warning(f"[_convert_cell_value_for_write] 无法识别的字典类型: {value}")
        return ""

    # 处理列表类型（可能是富文本段落）
    if isinstance(value, list):
        # 尝试提取所有 text
        texts = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "".join(texts) if texts else ""

    # 其他类型直接返回
    return value


class LarkBaseClient:
    """
    Lark API 基础客户端

    使用 Tenant Access Token 进行认证
    """

    # 国际版 URL
    BASE_URL_GLOBAL = "https://open.larksuite.com/open-apis"
    # 国内版 URL
    BASE_URL_CN = "https://open.feishu.cn/open-apis"

    TOKEN_EXPIRE_BUFFER = 60  # 1分钟缓冲，提前刷新 token

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        use_global: bool = True,
    ):
        """
        初始化客户端

        Args:
            app_id: 飞书应用 App ID
            app_secret: 飞书应用 App Secret
            use_global: 是否使用国际版 (larksuite)，默认 True
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = self.BASE_URL_GLOBAL if use_global else self.BASE_URL_CN
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "LarkBaseClient":
        """上下文管理器入口"""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """上下文管理器退出"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _get_tenant_access_token(self) -> str:
        """
        获取 Tenant Access Token (带缓存)

        Returns:
            tenant_access_token 字符串
        """
        # 检查缓存是否有效
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at
        ):
            return self._access_token

        logger.info(
            "[LarkBaseClient._get_tenant_access_token] 获取新的 tenant access token"
        )

        client = self._get_client()
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            raise Exception(f"获取 tenant access token 失败: {data.get('msg')}")

        self._access_token = data["tenant_access_token"]
        # 设置过期时间，提前 1 分钟刷新
        expire_seconds = data.get("expire", 600) - self.TOKEN_EXPIRE_BUFFER
        self._token_expires_at = datetime.now() + timedelta(seconds=expire_seconds)

        logger.info(
            f"[LarkBaseClient._get_tenant_access_token] 获取成功, "
            f"过期时间: {self._token_expires_at}"
        )

        return self._access_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        check_code: bool = True,
    ) -> dict[str, Any]:
        """
        发起 API 请求

        Args:
            method: HTTP 方法
            endpoint: API 端点（不含 base_url）
            params: URL 参数
            json_data: JSON 请求体
            check_code: 是否检查响应 code

        Returns:
            API 响应数据
        """
        token = await self._get_tenant_access_token()
        client = self._get_client()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
        )
        response.raise_for_status()
        data = response.json()

        if check_code and data.get("code") != 0:
            raise Exception(f"API 请求失败: {data.get('msg')}, code={data.get('code')}")

        return data

    async def close(self) -> None:
        """关闭客户端连接"""
        if self._client:
            await self._client.aclose()
            self._client = None


class LarkSheetsClient(LarkBaseClient):
    """
    Lark Sheets (电子表格) API 客户端

    提供电子表格的读写操作
    """

    async def get_sheet_info(
        self,
        spreadsheet_token: str,
    ) -> dict[str, Any]:
        """
        获取电子表格的工作表信息

        Args:
            spreadsheet_token: 电子表格 token

        Returns:
            包含 sheets 列表的响应
        """
        logger.info(
            f"[LarkSheetsClient.get_sheet_info] 获取工作表信息, "
            f"spreadsheet_token={spreadsheet_token}"
        )

        endpoint = f"/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        data = await self._request("GET", endpoint)

        sheets = data.get("data", {}).get("sheets", [])
        logger.info(f"[LarkSheetsClient.get_sheet_info] 获取到 {len(sheets)} 个工作表")

        return data.get("data", {})

    async def read_sheet_values(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        range_str: str | None = None,
    ) -> list[list[Any]]:
        """
        读取工作表数据

        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            range_str: 范围字符串，如 "A1:Z100"，默认读取全部

        Returns:
            二维数组形式的数据
        """
        # 构建范围
        if range_str:
            full_range = f"{sheet_id}!{range_str}"
        else:
            full_range = sheet_id

        logger.info(
            f"[LarkSheetsClient.read_sheet_values] 读取数据, "
            f"spreadsheet_token={spreadsheet_token}, range={full_range}"
        )

        endpoint = f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{full_range}"
        data = await self._request("GET", endpoint)

        values = data.get("data", {}).get("valueRange", {}).get("values", [])
        logger.info(f"[LarkSheetsClient.read_sheet_values] 读取到 {len(values)} 行数据")

        return values

    async def read_sheet_as_dataframe(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        range_str: str | None = None,
        header_row: int = 0,
    ) -> pd.DataFrame:
        """
        读取工作表数据并转换为 pandas DataFrame

        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            range_str: 范围字符串，如 "A1:Z100"，默认读取全部
            header_row: 表头所在行（0-indexed），默认第一行

        Returns:
            pandas DataFrame
        """
        values = await self.read_sheet_values(spreadsheet_token, sheet_id, range_str)

        if not values:
            logger.warning("[LarkSheetsClient.read_sheet_as_dataframe] 空数据")
            return pd.DataFrame()

        # 提取表头和数据
        if header_row < len(values):
            headers = values[header_row]
            data_rows = values[header_row + 1 :]
        else:
            headers = [f"col_{i}" for i in range(len(values[0]))]
            data_rows = values

        # 确保所有行长度一致
        max_cols = len(headers)
        normalized_rows = []
        for row in data_rows:
            if len(row) < max_cols:
                row = row + [None] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            normalized_rows.append(row)

        df = pd.DataFrame(normalized_rows, columns=headers)

        logger.info(
            f"[LarkSheetsClient.read_sheet_as_dataframe] 转换完成, " f"shape={df.shape}"
        )

        return df

    async def write_sheet_values(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        values: list[list[Any]],
        range_str: str | None = None,
    ) -> bool:
        """
        写入工作表数据

        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            values: 二维数组形式的数据
            range_str: 范围字符串，如 "A1:Z100"

        Returns:
            是否写入成功
        """
        if not values:
            return True

        rows = len(values)
        cols = max(len(row) for row in values) if values else 0

        # 自动计算范围
        if not range_str:
            end_col = chr(65 + cols - 1) if cols <= 26 else "Z"
            range_str = f"A1:{end_col}{rows}"

        full_range = f"{sheet_id}!{range_str}"

        logger.info(
            f"[LarkSheetsClient.write_sheet_values] 写入数据, "
            f"spreadsheet_token={spreadsheet_token}, range={full_range}, rows={rows}"
        )

        endpoint = f"/sheet/v2/spreadsheets/{spreadsheet_token}/values"
        json_data = {
            "valueRange": {
                "range": full_range,
                "values": values,
            }
        }
        logger.info(f"[LarkSheetsClient.write_sheet_values] 发送写入请求, json_data is {json_data}")

        await self._request("PUT", endpoint, json_data=json_data)

        logger.info("[LarkSheetsClient.write_sheet_values] 写入成功")

        return True

    async def write_dataframe_to_sheet(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        df: pd.DataFrame,
        include_header: bool = True,
        start_row: int | None = None,
    ) -> bool:
        """
        将 pandas DataFrame 写入工作表

        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            df: pandas DataFrame
            include_header: 是否包含表头
            start_row: 起始行号（从1开始），None 表示从第1行开始

        Returns:
            是否写入成功
        """
        # 转换 DataFrame 为二维数组
        df_converted = df.astype(object).fillna("")
        values = []

        if include_header:
            values.append(df_converted.columns.tolist())

        # 转换每个单元格值，处理特殊类型（如 @ 提及）
        for row in df_converted.values.tolist():
            converted_row = [_convert_cell_value_for_write(cell) for cell in row]
            values.append(converted_row)

        # 计算范围字符串
        range_str = None
        if start_row is not None:
            rows = len(values)
            cols = len(df.columns)
            end_col = chr(65 + cols - 1) if cols <= 26 else "Z"
            end_row = start_row + rows - 1
            range_str = f"A{start_row}:{end_col}{end_row}"

        return await self.write_sheet_values(
            spreadsheet_token=spreadsheet_token,
            sheet_id=sheet_id,
            values=values,
            range_str=range_str,
        )

    async def write_rows_to_sheet(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        df: pd.DataFrame,
    ) -> bool:
        """
        将 DataFrame 的每一行写入到其对应的行位置

        根据 DataFrame 的索引确定每行在表格中的位置（索引 + 2，因为有表头且索引从0开始）

        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            df: pandas DataFrame（索引对应表格行号 - 2）

        Returns:
            是否写入成功
        """
        if df.empty:
            return True

        # 转换 DataFrame 为可写入格式
        df_converted = df.astype(object).fillna("")

        # 按行写入，每行写入到其对应的位置
        for idx in df.index:
            row_num = idx + 2  # DataFrame 索引 + 2 = 表格行号（有表头，索引从0开始）
            row_data = df_converted.loc[idx].tolist()
            converted_row = [_convert_cell_value_for_write(cell) for cell in row_data]

            # 计算范围：从 A{row_num} 到 {end_col}{row_num}
            cols = len(df.columns)
            end_col = chr(65 + cols - 1) if cols <= 26 else "Z"
            range_str = f"A{row_num}:{end_col}{row_num}"

            await self.write_sheet_values(
                spreadsheet_token=spreadsheet_token,
                sheet_id=sheet_id,
                values=[converted_row],
                range_str=range_str,
            )

        logger.info(
            f"[LarkSheetsClient.write_rows_to_sheet] 写入完成, "
            f"共 {len(df)} 行"
        )

        return True

    async def add_sheet(
        self,
        spreadsheet_token: str,
        title: str,
        index: int = 0,
    ) -> str:
        """
        添加新工作表

        Args:
            spreadsheet_token: 电子表格 token
            title: 工作表标题
            index: 工作表位置索引

        Returns:
            新工作表的 sheet_id
        """
        logger.info(
            f"[LarkSheetsClient.add_sheet] 添加工作表, "
            f"spreadsheet_token={spreadsheet_token}, title={title}"
        )

        endpoint = f"/sheets/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update"
        json_data = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "index": index,
                        }
                    }
                }
            ]
        }

        data = await self._request("POST", endpoint, json_data=json_data)

        sheet_id = data["data"]["replies"][0]["addSheet"]["properties"]["sheetId"]
        logger.info(f"[LarkSheetsClient.add_sheet] 添加成功, sheet_id={sheet_id}")

        return sheet_id


class LarkBitableClient(LarkBaseClient):
    """
    Lark Bitable (多维表格) API 客户端

    提供多维表格的 CRUD 操作
    """

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        filter_formula: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        列出表格记录

        Args:
            app_token: 多维表格 App Token
            table_id: 数据表 ID
            filter_formula: 过滤公式，如 'CurrentValue.[status]="new"'
            page_size: 每页数量，最大 500
            page_token: 分页标记

        Returns:
            包含 items 和 page_token 的响应
        """
        logger.info(
            f"[LarkBitableClient.list_records] 查询记录, "
            f"table_id={table_id}, filter={filter_formula}"
        )

        endpoint = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params: dict[str, Any] = {"page_size": page_size}

        if filter_formula:
            params["filter"] = filter_formula
        if page_token:
            params["page_token"] = page_token

        data = await self._request("GET", endpoint, params=params)

        items = data.get("data", {}).get("items", [])
        has_more = data.get("data", {}).get("has_more", False)
        next_page_token = data.get("data", {}).get("page_token")

        logger.info(
            f"[LarkBitableClient.list_records] 查询完成, "
            f"返回 {len(items)} 条记录, has_more={has_more}"
        )

        return {
            "items": items,
            "has_more": has_more,
            "page_token": next_page_token,
        }

    async def list_all_records(
        self,
        app_token: str,
        table_id: str,
        filter_formula: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        列出所有符合条件的记录（自动分页）

        Args:
            app_token: 多维表格 App Token
            table_id: 数据表 ID
            filter_formula: 过滤公式

        Returns:
            所有记录列表
        """
        all_items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            result = await self.list_records(
                app_token=app_token,
                table_id=table_id,
                filter_formula=filter_formula,
                page_token=page_token,
            )

            all_items.extend(result["items"])

            if not result["has_more"]:
                break

            page_token = result["page_token"]

        logger.info(
            f"[LarkBitableClient.list_all_records] 共获取 {len(all_items)} 条记录"
        )

        return all_items

    async def list_records_as_dataframe(
        self,
        app_token: str,
        table_id: str,
        filter_formula: str | None = None,
    ) -> pd.DataFrame:
        """
        列出所有记录并转换为 pandas DataFrame

        Args:
            app_token: 多维表格 App Token
            table_id: 数据表 ID
            filter_formula: 过滤公式

        Returns:
            pandas DataFrame
        """
        records = await self.list_all_records(
            app_token=app_token,
            table_id=table_id,
            filter_formula=filter_formula,
        )

        if not records:
            return pd.DataFrame()

        # 提取字段数据
        rows = []
        for record in records:
            row = {"record_id": record.get("record_id", "")}
            fields = record.get("fields", {})
            for key, value in fields.items():
                # 处理多行文本等复杂类型
                if isinstance(value, list):
                    if value and isinstance(value[0], dict) and "text" in value[0]:
                        value = "".join(item.get("text", "") for item in value)
                    else:
                        value = str(value)
                row[key] = value
            rows.append(row)

        df = pd.DataFrame(rows)

        logger.info(
            f"[LarkBitableClient.list_records_as_dataframe] 转换完成, "
            f"shape={df.shape}"
        )

        return df

    async def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> bool:
        """
        更新单条记录

        Args:
            app_token: 多维表格 App Token
            table_id: 数据表 ID
            record_id: 记录 ID
            fields: 要更新的字段

        Returns:
            是否更新成功
        """
        logger.info(
            f"[LarkBitableClient.update_record] 更新记录, "
            f"record_id={record_id}, fields={list(fields.keys())}"
        )

        endpoint = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        json_data = {"fields": fields}

        await self._request("PUT", endpoint, json_data=json_data)

        logger.info(f"[LarkBitableClient.update_record] 更新成功: {record_id}")

        return True

    async def batch_update_records(
        self,
        app_token: str,
        table_id: str,
        records: list[dict[str, Any]],
    ) -> int:
        """
        批量更新记录

        Args:
            app_token: 多维表格 App Token
            table_id: 数据表 ID
            records: 记录列表，每条记录包含 record_id 和 fields

        Returns:
            成功更新的记录数
        """
        if not records:
            return 0

        logger.info(
            f"[LarkBitableClient.batch_update_records] 批量更新 {len(records)} 条记录"
        )

        endpoint = (
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
        )

        # Lark 批量更新限制每次 500 条
        batch_size = 500
        success_count = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            json_data = {"records": batch}

            try:
                await self._request("POST", endpoint, json_data=json_data)
                success_count += len(batch)
            except Exception as e:
                logger.error(
                    f"[LarkBitableClient.batch_update_records] "
                    f"批量更新失败: {e}, batch={i // batch_size + 1}"
                )

        logger.info(
            f"[LarkBitableClient.batch_update_records] "
            f"批量更新完成, 成功 {success_count}/{len(records)}"
        )

        return success_count
