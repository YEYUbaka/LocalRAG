import logging
from typing import Any
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.config import settings

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # 秒

# 火山方舟（豆包）特殊模型标识
VOLCENGINE_MODELS = [
    "doubao-pro", "doubao-lite", "doubao-vision",
    "doubao-1.5", "deepseek-r1", "deepseek-v3",
]


def is_volcengine_model(model_name: str) -> bool:
    """判断是否为火山方舟模型"""
    # 接入点 ID 格式：ep-20240xxx
    if model_name.startswith("ep-"):
        return True
    return any(model_name.startswith(prefix) for prefix in VOLCENGINE_MODELS)


def get_chat_model(
    model_name: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    extra_params: dict[str, Any] | None = None,
) -> BaseChatModel:
    """
    获取 LLM 模型实例

    Args:
        model_name: 模型名称，None 则使用配置
        temperature: 温度参数，None 则使用配置
        max_tokens: 最大生成长度，None 则使用配置
        extra_params: 额外参数（如火山方舟的 thinking 配置）
    """
    effective_model = model_name or settings.llm_model_name
    effective_temperature = temperature if temperature is not None else settings.temperature
    effective_max_tokens = max_tokens if max_tokens is not None else settings.max_tokens

    # 基础参数
    kwargs = {
        "model": effective_model,
        "api_key": settings.llm_api_key or "sk-placeholder",
        "base_url": settings.llm_base_url,
        "temperature": effective_temperature,
        "max_tokens": effective_max_tokens,
        "streaming": True,
        "request_timeout": 120,  # 120 秒超时（豆包深度思考可能较慢）
        "max_retries": MAX_RETRIES,
    }

    # 火山方舟模型特殊处理
    if is_volcengine_model(effective_model):
        # 检查是否使用了模型名称而不是接入点 ID
        if any(effective_model.startswith(prefix) for prefix in VOLCENGINE_MODELS):
            logger.warning(f"检测到火山方舟模型名称 '{effective_model}'，火山方舟需要使用接入点 ID（如 ep-20240xxx）。请在火山引擎控制台创建接入点后使用接入点 ID。")
        # 豆包 vision 模型需要特殊处理
        if "vision" in effective_model:
            logger.info(f"使用火山方舟视觉模型: {effective_model}")
        # 深度思考模型（deepseek-r1）需要更长超时
        if "deepseek-r1" in effective_model or "thinking" in effective_model:
            kwargs["request_timeout"] = 300  # 5 分钟超时
            logger.info(f"使用深度思考模型，超时延长至 300 秒: {effective_model}")

    # 合并额外参数
    if extra_params:
        kwargs.update(extra_params)

    logger.info(f"初始化 LLM 模型: {effective_model}, base_url: {settings.llm_base_url}")
    return ChatOpenAI(**kwargs)


def get_vision_model() -> BaseChatModel:
    """获取支持视觉的模型（用于图片理解）"""
    # 优先使用 vision 模型，否则使用普通模型
    model_name = settings.llm_model_name
    if is_volcengine_model(model_name) and "vision" not in model_name:
        # 尝试使用对应的 vision 版本
        vision_model = model_name.replace("-pro-", "-vision-pro-").replace("-lite-", "-vision-lite-")
        if vision_model != model_name:
            logger.info(f"切换到视觉模型: {vision_model}")
            model_name = vision_model

    return get_chat_model(model_name=model_name)


def get_thinking_model() -> BaseChatModel:
    """获取支持深度思考的模型"""
    model_name = settings.llm_model_name

    # 对于火山方舟，使用 deepseek-r1 或 doubao-thinking
    if is_volcengine_model(model_name):
        if "deepseek" not in model_name:
            # 尝试使用 deepseek-r1
            logger.info("切换到深度思考模型: deepseek-r1")
            model_name = "deepseek-r1"

    return get_chat_model(
        model_name=model_name,
        temperature=1.0,  # 深度思考模式通常需要更高温度
        extra_params={"request_timeout": 300},
    )
