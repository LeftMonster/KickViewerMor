import functools


from functools import wraps
import time
from inspect import signature, Parameter


from utils.logger_util import logger


def retry(exception_to_catch=Exception, delay_seconds=1, num_times=5):
    """
    装饰器，在遇到指定异常时重试函数执行

    参数:
        exception_to_catch: 要捕获的异常类型
        delay_seconds: 重试之间的延迟（秒）
        num_times: 最大重试次数
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < num_times:
                try:
                    return func(*args, **kwargs)
                except exception_to_catch as e:
                    attempts += 1
                    if attempts == num_times:
                        # 达到最大重试次数，重新抛出异常
                        raise
                    print(f"尝试 {attempts}/{num_times} 失败: {str(e)}. {delay_seconds}秒后重试...")
                    time.sleep(delay_seconds)

        return wrapper

    return decorator


def playwright_error_handler(func):
    """Playwright 错误处理装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['target closed', 'browser closed', 'context closed']):
                logger.warning(f"Playwright 资源已关闭: {e}")
                return None
            else:
                logger.error(f"Playwright 操作失败: {e}")
                raise
    return wrapper