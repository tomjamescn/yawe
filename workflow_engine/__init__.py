"""
Workflow Engine - 配置驱动的通用任务编排框架

一个轻量级、灵活、配置驱动的工作流引擎，用于自动化任务编排和执行。

核心特性:
- 完全配置驱动，零代码定义工作流
- 断点续传，任务级恢复
- SSH远程执行和文件传输
- 灵活的错误处理和通知机制
- 任务间变量传递和模板渲染
- 并发防护和状态管理

基本用法:
    from workflow_engine import WorkflowEngine, Config, Logger

    # 加载配置
    config = Config("config.yaml")
    logger = Logger(log_dir="logs")

    # 创建上下文
    context = {
        'logger': logger,
        'config': config
    }

    # 运行工作流
    engine = WorkflowEngine(config.workflow, context)
    exit_code = engine.run()
"""

__version__ = "1.0.0"
__author__ = "Tom James"

from workflow_engine.core.config import Config
from workflow_engine.core.logger import Logger
from workflow_engine.core.workflow import WorkflowEngine
from workflow_engine.core.state_manager import WorkflowStateManager
from workflow_engine.tasks.base import Task
from workflow_engine.tasks.factory import TaskFactory
from workflow_engine.utils.executor import SSHExecutor
from workflow_engine.utils.transfer import FileTransfer
from workflow_engine.utils.notifier import Notifier

__all__ = [
    'Config',
    'Logger',
    'WorkflowEngine',
    'WorkflowStateManager',
    'Task',
    'TaskFactory',
    'SSHExecutor',
    'FileTransfer',
    'Notifier',
]
