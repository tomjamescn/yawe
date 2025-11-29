"""
通知任务
"""

from typing import Tuple
from .base import Task


class NotificationTask(Task):
    """通知任务"""

    def execute(self) -> Tuple[bool, str]:
        """
        发送通知

        Returns:
            (成功标志, 消息)
        """
        self.logger.info(f"执行任务: {self.name} - 发送通知")

        # 获取通知参数
        task_name = self.get_param('task_name', self.name)
        message = self.get_param('message', '')
        notification_type = self.get_param('notification_type', 'success')
        details = self.get_param('details', message)
        error_msg = self.get_param('error_msg', message)
        warning_msg = self.get_param('warning_msg', message)

        try:
            # 根据通知类型发送不同的通知
            if notification_type == 'success':
                self.notifier.send_success(
                    task_name=task_name,
                    details=details
                )
            elif notification_type == 'failure':
                self.notifier.send_failure(
                    task_name=task_name,
                    error_msg=error_msg
                )
            elif notification_type == 'warning':
                self.notifier.send_warning(
                    task_name=task_name,
                    warning_msg=warning_msg
                )
            else:
                return False, f"未知的通知类型: {notification_type}"

            self.logger.info(f"通知发送成功: {task_name} ({notification_type})")
            return True, f"通知发送成功 ({notification_type})"

        except Exception as e:
            error_msg = f"通知发送失败: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
