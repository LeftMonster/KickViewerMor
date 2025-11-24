import logging
import sys
import os
import zipfile
import glob
from datetime import datetime, timedelta
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import atexit


# from utils.config_util import get_env

class DefaultColorFormatter(logging.Formatter):
    # ANSI 颜色定义
    COLORS = {
        'DEBUG': '\033[94m',  # 蓝色
        'INFO': '\033[92m',  # 绿色
        'WARNING': '\033[93m',  # 黄色
        'ERROR': '\033[91m',  # 红色
        'CRITICAL': '\033[95m',  # 紫红色
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


class FileOnlyFormatter(logging.Formatter):
    """文件输出专用格式器，不包含颜色代码"""

    def format(self, record):
        return super().format(record)


class DailyRotatingFileHandler(logging.FileHandler):
    """按天轮转的文件处理器"""

    def __init__(self, log_dir='logs', encoding='utf-8'):
        # 确保log_dir是相对于Python运行目录（当前工作目录）
        self.log_dir = Path.cwd() / log_dir
        self.log_dir.mkdir(exist_ok=True)

        # 获取当前日期的日志文件
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{self.current_date}.log"

        super().__init__(log_file, encoding=encoding)

        # 用于异步打包的线程池
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='LogArchiver')

        # 程序退出时清理线程池
        atexit.register(self._cleanup)

    def emit(self, record):
        """重写emit方法，检查是否需要切换日志文件"""
        current_date = datetime.now().strftime('%Y-%m-%d')

        # 如果日期发生变化，需要切换日志文件
        if current_date != self.current_date:
            self._rotate_log_file(current_date)

        super().emit(record)

    def _rotate_log_file(self, new_date):
        """切换到新的日志文件"""
        # 关闭当前文件
        if self.stream:
            self.stream.close()

        # 检查是否需要打包上个月的日志
        self._check_and_archive_monthly_logs()

        # 更新到新的日志文件
        self.current_date = new_date
        new_log_file = self.log_dir / f"{new_date}.log"
        self.baseFilename = str(new_log_file)

        # 重新打开文件流
        self.stream = self._open()

    def _check_and_archive_monthly_logs(self):
        """检查并打包上个月的日志"""
        try:
            # 获取上个月的年月
            last_month = datetime.now().replace(day=1) - timedelta(days=1)
            year_month = last_month.strftime('%Y-%m')

            # 查找上个月的所有日志文件
            pattern = f"{year_month}-*.log"
            log_files = list(self.log_dir.glob(pattern))

            if log_files:
                # 异步打包，避免阻塞主线程
                self.executor.submit(self._archive_monthly_logs, year_month, log_files)
        except Exception as e:
            # 打包失败不应该影响正常日志记录
            print(f"Archive logs error: {e}", file=sys.stderr)

    def _archive_monthly_logs(self, year_month, log_files):
        """打包月度日志文件"""
        try:
            zip_filename = self.log_dir / f"{year_month}-log.zip"

            # 如果zip文件已存在，跳过
            if zip_filename.exists():
                return

            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for log_file in log_files:
                    if log_file.exists():
                        zipf.write(log_file, log_file.name)

            # 打包成功后删除原始日志文件
            for log_file in log_files:
                try:
                    log_file.unlink()
                except OSError:
                    pass  # 文件可能正在使用，忽略删除错误

            print(f"Monthly logs archived: {zip_filename}")
        except Exception as e:
            print(f"Failed to archive monthly logs: {e}", file=sys.stderr)

    def _cleanup(self):
        """清理资源"""
        try:
            self.executor.shutdown(wait=True, timeout=5)
        except:
            pass


class EnhancedLogger:
    """增强的日志记录器类"""

    def __init__(self, name=None, log_dir='logs', level=logging.INFO):
        self.logger = logging.getLogger(name or 'app')  # 使用默认名称'app'而不是模块路径
        self.logger.setLevel(level)

        # 避免重复添加处理器
        if not self.logger.handlers:
            self._setup_handlers(log_dir)

    def _setup_handlers(self, log_dir):
        """设置日志处理器"""
        # 控制台处理器 - 带颜色
        console_handler = logging.StreamHandler(sys.stdout)
        # console_formatter = DefaultColorFormatter(
        #     '%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'
        # )
        console_formatter = DefaultColorFormatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # 文件处理器 - 不带颜色，按天轮转
        # 确保log_dir是相对于Python运行目录
        file_handler = DailyRotatingFileHandler(log_dir)
        # file_formatter = FileOnlyFormatter(
        #     '%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'
        # )
        file_formatter = FileOnlyFormatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

    def get_logger(self):
        """获取日志记录器实例"""
        return self.logger


# 创建默认的日志记录器实例，使用Python运行目录下的logs文件夹
_default_logger = EnhancedLogger()
logger = _default_logger.get_logger()


# 提供便捷的创建函数
def get_logger(name=None, log_dir='logs', level=logging.INFO):
    """
    获取增强的日志记录器

    Args:
        name: 日志记录器名称，默认为调用模块名
        log_dir: 日志目录，默认为 'logs'
        level: 日志级别，默认为 INFO

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    enhanced_logger = EnhancedLogger(name, log_dir, level)
    return enhanced_logger.get_logger()


# 使用示例
if __name__ == "__main__":
    # 测试日志功能
    test_logger = get_logger('test_logger')

    test_logger.debug("This is a debug message")
    test_logger.info("This is an info message")
    test_logger.warning("This is a warning message")
    test_logger.error("This is an error message")
    test_logger.critical("This is a critical message")

    print(f"Log files will be saved to: {Path.cwd() / 'logs'}")