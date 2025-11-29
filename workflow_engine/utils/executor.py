"""
SSH执行器模块

执行远程SSH命令，支持自动重试和错误检测。
"""

import subprocess
import time
from typing import Optional, Tuple, List

try:
    from logger import Logger
    from notifier import Notifier
except ImportError:
    Logger = None
    Notifier = None


class SSHExecutor:
    """SSH命令执行器"""

    def __init__(
        self,
        host: str,
        logger: Optional['Logger'] = None
    ):
        """
        初始化SSH执行器

        Args:
            host: SSH配置中的主机名(在~/.ssh/config中配置)
            logger: 日志记录器实例

        注意:
            SSH连接参数(user, port, IdentityFile等)应该在~/.ssh/config中预先配置
            例如:
                Host ms197
                    HostName 192.168.1.100
                    User tangwei
                    Port 22
                    IdentityFile ~/.ssh/id_rsa
        """
        self.host = host
        self.logger = logger
    
    def check_connection(self, timeout: int = 10) -> bool:
        """
        检查SSH连接是否正常

        Args:
            timeout: 连接超时时间（秒）

        Returns:
            连接是否正常
        """
        if self.logger:
            self.logger.info("检查SSH连接...")

        try:
            cmd = ["ssh", "-q", self.host, "exit"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout
            )

            if result.returncode == 0:
                if self.logger:
                    self.logger.info("SSH连接正常")
                return True
            else:
                if self.logger:
                    self.logger.error(f"SSH连接失败，返回码: {result.returncode}")
                    if result.stderr:
                        self.logger.error(f"错误信息: {result.stderr.decode()}")
                return False

        except subprocess.TimeoutExpired:
            if self.logger:
                self.logger.error(f"SSH连接检查超时（{timeout}秒）")
            return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"SSH连接检查异常: {str(e)}")
            return False
    
    def execute_command(
        self,
        command: str,
        check_error_keywords: bool = True,
        timeout: int = 3600,
        error_keywords: Optional[List[str]] = None
    ) -> Tuple[bool, str, int]:
        """
        执行SSH命令

        Args:
            command: 要执行的远程命令
            check_error_keywords: 是否检查输出中的错误关键词
            timeout: 命令执行超时时间（秒），默认1小时
            error_keywords: 自定义错误关键词列表

        Returns:
            (是否成功, 命令输出, 退出码)
        """
        try:
            # 构建完整的SSH命令，包含退出码捕获
            full_command = (
                f"{command}\n"
                f"EXIT_CODE=$?\n"
                f'echo "COMMAND_EXIT_CODE: $EXIT_CODE"\n'
                f"exit $EXIT_CODE"
            )

            cmd = ["ssh", self.host, full_command]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = result.stdout
            
            # 提取远程命令的退出码
            exit_code = result.returncode
            for line in output.splitlines():
                if line.startswith("COMMAND_EXIT_CODE:"):
                    try:
                        exit_code = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
            
            # 记录输出
            if self.logger:
                self.logger.info("远程命令执行输出:")
                for line in output.splitlines():
                    # 不记录退出码那一行
                    if not line.startswith("COMMAND_EXIT_CODE:"):
                        self.logger.info(line)
            
            # 检查是否有错误
            has_error = False
            if check_error_keywords:
                if error_keywords is None:
                    error_keywords = ["Error:", "Exception:", "Traceback", "FAILED"]
                has_error = any(keyword in output for keyword in error_keywords)
            
            success = (exit_code == 0) and (not has_error)
            
            return success, output, exit_code
            
        except subprocess.TimeoutExpired:
            error_msg = f"SSH命令执行超时（{timeout}秒）"
            if self.logger:
                self.logger.error(error_msg)
            return False, error_msg, -1
            
        except Exception as e:
            error_msg = f"SSH命令执行异常: {str(e)}"
            if self.logger:
                self.logger.error(error_msg)
            return False, error_msg, -1

    def execute_with_retry(
        self,
        command: str,
        task_name: str,
        max_retries: int = 10,
        retry_interval: int = 600,
        send_success_notify: bool = True,
        notifier: Optional['Notifier'] = None,
        timeout: int = 3600
    ) -> bool:
        """
        执行SSH命令，支持自动重试和通知
        
        Args:
            command: 远程执行的命令
            task_name: 任务名称（用于生成通知信息）
            max_retries: 最大重试次数，默认10次
            retry_interval: 重试间隔秒数，默认600秒(10分钟)
            send_success_notify: 是否发送成功通知，默认True
            notifier: 通知发送器实例
            timeout: 命令执行超时时间（秒）
            
        Returns:
            执行是否成功
        """
        retry_count = 0
        
        while retry_count < max_retries:
            if retry_count > 0:
                if self.logger:
                    self.logger.info(f"第 {retry_count} 次重试执行命令...")
            
            # 执行命令
            success, output, exit_code = self.execute_command(
                command=command,
                timeout=timeout
            )
            
            if not success:
                if self.logger:
                    self.logger.error(
                        f"Error: 命令执行失败，检测到错误信息或命令返回非零状态({exit_code})"
                    )
                
                # 如果不是最后一次重试，则等待后重试
                if retry_count < max_retries - 1:
                    wait_minutes = retry_interval // 60
                    if self.logger:
                        self.logger.info(f"将在{wait_minutes}分钟后重试...")
                    
                    if notifier:
                        notifier.send_failure(
                            task_name=task_name,
                            error_msg=f"退出码: {exit_code}",
                            retry_info=f"将在{wait_minutes}分钟后重试"
                        )
                    
                    time.sleep(retry_interval)
                    retry_count += 1
                else:
                    if self.logger:
                        self.logger.error(f"已达到最大重试次数({max_retries})，放弃执行")
                    
                    if notifier:
                        notifier.send_failure(
                            task_name=task_name,
                            error_msg=f"退出码: {exit_code}",
                            retry_info=f"已达到最大重试次数({max_retries})"
                        )
                    
                    return False
            else:
                if self.logger:
                    self.logger.info("命令执行完成")
                
                if send_success_notify and notifier:
                    notifier.send_success(task_name=task_name)
                
                return True
        
        return False
    
    def execute_script(
        self,
        script_path: str,
        args: Optional[List[str]] = None,
        interpreter: str = "bash",
        timeout: int = 3600
    ) -> Tuple[bool, str, int]:
        """
        执行远程脚本文件
        
        Args:
            script_path: 远程脚本路径
            args: 脚本参数列表
            interpreter: 脚本解释器，默认bash
            timeout: 执行超时时间（秒）
            
        Returns:
            (是否成功, 命令输出, 退出码)
        """
        command = f"{interpreter} {script_path}"
        if args:
            command += " " + " ".join(args)
        
        return self.execute_command(command, timeout=timeout)
    
    def get_remote_file_content(
        self,
        file_path: str,
        timeout: int = 60
    ) -> Tuple[bool, str]:
        """
        获取远程文件内容
        
        Args:
            file_path: 远程文件路径
            timeout: 超时时间（秒）
            
        Returns:
            (是否成功, 文件内容)
        """
        success, output, exit_code = self.execute_command(
            f"cat {file_path}",
            check_error_keywords=True,
            timeout=timeout
        )
        
        if success:
            # 移除最后的退出码行
            lines = output.splitlines()
            content = "\n".join(
                line for line in lines 
                if not line.startswith("COMMAND_EXIT_CODE:")
            )
            return True, content
        else:
            return False, ""


