"""
自定义异常类

定义翻译服务中使用的各种异常
"""


class TranslationServiceError(Exception):
    """翻译服务基础异常"""

    def __init__(self, message: str = "翻译服务错误"):
        self.message = message
        super().__init__(self.message)


class JobNotFoundError(TranslationServiceError):
    """任务未找到"""

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"任务未找到: {job_id}")


class JobAlreadyExistsError(TranslationServiceError):
    """任务已存在"""

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"任务已存在: {job_id}")


class JobCancelledError(TranslationServiceError):
    """任务已取消"""

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"任务已取消: {job_id}")


class TranslationFailedError(TranslationServiceError):
    """翻译失败"""

    def __init__(self, lang: str, reason: str):
        self.lang = lang
        self.reason = reason
        super().__init__(f"翻译失败 [{lang}]: {reason}")


class QualityCheckFailedError(TranslationServiceError):
    """质量检查失败"""

    def __init__(self, lang: str, score: int, threshold: int):
        self.lang = lang
        self.score = score
        self.threshold = threshold
        super().__init__(f"质量检查失败 [{lang}]: 得分 {score} 低于阈值 {threshold}")


class LLMClientError(TranslationServiceError):
    """LLM 客户端错误"""

    def __init__(self, model: str, error: str):
        self.model = model
        self.error = error
        super().__init__(f"LLM 调用失败 [{model}]: {error}")


class GlossaryLoadError(TranslationServiceError):
    """术语表加载错误"""

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"术语表加载失败 [{path}]: {reason}")


class MaxRetriesExceededError(TranslationServiceError):
    """超过最大重试次数"""

    def __init__(self, lang: str, max_retries: int):
        self.lang = lang
        self.max_retries = max_retries
        super().__init__(f"超过最大重试次数 [{lang}]: {max_retries}")


# ============ 沙盒与视觉评审异常 ============


class SandboxError(TranslationServiceError):
    """浏览器沙盒错误"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"沙盒错误: {reason}")


class VisualReviewError(TranslationServiceError):
    """视觉评审错误"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"视觉评审错误: {reason}")


# ============ 数据库异常 ============


class DatabaseError(TranslationServiceError):
    """数据库基础异常"""

    def __init__(self, message: str = "数据库错误"):
        super().__init__(message)


class DatabaseConnectionError(DatabaseError):
    """数据库连接错误"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"数据库连接失败: {reason}")


class DatabaseQueryError(DatabaseError):
    """数据库查询错误"""

    def __init__(self, query: str, reason: str):
        self.query = query
        self.reason = reason
        # 截断过长的 SQL
        truncated_query = query[:100] + "..." if len(query) > 100 else query
        super().__init__(f"数据库查询失败: {reason}, SQL: {truncated_query}")


# ============ Task API 异常 ============


class TaskNotFoundError(TranslationServiceError):
    """任务未找到"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class InvalidTaskParamsError(TranslationServiceError):
    """任务参数无效"""

    def __init__(self, message: str):
        super().__init__(message)


class TaskContentBlockedError(TranslationServiceError):
    """任务内容被屏蔽"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Content blocked for task: {task_id}")


# ============ 术语表异常 ============


class GlossaryTermNotFoundError(TranslationServiceError):
    """术语未找到"""

    def __init__(self, term_id: str):
        self.term_id = term_id
        super().__init__(f"术语未找到: {term_id}")


class GlossaryTermExistsError(TranslationServiceError):
    """术语已存在"""

    def __init__(self, term_en: str):
        self.term_en = term_en
        super().__init__(f"术语已存在: {term_en}")
