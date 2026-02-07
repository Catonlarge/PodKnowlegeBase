"""
AI 服务统一兜底装饰器

提供统一的异常处理和兜底逻辑，支持自定义兜底函数或静态兜底值。
"""
import functools
from loguru import logger
from typing import Callable, Any, Optional


def ai_fallback(
    fallback_func: Optional[Callable] = None,
    fallback_value: Any = None,
    log_level: str = "warning",
    log_message: Optional[str] = None
):
    """
    AI 服务统一兜底装饰器

    Args:
        fallback_func: 兜底函数（动态生成兜底值）
        fallback_value: 静态兜底值
        log_level: 日志级别（warning/info/error）
        log_message: 自定义日志消息，默认使用函数名

    Usage:
        # 使用静态兜底值
        @ai_fallback(fallback_value=[])
        def get_corrections(episode_id):
            ...

        # 使用动态兜底函数
        @ai_fallback(fallback_func=lambda episode: [...])
        def generate_marketing_copy(episode_id):
            ...

        # 同时提供两者时，fallback_func 优先
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                message = log_message or f"{func.__name__} 失败"
                getattr(logger, log_level)(f"{message}: {e}")

                # fallback_func 优先于 fallback_value
                if fallback_func:
                    try:
                        return fallback_func(*args, **kwargs)
                    except Exception as fallback_error:
                        logger.error(f"兜底函数也失败: {fallback_error}")
                        return fallback_value
                return fallback_value
        return wrapper
    return decorator


def silent_fallback(return_value: Any = None):
    """
    静默兜底装饰器 - 失败时静默返回默认值

    Args:
        return_value: 默认返回值

    Usage:
        @silent_fallback(return_value=[])
        def scan_and_correct(episode_id):
            ...
    """
    return ai_fallback(
        fallback_value=return_value,
        log_level="debug"  # 降低日志级别
    )


def log_and_reraise(log_message: Optional[str] = None):
    """
    记录日志后重新抛出异常（不兜底）

    用于需要记录失败但不提供兜底的场景。

    Args:
        log_message: 自定义日志消息

    Usage:
        @log_and_reraise("翻译服务调用失败")
        def translate_batch(cues):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                message = log_message or f"{func.__name__} 失败"
                logger.error(f"{message}: {e}")
                raise
        return wrapper
    return decorator
