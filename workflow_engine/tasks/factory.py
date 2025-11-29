"""
任务工厂

根据任务类型创建任务实例
"""

from typing import Dict, Type, Any
from .base import Task


class TaskFactory:
    """任务工厂,根据类型创建任务实例"""

    _task_registry: Dict[str, Type[Task]] = {}

    @classmethod
    def register(cls, task_type: str, task_class: Type[Task]):
        """
        注册任务类型

        Args:
            task_type: 任务类型标识
            task_class: 任务类
        """
        cls._task_registry[task_type] = task_class

    @classmethod
    def create(cls, task_type: str, name: str, config: Dict[str, Any], context: Dict[str, Any], workflow_context: Dict[str, Any] = None) -> Task:
        """
        创建任务实例

        Args:
            task_type: 任务类型标识
            name: 任务名称
            config: 任务配置
            context: 共享上下文
            workflow_context: 工作流上下文（前置任务导出的变量）

        Returns:
            任务实例

        Raises:
            ValueError: 未知的任务类型
        """
        if task_type not in cls._task_registry:
            raise ValueError(f"未知的任务类型: {task_type}")

        task_class = cls._task_registry[task_type]
        return task_class(name, config, context, workflow_context)

    @classmethod
    def list_types(cls) -> list:
        """
        列出所有已注册的任务类型

        Returns:
            任务类型列表
        """
        return list(cls._task_registry.keys())
