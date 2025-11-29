"""
工作流引擎

负责按照配置编排和执行任务
"""

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from workflow_engine.tasks.factory import TaskFactory


class WorkflowEngine:
    """工作流执行引擎"""

    def __init__(self, workflow_config: Dict[str, Any], context: Dict[str, Any],
                 state_manager: Optional['WorkflowStateManager'] = None,
                 resume_state: Optional[Dict[str, Any]] = None,
                 from_task: Optional[str] = None):
        """
        初始化工作流引擎

        Args:
            workflow_config: 工作流配置
            context: 共享上下文
            state_manager: 状态管理器(可选)
            resume_state: 恢复状态(可选)
            from_task: 从指定任务名称开始执行(可选)
        """
        self.workflow_config = workflow_config
        self.context = context
        self.logger = context['logger']
        self.notifier = context.get('notifier')

        # 状态管理
        self.state_manager = state_manager
        self.resume_state = resume_state
        self.current_state = None
        self.run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.from_task = from_task

        # 工作流上下文：存储任务间传递的变量
        self.workflow_context: Dict[str, Any] = {}

        # 执行统计
        self.executed_tasks: List[str] = []
        self.failed_tasks: List[Tuple[str, str]] = []
        self.skipped_tasks: List[str] = []

    def run(self) -> int:
        """
        执行工作流

        Returns:
            退出码(0表示成功,非0表示失败任务数)
        """
        tasks_config = self.workflow_config.get('tasks', [])
        settings = self.workflow_config.get('settings', {})
        stop_on_error = settings.get('stop_on_first_error', True)

        if not tasks_config:
            self.logger.warning("工作流配置为空,没有任务需要执行")
            return 0

        # 检查任务名称唯一性
        task_names = set()
        for idx, task_config in enumerate(tasks_config, 1):
            name = task_config.get('name', f'task_{idx}')
            if name in task_names:
                self.logger.error(f"任务名称重复: {name}")
                self.logger.error("请为每个任务配置唯一的名称，以便在日志和通知中区分")
                return 1
            task_names.add(name)

        # 创建或恢复状态
        resume_from_index = 0
        if self.resume_state:
            self.logger.info("恢复模式: 从上次失败处继续执行")
            self.current_state = self.resume_state
            self._restore_context_from_state()
            resume_from_index = self._find_resume_point()
            self._log_resume_info()
        elif self.from_task:
            # 从指定任务开始执行
            resume_from_index = self._find_task_index(self.from_task, tasks_config)
            if resume_from_index == -1:
                self.logger.error(f"未找到任务: {self.from_task}")
                self.logger.error("可用的任务名称:")
                for idx, task_config in enumerate(tasks_config, 1):
                    name = task_config.get('name', f'task_{idx}')
                    self.logger.error(f"  {idx}. {name}")
                return 1
            self.logger.info(f"指定任务模式: 从任务 '{self.from_task}' 开始执行")
            self.logger.warning("注意: 跳过的任务不会提供导出变量,如果后续任务依赖这些变量将会失败")
            self.logger.warning(f"跳过的任务: {', '.join([tc.get('name', f'task_{i}') for i, tc in enumerate(tasks_config[:resume_from_index-1], 1)])}")
            if self.state_manager:
                self.current_state = self.state_manager.create_state(
                    self.workflow_config, self.run_id
                )
                self.state_manager.save_state(self.current_state)
        else:
            self.logger.info("正常模式: 开始新的工作流执行")
            if self.state_manager:
                self.current_state = self.state_manager.create_state(
                    self.workflow_config, self.run_id
                )
                self.state_manager.save_state(self.current_state)

        self.logger.info(f"开始执行工作流,共 {len(tasks_config)} 个任务")

        # 遍历任务配置
        for idx, task_config in enumerate(tasks_config, 1):
            name = task_config.get('name', f'task_{idx}')
            task_type = task_config.get('type')
            enabled = task_config.get('enabled', True)

            # 恢复模式或指定任务模式: 跳过之前的任务
            if (self.resume_state or self.from_task) and idx < resume_from_index:
                skip_reason = "恢复模式跳过" if self.resume_state else "指定任务跳过"
                self.logger.info(f"[{idx}/{len(tasks_config)}] 任务跳过({skip_reason}): {name}")
                self.skipped_tasks.append(name)
                continue

            # 跳过禁用的任务
            if not enabled:
                self.logger.info(f"[{idx}/{len(tasks_config)}] 任务已禁用,跳过: {name}")
                self.skipped_tasks.append(name)
                continue

            if not task_type:
                self.logger.error(f"[{idx}/{len(tasks_config)}] 任务配置错误: {name} - 缺少type字段")
                self.failed_tasks.append((name, "缺少type字段"))
                if stop_on_error:
                    break
                continue

            # 标记任务开始(恢复模式或指定任务模式下显示特殊提示)
            if (self.resume_state or self.from_task) and idx == resume_from_index:
                start_reason = "恢复" if self.resume_state else "指定任务"
                self.logger.info(f"[{idx}/{len(tasks_config)}] 开始执行任务({start_reason}): {name} (类型: {task_type})")
            else:
                self.logger.info(f"[{idx}/{len(tasks_config)}] 开始执行任务: {name} (类型: {task_type})")

            # 更新任务状态为running
            if self.state_manager and self.current_state:
                self._update_task_state(idx - 1, 'running', '', {})
                self.state_manager.save_state(self.current_state)

            try:
                # 创建并执行任务（传递 workflow_context）
                task = TaskFactory.create(task_type, name, task_config, self.context, self.workflow_context)
                success, message = task.execute()

                self.executed_tasks.append(name)

                if success:
                    self.logger.info(f"[{idx}/{len(tasks_config)}] 任务成功: {name} - {message}")

                    # 任务成功后，收集导出的变量
                    exported_vars = {}
                    try:
                        exported_vars = task.export_context()
                        if exported_vars:
                            # 使用任务名作为命名空间，创建嵌套字典结构
                            # 这样 Jinja2 可以通过 {{ task_name.var_name }} 访问
                            if name not in self.workflow_context:
                                self.workflow_context[name] = {}

                            for key, value in exported_vars.items():
                                self.workflow_context[name][key] = value
                                self.logger.debug(f"导出变量: {name}.{key} = {value}")

                            self.logger.info(f"任务 {name} 导出了 {len(exported_vars)} 个变量")
                    except Exception as e:
                        self.logger.warning(f"收集任务导出变量时出错: {str(e)}")

                    # 更新任务状态为success
                    if self.state_manager and self.current_state:
                        self._update_task_state(idx - 1, 'success', message, exported_vars)
                        # 更新workflow_context到状态文件
                        self.current_state['workflow_context'] = self.workflow_context
                        self.state_manager.save_state(self.current_state)

                    # 发送成功通知
                    if task_config.get('notify_on_success', False) and self.notifier:
                        self._send_notification(task_config, 'success', name, message)
                else:
                    self.logger.error(f"[{idx}/{len(tasks_config)}] 任务失败: {name} - {message}")
                    self.failed_tasks.append((name, message))

                    # 更新任务状态为failed
                    if self.state_manager and self.current_state:
                        self._update_task_state(idx - 1, 'failed', message, {})
                        self.state_manager.save_state(self.current_state)

                    # 发送失败通知
                    if task_config.get('notify_on_failure', False) and self.notifier:
                        self._send_notification(task_config, 'failure', name, message)

                    # 检查是否需要中断流程
                    fail_on_error = task_config.get('fail_on_error', True)
                    if fail_on_error and stop_on_error:
                        self.logger.error("任务失败导致工作流中断")
                        break

            except Exception as e:
                self.logger.exception(f"[{idx}/{len(tasks_config)}] 任务执行异常: {name}")
                error_msg = str(e)
                self.failed_tasks.append((name, error_msg))

                # 更新任务状态为failed
                if self.state_manager and self.current_state:
                    self._update_task_state(idx - 1, 'failed', error_msg, {})
                    self.state_manager.save_state(self.current_state)

                # 发送失败通知
                if task_config.get('notify_on_failure', False) and self.notifier:
                    self._send_notification(task_config, 'failure', name, error_msg)

                # 检查是否需要中断流程
                fail_on_error = task_config.get('fail_on_error', True)
                if fail_on_error and stop_on_error:
                    self.logger.error("任务异常导致工作流中断")
                    break

        # 更新最终工作流状态
        if self.state_manager and self.current_state:
            final_status = 'success' if len(self.failed_tasks) == 0 else 'failed'
            self.current_state['metadata']['workflow_status'] = final_status
            self.state_manager.save_state(self.current_state)

        # 工作流完成统计
        self._log_summary()

        # 返回失败任务数
        return len(self.failed_tasks)

    def _send_notification(self, task_config: Dict[str, Any], notify_type: str, task_name: str, message: str):
        """
        发送任务通知

        Args:
            task_config: 任务配置
            notify_type: 通知类型 (success/failure)
            task_name: 任务名称
            message: 消息内容
        """
        try:
            # 获取通知配置
            notification_config = task_config.get('notification', {})
            type_config = notification_config.get(notify_type, {})

            # 获取通知内容（支持模板变量）
            title = type_config.get('title', f"任务{notify_type}: {task_name}")
            notify_message = type_config.get('message', message)

            # 简单的模板变量替换
            notify_message = notify_message.replace('{{ task_name }}', task_name)
            notify_message = notify_message.replace('{{ message }}', message)
            notify_message = notify_message.replace('{{ error_message }}', message)

            # 发送通知
            if notify_type == 'success':
                self.notifier.send_success(title, notify_message)
            else:
                self.notifier.send_failure(title, notify_message)

            self.logger.info(f"已发送{notify_type}通知: {title}")

        except Exception as e:
            self.logger.error(f"发送通知异常: {str(e)}")

    def _log_summary(self):
        """记录工作流执行摘要"""
        total = len(self.executed_tasks) + len(self.skipped_tasks)
        executed = len(self.executed_tasks)
        failed = len(self.failed_tasks)
        skipped = len(self.skipped_tasks)
        succeeded = executed - failed

        self.logger.info("=" * 60)
        self.logger.info("工作流执行完成")
        self.logger.info(f"总任务数: {total}")
        self.logger.info(f"已执行: {executed}")
        self.logger.info(f"成功: {succeeded}")
        self.logger.info(f"失败: {failed}")
        self.logger.info(f"跳过: {skipped}")

        if self.failed_tasks:
            self.logger.error("失败任务详情:")
            for task_name, error_msg in self.failed_tasks:
                self.logger.error(f"  - {task_name}: {error_msg}")

        self.logger.info("=" * 60)

    def _restore_context_from_state(self):
        """从状态恢复 workflow_context"""
        if 'workflow_context' in self.current_state:
            self.workflow_context = self.current_state['workflow_context']
            self.logger.info(f"已恢复 {len(self.workflow_context)} 个任务的上下文变量")

    def _find_resume_point(self) -> int:
        """
        找到恢复点(第一个失败或运行中的任务索引)

        Returns:
            任务索引(1-based)
        """
        for idx, task_state in enumerate(self.current_state['tasks']):
            if task_state['status'] in ('failed', 'running', 'pending'):
                self.logger.info(f"恢复点: 任务 {idx+1} - {task_state['name']}")
                return idx + 1
        # 如果所有任务都成功,从头开始
        return 1

    def _update_task_state(self, task_index: int, status: str,
                          message: str, exported_vars: Dict[str, Any]):
        """
        更新任务状态

        Args:
            task_index: 任务索引(0-based)
            status: 任务状态
            message: 消息
            exported_vars: 导出的变量
        """
        if task_index >= len(self.current_state['tasks']):
            self.logger.warning(f"任务索引越界: {task_index}")
            return

        task_state = self.current_state['tasks'][task_index]
        task_state['status'] = status
        task_state['message'] = message

        if status == 'running':
            task_state['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            task_state['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if exported_vars:
            task_state['exported_context'] = exported_vars

        # 更新metadata
        self.current_state['metadata']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _log_resume_info(self):
        """记录恢复信息"""
        metadata = self.current_state['metadata']
        completed = sum(1 for t in self.current_state['tasks'] if t['status'] == 'success')
        failed_task = next((t for t in self.current_state['tasks']
                           if t['status'] in ('failed', 'running')), None)

        self.logger.info(f"加载状态文件: workflow_state_{metadata['config_hash']}_{metadata['run_id']}.json")
        self.logger.info(f"原始运行时间: {metadata['start_time']}")
        self.logger.info(f"已完成任务: {completed} 个")
        if failed_task:
            self.logger.info(f"失败任务: {failed_task['name']}")

    def _find_task_index(self, task_name: str, tasks_config: List[Dict[str, Any]]) -> int:
        """
        查找任务在配置列表中的索引

        Args:
            task_name: 任务名称
            tasks_config: 任务配置列表

        Returns:
            任务索引(1-based),未找到返回-1
        """
        for idx, task_config in enumerate(tasks_config, 1):
            name = task_config.get('name', f'task_{idx}')
            if name == task_name:
                return idx
        return -1
