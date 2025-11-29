"""
日志管理器模块

提供统一的日志记录功能，支持文件和控制台双输出。
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class Logger:
    """日志管理器"""
    
    def __init__(
        self, 
        log_dir: str = "logs", 
        log_name: Optional[str] = None,
        level: str = "INFO"
    ):
        """
        初始化日志管理器
        
        Args:
            log_dir: 日志目录
            log_name: 日志文件名，默认为 sync_predict_时间戳.log
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        if log_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_name = f"sync_predict_{timestamp}.log"
        
        self.log_file = self.log_dir / log_name
        self.level = level.upper()
        
        # 配置logging
        self._setup_logger()
    
    def _setup_logger(self):
        """配置日志记录器"""
        # 创建logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(getattr(logging, self.level))
        
        # 避免重复添加handler
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # 创建formatter
        formatter = logging.Formatter(
            fmt='[%(asctime)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 文件handler
        file_handler = logging.FileHandler(
            self.log_file, 
            encoding='utf-8',
            mode='a'
        )
        file_handler.setLevel(getattr(logging, self.level))
        file_handler.setFormatter(formatter)
        
        # 控制台handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.level))
        console_handler.setFormatter(formatter)
        
        # 添加handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log(self, message: str, level: str = "INFO"):
        """
        记录日志
        
        Args:
            message: 日志消息
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        level = level.upper()
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message)
    
    def debug(self, message: str):
        """记录DEBUG级别日志"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """记录INFO级别日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """记录WARNING级别日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """记录ERROR级别日志"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """记录CRITICAL级别日志"""
        self.logger.critical(message)
    
    def exception(self, message: str):
        """
        记录异常信息，包含堆栈跟踪
        
        Args:
            message: 异常描述信息
        """
        self.logger.exception(message)
    
    def get_log_file(self) -> Path:
        """
        获取日志文件路径
        
        Returns:
            日志文件的Path对象
        """
        return self.log_file
    
    def set_level(self, level: str):
        """
        动态设置日志级别
        
        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        level = level.upper()
        self.level = level
        self.logger.setLevel(getattr(logging, level))
        for handler in self.logger.handlers:
            handler.setLevel(getattr(logging, level))


# 使用示例
if __name__ == "__main__":
    # 基础使用
    logger = Logger()
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    logger.debug("这是一条调试日志（默认不显示）")
    
    # 自定义配置
    logger2 = Logger(
        log_dir="custom_logs",
        log_name="test.log",
        level="DEBUG"
    )
    logger2.debug("现在可以看到调试信息了")
    logger2.info(f"日志文件位置: {logger2.get_log_file()}")
    
    # 动态修改日志级别
    logger2.set_level("WARNING")
    logger2.info("这条信息不会显示")
    logger2.warning("但这条警告会显示")
    
    # 记录异常
    try:
        1 / 0
    except Exception:
        logger.exception("捕获到异常")