"""
配置管理模块

从YAML文件加载配置信息
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """配置管理器"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise Exception(f"加载配置文件失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（支持点号分隔的嵌套键）

        Args:
            key: 配置键，支持点号分隔（如 "ssh.host"）
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置节

        Args:
            section: 配置节名称

        Returns:
            配置节字典
        """
        return self._config.get(section, {})

    def get_all(self) -> Dict[str, Any]:
        """
        获取所有配置

        Returns:
            完整配置字典
        """
        return self._config.copy()

    # 快捷访问方法（仅保留实际使用的配置）

    @property
    def notifier_api_url(self) -> str:
        """获取通知API URL"""
        return self.get('notifier.api_url', '')

    @property
    def notifier_timeout(self) -> int:
        """获取通知超时时间"""
        return self.get('notifier.timeout', 10)

    @property
    def notifier_verify_ssl(self) -> bool:
        """获取是否验证SSL"""
        return self.get('notifier.verify_ssl', False)

    @property
    def log_dir(self) -> str:
        """获取日志目录"""
        return self.get('logger.log_dir', 'logs')

    @property
    def log_name(self) -> Optional[str]:
        """获取日志文件名"""
        return self.get('logger.log_name')

    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self.get('logger.level', 'INFO')

    @property
    def command_timeout(self) -> int:
        """获取命令执行默认超时时间"""
        return self.get('tasks.command_timeout', 3600)

    @property
    def transfer_timeout(self) -> int:
        """获取文件传输默认超时时间"""
        return self.get('tasks.transfer.timeout', 600)

    @property
    def transfer_show_progress(self) -> bool:
        """获取是否显示传输进度"""
        return self.get('tasks.transfer.show_progress', True)

    @property
    def transfer_compress(self) -> bool:
        """获取是否压缩传输"""
        return self.get('tasks.transfer.compress', True)

    @property
    def transfer_preserve_times(self) -> bool:
        """获取是否保留时间戳"""
        return self.get('tasks.transfer.preserve_times', True)

    @property
    def transfer_remote_temp_dir(self) -> str:
        """获取远程临时目录"""
        return self.get('tasks.transfer.remote_temp_dir', '/tmp')

    @property
    def transfer_local_temp_dir(self) -> str:
        """获取本地临时目录"""
        return self.get('tasks.transfer.local_temp_dir', '/tmp')

    @property
    def local_shell(self) -> str:
        """获取本地命令默认使用的shell"""
        return self.get('tasks.local_shell', '/bin/sh')

    @property
    def transfer_decompress(self) -> bool:
        """获取预压缩传输后是否解压（默认True）"""
        return self.get('tasks.transfer.decompress', True)

    @property
    def cleanup_on_startup(self) -> bool:
        """获取是否在启动时清理旧临时文件（默认True）"""
        return self.get('tasks.transfer.cleanup_on_startup', True)

    @property
    def temp_file_max_age(self) -> int:
        """获取临时文件最大保留时间/秒（默认86400=24小时）"""
        return self.get('tasks.transfer.temp_file_max_age', 86400)

    @property
    def cleanup_on_exit(self) -> bool:
        """获取是否在退出时清理当前会话临时文件（默认True）"""
        return self.get('tasks.transfer.cleanup_on_exit', True)


# 使用示例
if __name__ == "__main__":
    # 加载配置
    config = Config("config.yaml")

    # 访问配置
    print(f"日志目录: {config.log_dir}")
    print(f"日志级别: {config.log_level}")
    print(f"通知API: {config.notifier_api_url}")
    print(f"命令超时: {config.command_timeout}秒")
    print(f"传输超时: {config.transfer_timeout}秒")

    # 使用点号访问
    print(f"\n工作流配置:")
    workflow = config.get('workflow', {})
    tasks = workflow.get('tasks', [])
    print(f"  任务数量: {len(tasks)}")
    for task in tasks:
        print(f"  - {task.get('name')} ({task.get('type')})")
