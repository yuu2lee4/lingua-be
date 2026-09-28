"""Define the configurable parameters for the agent."""

import os
import warnings
from typing import Any

# Disable protobuf version warnings early to avoid noise
warnings.filterwarnings(
    "ignore", category=UserWarning, module="google.protobuf.runtime_version"
)

# Disable various debug loggers that create noise
import logging

logging.getLogger("opik").setLevel(logging.WARNING)
logging.getLogger("custom_batch_logger").setLevel(logging.WARNING)
logging.getLogger("opik.evaluation.metrics.custom_batch_logger").setLevel(
    logging.WARNING
)
logging.getLogger("apollo.python_3x").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)


# 替代 distutils.util.strtobool (Python 3.13 兼容)
def strtobool(val: str) -> bool:
    """Convert a string representation of truth to true or false."""
    if isinstance(val, str):
        val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError(f"invalid truth value {val!r}")


from .settings import APOLLO_URL, ENV_LOCAL
from .settings import APP_ENV
from apollo.apollo_client import ApolloClient


# 延迟导入 logger 避免循环依赖
def get_logger():
    """延迟导入 logger"""
    from app.logger import logger

    return logger


class KeyNotFoundError(Exception):
    """配置项未找到异常"""


class Configuration:
    def __init__(self):
        self._client = None
        self._initialize()

    def _safe_get_config(self, key: str, default: Any = None) -> Any:
        """安全获取配置项"""
        try:
            value = self._client.get_value(key, default)
            if not value:
                raise KeyNotFoundError(f"Config key {key} not found")
            get_logger().info(f"Config key {key} value {value}")
            return value

        except Exception:
            raise

    def _safe_get_env_config(self, env_key: str, default: Any = None) -> Any:
        """
        安全从环境变量获取配置项
        """
        try:
            value = os.getenv(env_key, default)
            if not value:
                raise KeyNotFoundError(
                    f"Environment variable {env_key} not found and no default provided"
                )
            get_logger().info(f"Config key {env_key} value {value}")
            return value

        except Exception:
            raise

    def _create_apollo_client(self):
        """创建Apollo客户端"""
        return ApolloClient(
            app_id=self.application_name,
            cluster="default",
            config_url=APOLLO_URL,
            start_hot_update=False,
        )

    def _initialize(self):
        """初始化"""
        try:
            self.application_name = "ai-translation"
            self._client = self._create_apollo_client()

            # 修复 apollo-python-client 的 bug：确保必要的属性被初始化
            if not hasattr(self._client, '_notification_map'):
                self._client._notification_map = {}

            # vertexAI
            self.vertexai_google_genai_use_vertexai = self._safe_get_config(
                "vertexai.google_genai_use_vertexai"
            )
            self.vertexai_google_cloud_project = self._safe_get_config(
                "vertexai.google_cloud_project"
            )
            self.vertexai_google_cloud_location = self._safe_get_config(
                "vertexai.google_cloud_location"
            )
            self.vertexai_google_application_credentials = self._safe_get_config(
                "vertexai.google_application_credentials"
            )

            # llm
            self.llm_model_name = self._safe_get_config("llm.model_name")
            self.llm_include_thoughts = strtobool(
                self._safe_get_config("llm.include_thoughts")
            )
            self.llm_default_model_name = self._safe_get_config(
                "llm.default_model_name"
            )
            self.llm_fallback_model_name = self._safe_get_config(
                "llm.fallback_model_name"
            )
            self.llm_guardrail_model_name = self._safe_get_config(
                "llm.guardrail_model_name"
            )
            self.llm_use_dynamic_prompt = strtobool(
                self._safe_get_config("llm.use_dynamic_prompt")
            )
            self.llm_image_analysis_model = self._safe_get_config(
                "llm.image_analysis_model"
            )

            self.llm_image_analysis_model_list = []
            if self.llm_image_analysis_model:
                self.llm_image_analysis_model_list = [
                    model.strip()
                    for model in self.llm_image_analysis_model.split(",")
                    if model.strip()
                ]

            # 构建模型回退映射字典
            self.llm_fallbacks = {}
            if self.llm_model_name and self.llm_fallback_model_name:
                # 按逗号分割模型名称和回退模型名称
                model_names = [
                    name.strip()
                    for name in self.llm_model_name.split(",")
                    if name.strip()
                ]
                fallback_names = [
                    name.strip()
                    for name in self.llm_fallback_model_name.split(",")
                    if name.strip()
                ]

                # 构建一一对应的映射关系
                for i, model in enumerate(model_names):
                    if i < len(fallback_names):
                        self.llm_fallbacks[model] = fallback_names[i]
                    # 如果回退模型数量少于主模型数量，后续主模型使用最后一个回退模型
                    elif fallback_names:
                        self.llm_fallbacks[model] = fallback_names[-1]

            self.timezone = self._safe_get_config("timezone")

            # opik
            self.opik_url = self._safe_get_config("opik.url")
            self.opik_project_name = self._safe_get_config("opik.project_name")
            # opik并发控制配置
            self.opik_max_concurrent_traces = self._safe_get_config(
                "opik.max_concurrent_traces", 100
            )
            self.opik_max_concurrent_spans = self._safe_get_config(
                "opik.max_concurrent_spans", 200
            )

            # redis
            self.redis_url = self._safe_get_config("redis.url")

            # xxl-job
            self.xxl_app_name = "ai-translation"
            self.xxl_admin_baseurl = self._safe_get_config("xxl.baseurl")
            self.xxl_listen_host = self._safe_get_config("xxl.listen_host")
            self.xxl_listen_port = self._safe_get_config("xxl.listen_port")
            self.xxl_access_token = self._safe_get_config("xxl.access_token")

            # consul
            if APP_ENV == ENV_LOCAL:
                self.consul_host = self._safe_get_config("consul.host")
                self.consul_port = int(self._safe_get_config("consul.port"))
            else:
                self.consul_host = self._safe_get_env_config("HOST_IP")
                self.consul_port = int(self._safe_get_env_config("CONSUL_PORT"))
            self.consul_cache_ttl = int(self._safe_get_config("consul.cache_ttl", 30))
            self.consul_timeout = int(self._safe_get_config("consul.timeout", 10))

            self.jina_ai_api_key = self._safe_get_config("jina_ai_api_key")
            self.twitter_api_endpoint = self._safe_get_config("twitter.endpoint")
            self.twitter_api_key = self._safe_get_config("twitter.apikey")

            # openAI
            self.open_ai_api_key = self._safe_get_config("open_ai_api_key")

            # claudeAI
            self.claude_api_key = self._safe_get_config("claude_api_key")

            # Bedrock 配置（可选，通过 use_bedrock 开关控制）
            self.use_bedrock = strtobool(
                self._safe_get_config("bedrock.use_bedrock", "true")
            )
            if self.use_bedrock:
                self.aws_bearer_token_bedrock = self._safe_get_config(
                    "bedrock.aws_bearer_token"
                )
                self.aws_region = self._safe_get_config(
                    "bedrock.aws_region", "us-west-2"
                )
            else:
                self.aws_bearer_token_bedrock = ""
                self.aws_region = ""

            # serpapi
            self.serpapi_api_key = self._safe_get_config("serpapi_api_key")

            # MySQL 数据库配置
            self.mysql_host = self._safe_get_config("mysql.host")
            self.mysql_port = int(self._safe_get_config("mysql.port"))
            self.mysql_database = self._safe_get_config("mysql.db_name")
            self.mysql_user = self._safe_get_config("mysql.user_name")
            self.mysql_password = self._safe_get_config("mysql.password")
            self.mysql_pool_size = int(self._safe_get_config("mysql.pool_size", "10"))
            self.mysql_pool_recycle = int(
                self._safe_get_config("mysql.pool_recycle", "3600")
            )

            # Lark Sheets 配置 (使用国际版 larksuite)
            self.lark_app_id = self._safe_get_config("lark.app_id")
            self.lark_app_secret = self._safe_get_config("lark.app_secret")
            # 支持逗号分隔的多个 spreadsheet_token
            raw_token = self._safe_get_config("lark.spreadsheet_token")
            self.lark_spreadsheet_tokens: list[str] = [
                t.strip() for t in raw_token.split(",") if t.strip()
            ]
            # 向后兼容：取第一个 token
            self.lark_spreadsheet_token = self.lark_spreadsheet_tokens[0]

            # Task API 鉴权
            self.task_api_bearer_token = self._safe_get_config(
                "task_api.bearer_token", ""
            )

            # CUA 沙盒配置
            self.cua_sandbox_url = self._safe_get_config("cua.sandbox_url", "http://localhost:8000")

            # set env
            # vertexAI
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = (
                self.vertexai_google_genai_use_vertexai
            )
            os.environ["GOOGLE_CLOUD_PROJECT"] = self.vertexai_google_cloud_project
            os.environ["GOOGLE_CLOUD_LOCATION"] = self.vertexai_google_cloud_location
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                self.vertexai_google_application_credentials
            )
            os.environ["VERTEXAI_PROJECT"] = self.vertexai_google_cloud_project
            os.environ["VERTEXAI_LOCATION"] = self.vertexai_google_cloud_location

            # openAI
            os.environ["OPENAI_API_KEY"] = self.open_ai_api_key

            # claudeAI
            os.environ["ANTHROPIC_API_KEY"] = self.claude_api_key

            # Bedrock
            os.environ["USE_BEDROCK"] = "true" if self.use_bedrock else "false"
            if self.aws_bearer_token_bedrock:
                os.environ["AWS_BEARER_TOKEN_BEDROCK"] = (
                    self.aws_bearer_token_bedrock
                )
            if self.aws_region:
                os.environ["AWS_REGION"] = self.aws_region

            # CUA 沙盒
            os.environ["CUA_SANDBOX_URL"] = self.cua_sandbox_url

            # opik
            os.environ["OPIK_URL_OVERRIDE"] = self.opik_url
            os.environ["OPIK_PROJECT_NAME"] = self.opik_project_name

        except Exception:
            raise


try:
    Config = Configuration()

except Exception:
    raise
