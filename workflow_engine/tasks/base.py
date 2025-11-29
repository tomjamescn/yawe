"""
任务基类

定义所有任务的通用接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class Task(ABC):
    """任务基类"""

    def __init__(self, name: str, config: Dict[str, Any], context: Dict[str, Any], workflow_context: Dict[str, Any] = None):
        """
        初始化任务

        Args:
            name: 任务名称
            config: 任务配置
            context: 共享上下文(包含logger, notifier, ssh, transfer等组件)
            workflow_context: 工作流上下文(前置任务导出的变量)
        """
        self.name = name
        self.config = config
        self.context = context
        self.workflow_context = workflow_context or {}

        # 从上下文获取常用组件
        self.logger = context.get('logger')
        self.notifier = context.get('notifier')
        self.ssh = context.get('ssh')
        self.transfer = context.get('transfer')
        self.global_config = context.get('config')

    @abstractmethod
    def execute(self) -> Tuple[bool, str]:
        """
        执行任务

        Returns:
            (成功标志, 消息/错误信息)
        """
        pass

    def get_param(self, key: str, default: Any = None) -> Any:
        """
        获取任务参数

        Args:
            key: 参数键
            default: 默认值

        Returns:
            参数值
        """
        return self.config.get('params', {}).get(key, default)

    def set_context_data(self, key: str, value: Any):
        """
        设置上下文数据(用于任务间传递数据)

        Args:
            key: 数据键
            value: 数据值
        """
        if 'data' not in self.context:
            self.context['data'] = {}
        self.context['data'][key] = value

    def get_context_data(self, key: str, default: Any = None) -> Any:
        """
        获取上下文数据

        Args:
            key: 数据键
            default: 默认值

        Returns:
            数据值
        """
        return self.context.get('data', {}).get(key, default)

    def export_context(self) -> Dict[str, Any]:
        """
        导出任务执行后的上下文变量（供后续任务使用）

        子类可以重写此方法来导出自定义变量

        Returns:
            导出的变量字典
        """
        return {}
