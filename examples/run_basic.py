#!/usr/bin/env python3
"""
基础工作流执行示例

运行方法:
    python examples/run_basic.py
"""

import sys
import os

# 添加父目录到路径以便导入 workflow_engine
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow_engine import Config, Logger, WorkflowEngine


def main():
    """主函数"""
    # 加载配置文件
    config_file = os.path.join(os.path.dirname(__file__), "basic_workflow.yaml")
    config = Config(config_file)

    # 初始化日志
    logger = Logger(
        log_dir=config.log_dir,
        level=config.log_level
    )

    logger.info("=" * 60)
    logger.info("YAWE (Yet Another Workflow Engine) - 基础示例")
    logger.info("=" * 60)

    # 创建共享上下文
    context = {
        'logger': logger,
        'config': config
    }

    # 获取工作流配置
    workflow_config = config.get('workflow', {})

    # 创建工作流引擎
    engine = WorkflowEngine(workflow_config, context)

    # 执行工作流
    exit_code = engine.run()

    # 输出结果
    logger.info("=" * 60)
    if exit_code == 0:
        logger.info("工作流执行成功!")
    else:
        logger.error(f"工作流执行失败，失败任务数: {exit_code}")
    logger.info("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
