"""
日志工具模块
提供统一的日志配置和使用接口
"""

import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    
    # 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    def format(self, record):
        # 添加线程信息
        record.thread_name = threading.current_thread().name
        record.thread_id = threading.current_thread().ident
        
        # 格式化消息
        log_message = super().format(record)
        
        # 如果是控制台输出，添加颜色
        if hasattr(record, 'add_color') and record.add_color:
            color = self.COLORS.get(record.levelname, '')
            reset = self.COLORS['RESET']
            return f"{color}{log_message}{reset}"
        
        return log_message


class LoggerManager:
    """日志管理器"""
    
    def __init__(self):
        self._loggers = {}
        self._initialized = False
        self.log_dir = None
        
    def initialize(self, 
                   log_dir: str = "logs",
                   max_file_size: int = 100 * 1024 * 1024,  # 100MB
                   backup_count: int = 7,  # 保存7天
                   console_level: str = "INFO",
                   file_level: str = "DEBUG"):
        """
        初始化日志系统
        
        Args:
            log_dir: 日志目录
            max_file_size: 单个日志文件最大大小（字节）
            backup_count: 保留的备份文件数量
            console_level: 控制台日志级别
            file_level: 文件日志级别
        """
        if self._initialized:
            return
            
        # 创建日志目录
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 设置根日志级别
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # 清除现有的处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 创建格式化器
        detailed_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | '
                'Thread-%(thread_name)s(%(thread_id)d) | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, console_level.upper()))
        console_handler.setFormatter(simple_formatter)
        # 标记为控制台输出，用于添加颜色
        console_handler.addFilter(lambda record: setattr(record, 'add_color', True) or True)
        root_logger.addHandler(console_handler)
        
        # 通用日志文件处理器（所有级别）
        all_log_file = self.log_dir / "app.log"
        all_handler = logging.handlers.RotatingFileHandler(
            all_log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        all_handler.setLevel(getattr(logging, file_level.upper()))
        all_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(all_handler)
        
        # 错误日志文件处理器（只记录ERROR及以上级别）
        error_log_file = self.log_dir / "error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        
        # 错误日志使用更详细的格式，包含栈信息
        error_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | '
                'Thread-%(thread_name)s(%(thread_id)d) | %(funcName)s() | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)
        
        # 访问日志文件处理器（用于API访问日志）
        access_log_file = self.log_dir / "access.log"
        access_handler = logging.handlers.RotatingFileHandler(
            access_log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(simple_formatter)
        
        # 创建专门的访问日志记录器
        access_logger = logging.getLogger('access')
        access_logger.setLevel(logging.INFO)
        access_logger.addHandler(access_handler)
        access_logger.propagate = False  # 不传播到根日志器
        
        self._initialized = True
        
        # 记录初始化信息
        logger = self.get_logger(__name__)
        logger.info("=" * 60)
        logger.info("日志系统初始化完成")
        logger.info(f"日志目录: {self.log_dir.absolute()}")
        logger.info(f"文件大小限制: {max_file_size / 1024 / 1024:.1f}MB")
        logger.info(f"备份文件数量: {backup_count}")
        logger.info(f"控制台日志级别: {console_level}")
        logger.info(f"文件日志级别: {file_level}")
        logger.info("=" * 60)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称，通常使用 __name__
            
        Returns:
            logging.Logger: 日志记录器实例
        """
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]
    
    def get_access_logger(self) -> logging.Logger:
        """获取访问日志记录器"""
        return logging.getLogger('access')
    
    def log_exception(self, logger: logging.Logger, message: str = "发生异常"):
        """
        记录异常信息，包含完整的栈跟踪
        
        Args:
            logger: 日志记录器
            message: 异常消息
        """
        logger.error(message, exc_info=True, stack_info=True)
    
    def cleanup_old_logs(self, days: int = 7):
        """
        清理旧的日志文件
        
        Args:
            days: 保留天数
        """
        if not self.log_dir:
            return
            
        cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
        
        for log_file in self.log_dir.glob("*.log.*"):
            try:
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    print(f"删除旧日志文件: {log_file}")
            except Exception as e:
                print(f"删除日志文件失败 {log_file}: {e}")


# 全局日志管理器实例
logger_manager = LoggerManager()


def get_logger(name: str = None) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称，如果为None则使用调用者的模块名
        
    Returns:
        logging.Logger: 日志记录器实例
    """
    if name is None:
        # 获取调用者的模块名
        frame = sys._getframe(1)
        name = frame.f_globals.get('__name__', 'unknown')
    
    return logger_manager.get_logger(name)


def log_exception(message: str = "发生异常", logger: Optional[logging.Logger] = None):
    """
    记录异常信息的便捷函数
    
    Args:
        message: 异常消息
        logger: 日志记录器，如果为None则自动获取
    """
    if logger is None:
        # 获取调用者的模块名
        frame = sys._getframe(1)
        caller_name = frame.f_globals.get('__name__', 'unknown')
        logger = get_logger(caller_name)
    
    logger_manager.log_exception(logger, message)


def init_logging(log_dir: str = "logs", 
                max_file_size: int = 100 * 1024 * 1024,
                backup_count: int = 7,
                console_level: str = "INFO",
                file_level: str = "DEBUG"):
    """
    初始化日志系统的便捷函数
    
    Args:
        log_dir: 日志目录
        max_file_size: 单个日志文件最大大小（字节）
        backup_count: 保留的备份文件数量
        console_level: 控制台日志级别
        file_level: 文件日志级别
    """
    logger_manager.initialize(
        log_dir=log_dir,
        max_file_size=max_file_size,
        backup_count=backup_count,
        console_level=console_level,
        file_level=file_level
    )


# 便捷的日志记录函数
def debug(message: str, logger: Optional[logging.Logger] = None):
    """记录DEBUG级别日志"""
    if logger is None:
        frame = sys._getframe(1)
        caller_name = frame.f_globals.get('__name__', 'unknown')
        logger = get_logger(caller_name)
    logger.debug(message)


def info(message: str, logger: Optional[logging.Logger] = None):
    """记录INFO级别日志"""
    if logger is None:
        frame = sys._getframe(1)
        caller_name = frame.f_globals.get('__name__', 'unknown')
        logger = get_logger(caller_name)
    logger.info(message)


def warning(message: str, logger: Optional[logging.Logger] = None):
    """记录WARNING级别日志"""
    if logger is None:
        frame = sys._getframe(1)
        caller_name = frame.f_globals.get('__name__', 'unknown')
        logger = get_logger(caller_name)
    logger.warning(message)


def error(message: str, logger: Optional[logging.Logger] = None):
    """记录ERROR级别日志"""
    if logger is None:
        frame = sys._getframe(1)
        caller_name = frame.f_globals.get('__name__', 'unknown')
        logger = get_logger(caller_name)
    logger.error(message)


def critical(message: str, logger: Optional[logging.Logger] = None):
    """记录CRITICAL级别日志"""
    if logger is None:
        frame = sys._getframe(1)
        caller_name = frame.f_globals.get('__name__', 'unknown')
        logger = get_logger(caller_name)
    logger.critical(message)
