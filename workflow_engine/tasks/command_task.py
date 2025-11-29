"""
通用命令任务

支持SSH远程命令和本地命令执行，完全由配置驱动
"""

import re
from typing import Tuple, List, Dict, Any
from jinja2 import Template, TemplateError
from .base import Task


class CommandTask(Task):
    """通用命令执行任务，支持SSH和本地命令"""

    # 默认错误关键词
    DEFAULT_ERROR_KEYWORDS = [
        "Error:",
        "ERROR:",
        "Exception:",
        "Traceback",
        "FAILED",
        "错误:",
        "异常:",
        "失败",
    ]

    def execute(self) -> Tuple[bool, str]:
        """
        执行命令

        Returns:
            (成功标志, 消息)
        """
        self.logger.info(f"执行任务: {self.name}")

        # 获取执行器类型
        executor = self.config.get('executor', 'ssh')

        if executor == 'ssh':
            return self._execute_ssh_command()
        elif executor == 'local':
            return self._execute_local_command()
        else:
            return False, f"未知的执行器类型: {executor}"

    def _execute_ssh_command(self) -> Tuple[bool, str]:
        """执行SSH远程命令"""

        # 获取host（必填）
        host = self.config.get('host')
        if not host:
            return False, "SSH命令必须指定 host 参数"

        # 检查是否需要创建或切换host
        if not self.ssh or self.ssh.host != host:
            self.logger.info(f"创建/切换SSH连接到: {host}")
            # 创建或重新初始化SSH执行器
            from workflow_engine.utils.executor import SSHExecutor
            self.ssh = SSHExecutor(
                host=host,
                logger=self.logger
            )
            self.context['ssh'] = self.ssh

        # 渲染命令
        command = self._render_command()
        if not command:
            return False, "命令渲染失败或为空"

        self.logger.info(f"执行SSH命令:\n{command}")

        # 获取超时时间
        timeout = self.get_param('timeout')
        if not timeout:
            timeout = self.global_config.command_timeout

        # 检查是否配置了重试
        retry_config = self.config.get('retry')
        if retry_config:
            # 使用带重试的执行方法
            max_retries = retry_config.get('max_retries', 3)
            retry_interval = retry_config.get('retry_interval', 300)

            self.logger.info(f"启用重试机制: 最大重试{max_retries}次，间隔{retry_interval}秒")

            success = self.ssh.execute_with_retry(
                command=command,
                task_name=self.name,
                max_retries=max_retries,
                retry_interval=retry_interval,
                send_success_notify=False,  # 任务级别的通知由workflow处理
                notifier=self.notifier,
                timeout=timeout
            )

            if success:
                return True, "命令执行成功（可能经过重试）"
            else:
                return False, f"命令执行失败（已重试{max_retries}次）"
        else:
            # 使用单次执行方法
            success, output, exit_code = self.ssh.execute_command(
                command,
                timeout=timeout
            )

            # 判断命令是否成功
            return self._check_command_result(success, output, exit_code)

    def _execute_local_command(self) -> Tuple[bool, str]:
        """执行本地命令"""

        # 渲染命令
        command = self._render_command()
        if not command:
            return False, "命令渲染失败或为空"

        self.logger.info(f"执行本地命令:\n{command}")

        import subprocess

        try:
            # 获取超时时间
            timeout = self.get_param('timeout')
            if not timeout:
                timeout = self.global_config.command_timeout

            # 获取shell配置（任务级 > 全局级）
            shell = self.config.get('shell')
            if shell is None:
                shell = self.global_config.local_shell

            self.logger.info(f"使用shell: {shell}")

            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                executable=shell,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = result.stdout + result.stderr
            exit_code = result.returncode

            # 记录输出
            if output:
                self.logger.info(f"命令输出:\n{output}")

            # 判断命令是否成功
            return self._check_command_result(True, output, exit_code)

        except subprocess.TimeoutExpired:
            return False, f"命令执行超时 ({timeout}秒)"
        except Exception as e:
            self.logger.exception("本地命令执行异常")
            return False, f"命令执行异常: {str(e)}"

    def _render_command(self) -> str:
        """
        渲染命令模板

        Returns:
            渲染后的命令字符串
        """
        # 优先使用 command_template，其次使用 command
        command_template = self.config.get('command_template')
        if not command_template:
            command_template = self.config.get('command', '')

        if not command_template:
            self.logger.error("未配置 command 或 command_template")
            return ""

        # 获取模板参数
        # 支持两种格式: params 字典 或 直接在 config 中的参数
        params = self.config.get('params', {})

        # 合并 workflow_context（前置任务导出的变量）
        # workflow_context 中的变量可以直接在模板中访问
        render_vars = {}
        if self.workflow_context:
            render_vars.update(self.workflow_context)
        if params:
            render_vars.update(params)  # params 优先级更高

        # 如果没有模板变量，直接返回
        if not render_vars and '{{' not in command_template and '{%' not in command_template:
            return command_template

        # 使用 Jinja2 渲染模板
        try:
            from jinja2 import StrictUndefined
            template = Template(command_template, undefined=StrictUndefined)
            rendered = template.render(**render_vars)
            return rendered.strip()
        except TemplateError as e:
            self.logger.error(f"命令模板渲染失败: {str(e)}")
            self.logger.error(f"可用变量: {list(render_vars.keys())}")
            return ""
        except Exception as e:
            self.logger.exception("命令模板渲染异常")
            return ""

    def _check_command_result(self, success: bool, output: str, exit_code: int) -> Tuple[bool, str]:
        """
        检查命令执行结果

        Args:
            success: SSH执行器返回的成功标志
            output: 命令输出
            exit_code: 退出码

        Returns:
            (成功标志, 消息)
        """
        # 如果SSH执行本身失败，直接返回
        if not success:
            return False, f"命令执行失败，退出码: {exit_code}"

        # 1. 检查退出码
        if self.config.get('check_exit_code', True):
            if exit_code != 0:
                return False, f"命令退出码异常: {exit_code}"

        # 2. 检查错误关键词
        if self.config.get('check_error_keywords', True):
            error_keywords = self.config.get('error_keywords', self.DEFAULT_ERROR_KEYWORDS)
            for keyword in error_keywords:
                if keyword in output:
                    return False, f"输出中发现错误关键词: {keyword}"

        # 3. 检查成功关键词
        if self.config.get('check_success_keywords', False):
            success_keywords = self.config.get('success_keywords', [])
            if success_keywords:
                found = any(kw in output for kw in success_keywords)
                if not found:
                    return False, f"输出中未找到成功关键词: {success_keywords}"

        # 4. 检查输出文件（SSH远程文件）
        if self.config.get('check_output_files', False):
            check_result = self._check_output_files()
            if not check_result[0]:
                return check_result

        return True, "命令执行成功"

    def _check_output_files(self) -> Tuple[bool, str]:
        """
        检查输出文件是否存在

        Returns:
            (成功标志, 消息)
        """
        expected_files = self.config.get('expected_files', [])
        if not expected_files:
            return True, "无需检查输出文件"

        executor = self.config.get('executor', 'ssh')

        for file_config in expected_files:
            file_path = file_config.get('path')
            must_exist = file_config.get('must_exist', True)
            min_size = file_config.get('min_size', 0)

            if not file_path:
                continue

            # 检查文件是否存在
            if executor == 'ssh':
                check_cmd = f"test -f {file_path} && echo 'EXISTS' || echo 'NOT_EXISTS'"
                success, output, _ = self.ssh.execute_command(check_cmd, timeout=10)
                file_exists = success and 'EXISTS' in output
            else:
                import os
                file_exists = os.path.isfile(file_path)

            if must_exist and not file_exists:
                return False, f"输出文件不存在: {file_path}"

            # 检查文件大小
            if file_exists and min_size > 0:
                if executor == 'ssh':
                    size_cmd = f"stat -c %s {file_path}"
                    success, output, _ = self.ssh.execute_command(size_cmd, timeout=10)
                    if success:
                        try:
                            file_size = int(output.strip())
                            if file_size < min_size:
                                return False, f"输出文件大小不足: {file_path} (期望>={min_size}, 实际={file_size})"
                        except ValueError:
                            self.logger.warning(f"无法获取文件大小: {file_path}")
                else:
                    import os
                    file_size = os.path.getsize(file_path)
                    if file_size < min_size:
                        return False, f"输出文件大小不足: {file_path} (期望>={min_size}, 实际={file_size})"

        return True, "输出文件检查通过"


# 测试代码
if __name__ == "__main__":
    # 简单测试模板渲染
    from jinja2 import Template

    template_str = """
    cd {{ workspace }}
    {% for id in run_ids %}
    python train.py --id {{ id }}
    {% endfor %}
    """

    params = {
        'workspace': '/home/user/project',
        'run_ids': [1, 2, 3]
    }

    template = Template(template_str)
    result = template.render(**params)
    print("模板渲染结果:")
    print(result)