# 使用示例
if __name__ == "__main__":
    # 基础使用
    executor = SSHExecutor(host="ms197")
    
    # 检查连接
    if executor.check_connection():
        print("SSH连接正常")
        
        # 执行简单命令
        success, output, code = executor.execute_command("echo 'Hello from remote'")
        print(f"命令执行: {'成功' if success else '失败'}")
        print(f"退出码: {code}")
        print(f"输出:\n{output}")
    
    # 带日志和通知的使用
    try:
        from logger import Logger
        from notifier import Notifier
        
        logger = Logger()
        notifier = Notifier(
            api_url="https://reminderapi.joyslinktech.com/v1/push/key/YOUR_KEY",
            logger=logger
        )
        
        executor_with_logger = SSHExecutor(host="ms197", logger=logger)
        
        # 带重试的执行
        success = executor_with_logger.execute_with_retry(
            command="python /path/to/script.py",
            task_name="数据处理",
            max_retries=3,
            retry_interval=60,  # 1分钟
            notifier=notifier
        )
        
        print(f"任务执行: {'成功' if success else '失败'}")
        
    except ImportError:
        print("Logger或Notifier模块未找到，跳过带日志的示例")
    
    # 执行脚本
    success, output, code = executor.execute_script(
        script_path="/home/user/script.sh",
        args=["--input", "data.csv", "--output", "result.txt"]
    )
    
    # 获取文件内容
    success, content = executor.get_remote_file_content("/etc/hostname")
    if success:
        print(f"远程主机名: {content.strip()}")