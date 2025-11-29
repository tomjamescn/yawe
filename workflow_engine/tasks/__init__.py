"""
任务模块 - 自动注册所有任务类型
"""

from workflow_engine.tasks.factory import TaskFactory
from workflow_engine.tasks.base import Task
from workflow_engine.tasks.command_task import CommandTask
from workflow_engine.tasks.file_copy_task import FileCopyTask

# 注册内置任务类型
TaskFactory.register('command', CommandTask)
TaskFactory.register('transfer', FileCopyTask)

__all__ = [
    'TaskFactory',
    'Task',
    'CommandTask',
    'FileCopyTask',
]
