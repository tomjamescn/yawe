"""
YAWE (Yet Another Workflow Engine) 命令行接口

提供 workflow-run 命令用于执行工作流配置文件
"""

import sys
import argparse
from pathlib import Path

from workflow_engine import Config, Logger, WorkflowEngine, WorkflowStateManager


def main():
    """
    workflow-run 命令行入口函数

    使用方法:
        workflow-run [--config CONFIG_FILE]
        workflow-run -r  # 从断点恢复
        workflow-run --from-task "任务名"  # 从指定任务开始
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='YAWE 工作流引擎 - 执行配置驱动的工作流任务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  workflow-run --config workflow.yaml          执行指定配置文件
  workflow-run -r                              从上次失败的任务恢复
  workflow-run --from-task "数据处理"          从指定任务开始执行
  workflow-run --clean-state                   清理旧的状态文件
        """
    )

    parser.add_argument(
        '--config',
        default='config.yaml',
        help='工作流配置文件路径 (默认: config.yaml)'
    )
    parser.add_argument(
        '-r', '--resume',
        action='store_true',
        help='从上次失败的任务恢复执行'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='强制恢复(忽略配置变更检查)'
    )
    parser.add_argument(
        '--clean-state',
        action='store_true',
        help='清理旧的状态文件(默认保留30天)'
    )
    parser.add_argument(
        '--from-task',
        metavar='TASK_NAME',
        help='从指定任务名称开始执行(跳过之前的任务)'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )

    args = parser.parse_args()

    # 检查配置文件是否存在
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"错误: 配置文件不存在: {args.config}")
        print(f"请创建配置文件或使用 --config 参数指定正确的配置文件路径")
        sys.exit(1)

    # 初始化配置和日志
    try:
        config = Config(str(config_path))

        # 如果命令行指定了日志级别，覆盖配置文件设置
        log_level = args.log_level if hasattr(args, 'log_level') else config.get('log_level', 'INFO')

        logger = Logger(
            log_dir=config.get('log_dir', 'logs'),
            log_name=config.get('log_name', 'workflow'),
            level=log_level
        )
    except Exception as e:
        print(f"初始化配置或日志失败: {str(e)}")
        sys.exit(1)

    logger.info(f"从配置文件加载工作流: {args.config}")

    # 处理状态清理
    if args.clean_state:
        state_manager = WorkflowStateManager(config, logger)
        logger.info("清理旧状态文件...")
        removed = state_manager.cleanup_old_states(older_than_days=30)
        logger.info(f"清理了 {removed} 个旧状态文件")
        sys.exit(0)

    # 初始化状态管理器
    state_manager = WorkflowStateManager(config, logger)

    # 获取文件锁
    if not state_manager.acquire_lock():
        logger.error("检测到另一个工作流正在运行,无法启动")
        logger.error(f"如果确认没有其他实例运行,请删除锁文件: {config.get('log_dir', 'logs')}/.workflow_state/.lock")
        sys.exit(1)

    # 恢复模式
    resume_state = None
    if args.resume:
        resume_state = state_manager.load_latest_failed_state()
        if not resume_state:
            logger.error("未找到可恢复的状态文件")
            logger.error("")
            logger.error("可能原因:")
            logger.error("1. 上次运行成功完成(无失败任务)")
            logger.error("2. 状态文件已被清理")
            logger.error("3. 这是第一次运行")
            logger.error("")
            logger.error("解决方案:")
            logger.error(f"直接运行工作流: workflow-run --config {args.config}")
            state_manager.release_lock()
            sys.exit(1)

        # 验证状态
        valid, message = state_manager.validate_state(resume_state, args.force)
        if not valid:
            logger.error(f"状态验证失败:")
            logger.error(message)
            state_manager.release_lock()
            sys.exit(1)

    # 创建共享上下文
    context = {
        'config': config,
        'logger': logger,
        'data': {}  # 用于任务间传递数据
    }

    # 获取工作流配置
    workflow_config = config.get('workflow', {})
    if not workflow_config:
        logger.error("配置文件中未找到 'workflow' 配置节")
        logger.error("请确保配置文件包含工作流定义")
        state_manager.release_lock()
        sys.exit(1)

    # 创建并运行工作流引擎
    try:
        workflow_engine = WorkflowEngine(
            workflow_config,
            context,
            state_manager=state_manager,
            resume_state=resume_state,
            from_task=args.from_task
        )

        logger.info("开始执行工作流")
        exit_code = workflow_engine.run()

        # 释放文件锁
        state_manager.release_lock()

        if exit_code == 0:
            logger.info("工作流执行成功完成")
        else:
            logger.error(f"工作流执行失败 (失败任务数: {exit_code})")

        sys.exit(exit_code)

    except KeyboardInterrupt:
        logger.warning("用户中断执行")
        state_manager.release_lock()
        sys.exit(130)
    except Exception as e:
        logger.error(f"执行过程中出现异常: {str(e)}")
        logger.exception("详细异常信息")
        state_manager.release_lock()
        sys.exit(1)


if __name__ == "__main__":
    main()
