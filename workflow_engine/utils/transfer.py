"""
文件传输模块

支持 rsync 和 scp 两种传输方式。
- rsync: 增量传输，适合大文件和目录同步（默认）
- scp: 简单传输，适合小文件，SSH自带无需安装
"""

import subprocess
from pathlib import Path
from typing import Optional, List

try:
    from logger import Logger
except ImportError:
    Logger = None


class FileTransfer:
    """文件传输器（支持 rsync 和 scp）"""

    def __init__(
        self,
        host: str,
        logger: Optional['Logger'] = None,
        remote_temp_dir: str = "/tmp",
        local_temp_dir: str = "/tmp"
    ):
        """
        初始化文件传输器

        Args:
            host: SSH配置中的主机名(在~/.ssh/config中配置)
            logger: 日志记录器实例
            remote_temp_dir: 远程临时目录（预压缩时使用），默认/tmp
            local_temp_dir: 本地临时目录（预压缩时使用），默认/tmp

        注意:
            SSH连接参数(user, port, IdentityFile等)应该在~/.ssh/config中预先配置
            rsync会通过SSH传输,自动使用SSH配置
        """
        self.host = host
        self.logger = logger
        self.remote_temp_dir = remote_temp_dir
        self.local_temp_dir = local_temp_dir

        # 检查rsync是否可用
        self._check_rsync_available()
    
    def _check_rsync_available(self) -> bool:
        """
        检查rsync是否安装
        
        Returns:
            rsync是否可用
        """
        try:
            result = subprocess.run(
                ["rsync", "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                if self.logger:
                    self.logger.debug("rsync工具可用")
                return True
            else:
                if self.logger:
                    self.logger.warning("rsync工具不可用，某些功能可能无法使用")
                return False
        except FileNotFoundError:
            if self.logger:
                self.logger.warning("未找到rsync工具，请先安装rsync")
            return False
        except Exception as e:
            if self.logger:
                self.logger.warning(f"检查rsync时出错: {str(e)}")
            return False
    
    def copy_from_remote(
        self,
        remote_path: str,
        local_path: str,
        method: str = "rsync",
        recursive: bool = False,
        preserve_times: bool = True,
        compress: bool = True,
        delete: bool = False,
        exclude: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        dry_run: bool = False,
        show_progress: bool = True,
        timeout: int = 600,
        pre_compress: bool = False,
        decompress: bool = True
    ) -> bool:
        """
        从远程主机复制文件到本地

        Args:
            remote_path: 远程文件/目录路径
            local_path: 本地目标路径
            method: 传输方法，"rsync"（默认）或 "scp"
            recursive: 是否递归复制目录
            preserve_times: 是否保留文件时间戳
            compress: 是否压缩传输数据（rsync/scp的流式压缩）
            delete: 是否删除本地多余的文件（仅rsync支持）
            exclude: 排除的文件/目录模式列表（仅rsync支持）
            include: 包含的文件/目录模式列表（仅rsync支持）
            dry_run: 是否只进行模拟运行（仅rsync支持）
            show_progress: 是否显示进度
            timeout: 超时时间（秒）
            pre_compress: 是否预压缩（远程打包→传输→本地解压）
            decompress: 是否解压（仅当pre_compress=True时有效，默认True）

        Returns:
            复制是否成功
        """
        if self.logger:
            self.logger.info(f"开始从远程复制 [{method}]: {remote_path} -> {local_path}")

        # 如果启用预压缩，使用预压缩传输流程
        if pre_compress:
            return self._copy_from_remote_with_precompress(
                remote_path=remote_path,
                local_path=local_path,
                exclude=exclude,
                timeout=timeout,
                decompress=decompress
            )

        # 确保本地目录存在
        local_dir = Path(local_path)
        if not local_dir.exists():
            local_dir.mkdir(parents=True, exist_ok=True)

        # 根据方法选择实现
        if method.lower() == "scp":
            return self._copy_from_remote_scp(
                remote_path=remote_path,
                local_path=local_path,
                recursive=recursive,
                compress=compress,
                show_progress=show_progress,
                timeout=timeout
            )
        else:  # 默认使用 rsync
            return self._copy_from_remote_rsync(
                remote_path=remote_path,
                local_path=local_path,
                recursive=recursive,
                preserve_times=preserve_times,
                compress=compress,
                delete=delete,
                exclude=exclude,
                include=include,
                dry_run=dry_run,
                show_progress=show_progress,
                timeout=timeout
            )

    def _copy_from_remote_rsync(
        self,
        remote_path: str,
        local_path: str,
        recursive: bool = False,
        preserve_times: bool = True,
        compress: bool = True,
        delete: bool = False,
        exclude: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        dry_run: bool = False,
        show_progress: bool = True,
        timeout: int = 600
    ) -> bool:
        """使用 rsync 从远程复制"""
        # 构建rsync命令
        cmd = ["rsync"]

        # 基本选项
        options = ["-v"]  # verbose

        if recursive:
            options.append("-r")  # recursive

        if preserve_times:
            options.append("-t")  # preserve times

        if compress:
            options.append("-z")  # compress

        if delete:
            options.append("--delete")  # delete extraneous files

        if dry_run:
            options.append("--dry-run")  # perform a trial run

        if show_progress:
            options.append("--progress")  # show progress

        # 添加排除规则
        if exclude:
            for pattern in exclude:
                options.extend(["--exclude", pattern])

        # 添加包含规则
        if include:
            for pattern in include:
                options.extend(["--include", pattern])

        cmd.extend(options)

        # 添加源和目标
        cmd.append(f"{self.host}:{remote_path}")
        cmd.append(local_path)

        # 执行命令
        return self._execute_transfer_command(cmd, timeout)

    def _copy_from_remote_scp(
        self,
        remote_path: str,
        local_path: str,
        recursive: bool = False,
        compress: bool = True,
        show_progress: bool = True,
        timeout: int = 600
    ) -> bool:
        """使用 scp 从远程复制"""
        # 构建scp命令
        cmd = ["scp"]

        # 基本选项
        if recursive:
            cmd.append("-r")  # recursive

        if compress:
            cmd.append("-C")  # compression

        if show_progress:
            cmd.append("-v")  # verbose (进度信息)

        # 添加源和目标
        cmd.append(f"{self.host}:{remote_path}")
        cmd.append(local_path)

        # 执行命令
        return self._execute_transfer_command(cmd, timeout)

    def _execute_transfer_command(self, cmd: List[str], timeout: int) -> bool:
        """执行传输命令的通用方法"""
        return self._execute_transfer_command_batch(cmd, timeout)


    def _execute_transfer_command_batch(self, cmd: List[str], timeout: int) -> bool:
        """执行传输命令（批量输出模式）"""
        try:
            if self.logger:
                self.logger.debug(f"执行命令: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            # 记录输出（改为 INFO 级别，确保显示）
            if result.stdout and self.logger:
                for line in result.stdout.splitlines():
                    self.logger.info(line)

            if result.returncode == 0:
                if self.logger:
                    self.logger.info("文件复制成功")
                return True
            else:
                if self.logger:
                    self.logger.error(f"文件复制失败，返回码: {result.returncode}")
                    if result.stderr:
                        self.logger.error(f"错误信息: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            if self.logger:
                self.logger.error(f"文件复制超时（{timeout}秒）")
            return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"文件复制异常: {str(e)}")
            return False

    def copy_to_remote(
        self,
        local_path: str,
        remote_path: str,
        method: str = "rsync",
        recursive: bool = False,
        preserve_times: bool = True,
        compress: bool = True,
        delete: bool = False,
        exclude: Optional[List[str]] = None,
        dry_run: bool = False,
        show_progress: bool = True,
        timeout: int = 600,
        pre_compress: bool = False,
        decompress: bool = True
    ) -> bool:
        """
        从本地复制文件到远程主机

        Args:
            local_path: 本地文件/目录路径
            remote_path: 远程目标路径
            method: 传输方法，"rsync"（默认）或 "scp"
            recursive: 是否递归复制目录
            preserve_times: 是否保留文件时间戳
            compress: 是否压缩传输数据（rsync/scp的流式压缩）
            delete: 是否删除远程多余的文件（仅rsync支持）
            exclude: 排除的文件/目录模式列表（仅rsync支持）
            dry_run: 是否只进行模拟运行（仅rsync支持）
            show_progress: 是否显示进度
            timeout: 超时时间（秒）
            pre_compress: 是否预压缩（本地打包→传输→远程解压）
            decompress: 是否解压（仅当pre_compress=True时有效，默认True）

        Returns:
            复制是否成功
        """
        if self.logger:
            self.logger.info(f"开始复制到远程 [{method}]: {local_path} -> {remote_path}")

        # 如果启用预压缩，使用预压缩传输流程
        if pre_compress:
            return self._copy_to_remote_with_precompress(
                local_path=local_path,
                remote_path=remote_path,
                exclude=exclude,
                timeout=timeout,
                decompress=decompress
            )

        # 根据方法选择实现
        if method.lower() == "scp":
            return self._copy_to_remote_scp(
                local_path=local_path,
                remote_path=remote_path,
                recursive=recursive,
                compress=compress,
                show_progress=show_progress,
                timeout=timeout
            )
        else:  # 默认使用 rsync
            return self._copy_to_remote_rsync(
                local_path=local_path,
                remote_path=remote_path,
                recursive=recursive,
                preserve_times=preserve_times,
                compress=compress,
                delete=delete,
                exclude=exclude,
                dry_run=dry_run,
                show_progress=show_progress,
                timeout=timeout
            )

    def _copy_to_remote_rsync(
        self,
        local_path: str,
        remote_path: str,
        recursive: bool = False,
        preserve_times: bool = True,
        compress: bool = True,
        delete: bool = False,
        exclude: Optional[List[str]] = None,
        dry_run: bool = False,
        show_progress: bool = True,
        timeout: int = 600
    ) -> bool:
        """使用 rsync 复制到远程"""
        # 构建rsync命令
        cmd = ["rsync"]

        # 基本选项
        options = ["-v"]

        if recursive:
            options.append("-r")

        if preserve_times:
            options.append("-t")

        if compress:
            options.append("-z")

        if delete:
            options.append("--delete")

        if dry_run:
            options.append("--dry-run")

        if show_progress:
            options.append("--progress")

        # 添加排除规则
        if exclude:
            for pattern in exclude:
                options.extend(["--exclude", pattern])

        cmd.extend(options)

        # 添加源和目标
        cmd.append(local_path)
        cmd.append(f"{self.host}:{remote_path}")

        # 执行命令
        return self._execute_transfer_command(cmd, timeout)

    def _copy_to_remote_scp(
        self,
        local_path: str,
        remote_path: str,
        recursive: bool = False,
        compress: bool = True,
        show_progress: bool = True,
        timeout: int = 600
    ) -> bool:
        """使用 scp 复制到远程"""
        # 构建scp命令
        cmd = ["scp"]

        # 基本选项
        if recursive:
            cmd.append("-r")  # recursive

        if compress:
            cmd.append("-C")  # compression

        if show_progress:
            cmd.append("-v")  # verbose (进度信息)

        # 添加源和目标
        cmd.append(local_path)
        cmd.append(f"{self.host}:{remote_path}")

        # 执行命令
        return self._execute_transfer_command(cmd, timeout)
    
    def sync_directory(
        self,
        source: str,
        destination: str,
        direction: str = "pull",
        exclude: Optional[List[str]] = None,
        delete: bool = True,
        dry_run: bool = False,
        timeout: int = 1200
    ) -> bool:
        """
        同步目录（双向同步助手）
        
        Args:
            source: 源目录路径
            destination: 目标目录路径
            direction: 方向，"pull"（从远程拉取）或"push"（推送到远程）
            exclude: 排除的文件/目录模式列表
            delete: 是否删除目标中多余的文件
            dry_run: 是否只进行模拟运行
            timeout: 超时时间（秒）
            
        Returns:
            同步是否成功
        """
        if direction == "pull":
            return self.copy_from_remote(
                remote_path=source,
                local_path=destination,
                recursive=True,
                delete=delete,
                exclude=exclude,
                dry_run=dry_run,
                timeout=timeout
            )
        elif direction == "push":
            return self.copy_to_remote(
                local_path=source,
                remote_path=destination,
                recursive=True,
                delete=delete,
                exclude=exclude,
                dry_run=dry_run,
                timeout=timeout
            )
        else:
            if self.logger:
                self.logger.error(f"不支持的同步方向: {direction}，请使用'pull'或'push'")
            return False
    
    def backup_remote_directory(
        self,
        remote_path: str,
        local_backup_path: str,
        exclude: Optional[List[str]] = None,
        timeout: int = 1800
    ) -> bool:
        """
        备份远程目录到本地
        
        Args:
            remote_path: 远程目录路径
            local_backup_path: 本地备份路径
            exclude: 排除的文件/目录模式列表
            timeout: 超时时间（秒）
            
        Returns:
            备份是否成功
        """
        if self.logger:
            self.logger.info(f"开始备份远程目录: {remote_path}")
        
        return self.copy_from_remote(
            remote_path=remote_path,
            local_path=local_backup_path,
            recursive=True,
            preserve_times=True,
            compress=True,
            exclude=exclude,
            show_progress=True,
            timeout=timeout
        )

    def _copy_from_remote_with_precompress(
        self,
        remote_path: str,
        local_path: str,
        exclude: Optional[List[str]] = None,
        timeout: int = 600,
        decompress: bool = True
    ) -> bool:
        """
        使用预压缩方式从远程复制

        流程: 远程压缩 → 传输压缩包 → [可选]本地解压 → 清理临时文件

        Args:
            remote_path: 远程文件/目录路径
            local_path: 本地目标路径
            exclude: 排除的文件/目录模式列表
            timeout: 超时时间（秒）
            decompress: 是否在本地解压（默认True）

        Returns:
            复制是否成功
        """
        import time
        import os

        if self.logger:
            self.logger.info(f"使用预压缩模式从远程复制: {remote_path} -> {local_path}")

        # 生成临时文件名
        timestamp = int(time.time())
        basename = os.path.basename(remote_path.rstrip('/'))
        if not basename:
            basename = "transfer"
        archive_name = f"{basename}_transfer_{timestamp}.tar.gz"
        remote_archive = f"{self.remote_temp_dir}/{archive_name}"
        local_archive = f"{self.local_temp_dir}/{archive_name}"

        try:
            # 步骤1: 在远程压缩
            if self.logger:
                self.logger.info(f"步骤1/3: 在远程压缩文件到 {remote_archive}")

            # 构建tar命令
            tar_cmd = f"tar -czf {remote_archive}"

            # 添加排除规则
            if exclude:
                for pattern in exclude:
                    tar_cmd += f" --exclude='{pattern}'"

            # 添加源路径 (使用 -C 切换到父目录，只打包目标目录/文件)
            remote_parent = os.path.dirname(remote_path.rstrip('/'))
            remote_target = os.path.basename(remote_path.rstrip('/'))
            if remote_parent:
                tar_cmd += f" -C {remote_parent} {remote_target}"
            else:
                tar_cmd += f" {remote_path}"

            # 执行远程压缩
            ssh_compress_cmd = ["ssh", self.host, tar_cmd]
            result = subprocess.run(
                ssh_compress_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                if self.logger:
                    self.logger.error(f"远程压缩失败: {result.stderr}")
                return False

            if self.logger:
                self.logger.info("远程压缩完成")

            # 步骤2: 传输压缩包
            if self.logger:
                self.logger.info(f"步骤2/3: 传输压缩包 {archive_name}")

            scp_cmd = ["scp", f"{self.host}:{remote_archive}", local_archive]
            success = self._execute_transfer_command_batch(scp_cmd, timeout)

            if not success:
                if self.logger:
                    self.logger.error("压缩包传输失败")
                # 清理远程临时文件
                subprocess.run(["ssh", self.host, f"rm -f {remote_archive}"], timeout=10)
                return False

            if self.logger:
                self.logger.info("压缩包传输完成")

            # 步骤3: 本地解压（可选）
            if decompress:
                if self.logger:
                    self.logger.info(f"步骤3/4: 解压到 {local_path}")

                # 确保本地目录存在
                local_dir = Path(local_path)
                if not local_dir.exists():
                    local_dir.mkdir(parents=True, exist_ok=True)

                # 解压
                tar_extract_cmd = ["tar", "-xzf", local_archive, "-C", local_path]
                result = subprocess.run(
                    tar_extract_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                if result.returncode != 0:
                    if self.logger:
                        self.logger.error(f"本地解压失败: {result.stderr}")
                        self.logger.warning(f"压缩包保留在: {local_archive}")
                    return False

                if self.logger:
                    self.logger.info("解压完成")
            else:
                if self.logger:
                    self.logger.info(f"步骤3/4: 跳过解压，压缩文件保留在 {local_archive}")
                # decompress=False时，压缩文件就是最终产物，不删除

            # 步骤4: 清理临时文件
            if self.logger:
                self.logger.info("步骤4/4: 清理临时文件...")

            # 仅在解压后才删除本地压缩包
            if decompress:
                try:
                    os.remove(local_archive)
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"删除本地临时文件失败: {str(e)}")
            else:
                if self.logger:
                    self.logger.info(f"压缩文件保留: {local_archive}")

            # 删除远程压缩包
            try:
                subprocess.run(
                    ["ssh", self.host, f"rm -f {remote_archive}"],
                    timeout=10,
                    capture_output=True
                )
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"删除远程临时文件失败: {str(e)}")

            if self.logger:
                self.logger.info("预压缩传输完成")

            return True

        except subprocess.TimeoutExpired:
            if self.logger:
                self.logger.error(f"预压缩传输超时（{timeout}秒）")
            # 尝试清理
            try:
                os.remove(local_archive)
            except:
                pass
            try:
                subprocess.run(["ssh", self.host, f"rm -f {remote_archive}"], timeout=10)
            except:
                pass
            return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"预压缩传输异常: {str(e)}")
            # 尝试清理
            try:
                os.remove(local_archive)
            except:
                pass
            try:
                subprocess.run(["ssh", self.host, f"rm -f {remote_archive}"], timeout=10)
            except:
                pass
            return False

    def _copy_to_remote_with_precompress(
        self,
        local_path: str,
        remote_path: str,
        exclude: Optional[List[str]] = None,
        timeout: int = 600,
        decompress: bool = True
    ) -> bool:
        """
        使用预压缩方式复制到远程

        流程: 本地压缩 → 传输压缩包 → [可选]远程解压 → 清理临时文件

        Args:
            local_path: 本地文件/目录路径
            remote_path: 远程目标路径
            exclude: 排除的文件/目录模式列表
            timeout: 超时时间（秒）
            decompress: 是否在远程解压（默认True）

        Returns:
            复制是否成功
        """
        import time
        import os

        if self.logger:
            self.logger.info(f"使用预压缩模式复制到远程: {local_path} -> {remote_path}")

        # 生成临时文件名
        timestamp = int(time.time())
        basename = os.path.basename(local_path.rstrip('/'))
        if not basename:
            basename = "transfer"
        archive_name = f"{basename}_transfer_{timestamp}.tar.gz"
        local_archive = f"{self.local_temp_dir}/{archive_name}"

        # 根据 decompress 决定远程压缩文件的位置
        # decompress=True: 使用临时目录（因为会解压到 remote_path，压缩文件会被删除）
        # decompress=False: 直接放到 remote_path（压缩文件就是最终产物）
        if decompress:
            remote_archive = f"{self.remote_temp_dir}/{archive_name}"
        else:
            # 不解压时，压缩文件直接保存到目标路径
            remote_archive = f"{remote_path}/{archive_name}"

        # 使用 try-finally 确保异常时也清理本地临时文件
        local_archive_created = False
        try:
            # 步骤1: 本地压缩
            if self.logger:
                self.logger.info(f"步骤1/3: 在本地压缩文件到 {local_archive}")

            # 构建tar命令
            tar_cmd = ["tar", "-czf", local_archive]

            # 添加排除规则
            if exclude:
                for pattern in exclude:
                    tar_cmd.extend(["--exclude", pattern])

            # 添加源路径 (使用 -C 切换到父目录)
            local_parent = os.path.dirname(local_path.rstrip('/'))
            local_target = os.path.basename(local_path.rstrip('/'))
            if local_parent:
                tar_cmd.extend(["-C", local_parent, local_target])
            else:
                tar_cmd.append(local_path)

            # 执行本地压缩
            result = subprocess.run(
                tar_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                if self.logger:
                    self.logger.error(f"本地压缩失败: {result.stderr}")
                return False

            local_archive_created = True
            if self.logger:
                self.logger.info("本地压缩完成")

            # 步骤2: 传输压缩包
            if self.logger:
                self.logger.info(f"步骤2/3: 传输压缩包 {archive_name}")

            scp_cmd = ["scp", local_archive, f"{self.host}:{remote_archive}"]
            success = self._execute_transfer_command_batch(scp_cmd, timeout)

            if not success:
                if self.logger:
                    self.logger.error("压缩包传输失败")
                # 清理本地临时文件
                try:
                    os.remove(local_archive)
                except:
                    pass
                return False

            if self.logger:
                self.logger.info("压缩包传输完成")

            # 步骤3: 远程解压（可选）
            if decompress:
                if self.logger:
                    self.logger.info(f"步骤3/4: 在远程解压到 {remote_path}")

                # 创建远程目录并解压
                ssh_extract_cmd = [
                    "ssh", self.host,
                    f"mkdir -p {remote_path} && tar -xzf {remote_archive} -C {remote_path}"
                ]

                result = subprocess.run(
                    ssh_extract_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                if result.returncode != 0:
                    if self.logger:
                        self.logger.error(f"远程解压失败: {result.stderr}")
                        self.logger.warning(f"远程压缩包保留在: {remote_archive}")
                    return False

                if self.logger:
                    self.logger.info("解压完成")
            else:
                if self.logger:
                    self.logger.info(f"步骤3/4: 跳过解压，压缩文件保留在 {remote_archive}")
                # decompress=False时，压缩文件就是最终产物，不删除

            # 步骤4: 清理远程临时文件（如果需要）
            if self.logger:
                self.logger.info("步骤4/4: 清理远程临时文件...")

            # 仅在解压后才删除远程压缩包
            if decompress:
                try:
                    subprocess.run(
                        ["ssh", self.host, f"rm -f {remote_archive}"],
                        timeout=10,
                        capture_output=True
                    )
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"删除远程临时文件失败: {str(e)}")
            else:
                if self.logger:
                    self.logger.info(f"远程压缩文件保留: {remote_archive}")

            if self.logger:
                self.logger.info("预压缩传输完成")

            return True

        except subprocess.TimeoutExpired:
            if self.logger:
                self.logger.error(f"预压缩传输超时（{timeout}秒）")
            return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"预压缩传输异常: {str(e)}")
            return False

        finally:
            # 确保清理本地临时压缩文件（仅当创建成功时）
            if local_archive_created:
                try:
                    if os.path.exists(local_archive):
                        os.remove(local_archive)
                        if self.logger:
                            self.logger.debug(f"清理本地临时压缩文件: {local_archive}")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"清理本地临时文件失败 {local_archive}: {str(e)}")


# 使用示例
if __name__ == "__main__":
    # 基础使用
    transfer = FileTransfer(host="ms197")
    
    # 从远程复制单个文件
    success = transfer.copy_from_remote(
        remote_path="/remote/path/file.txt",
        local_path="./local/path/"
    )
    print(f"文件复制: {'成功' if success else '失败'}")
    
    # 从远程递归复制目录
    success = transfer.copy_from_remote(
        remote_path="/remote/data/",
        local_path="./local/data/",
        recursive=True,
        exclude=["*.tmp", "*.log", "__pycache__"]
    )
    
    # 复制到远程
    success = transfer.copy_to_remote(
        local_path="./local/results/",
        remote_path="/remote/results/",
        recursive=True
    )
    
    # 带日志的使用
    try:
        from logger import Logger
        
        logger = Logger()
        transfer_with_log = FileTransfer(host="ms197", logger=logger)
        
        # 同步目录（从远程拉取）
        success = transfer_with_log.sync_directory(
            source="/remote/workspace/",
            destination="./local/workspace/",
            direction="pull",
            exclude=["*.pyc", ".git", "node_modules"],
            delete=True
        )
        
        # 备份远程目录
        success = transfer_with_log.backup_remote_directory(
            remote_path="/remote/important_data/",
            local_backup_path="./backups/data/",
            exclude=["*.tmp"]
        )
        
    except ImportError:
        print("Logger模块未找到，跳过带日志的示例")
    
    # 模拟运行（不实际传输）
    transfer.copy_from_remote(
        remote_path="/remote/large_data/",
        local_path="./local/",
        recursive=True,
        dry_run=True  # 只显示会传输什么，不实际传输
    )