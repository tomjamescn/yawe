"""
文件复制任务
"""

from typing import Tuple
from .base import Task


class FileCopyTask(Task):
    """文件复制任务（支持remote_to_local和local_to_remote）"""

    def __init__(self, name: str, config: dict, context: dict, workflow_context: dict = None):
        """初始化文件复制任务"""
        super().__init__(name, config, context, workflow_context)

        # 用于存储执行上下文信息（供export_context使用）
        self._execution_context = {}

    def execute(self) -> Tuple[bool, str]:
        """
        执行文件复制

        Returns:
            (成功标志, 消息)
        """
        self.logger.info(f"执行任务: {self.name} - 文件传输")

        # 获取host（必填）
        host = self.config.get('host')
        if not host:
            return False, "文件传输任务必须指定 host 参数"

        # 获取临时目录配置（任务级 > 全局级）
        remote_temp_dir = self.config.get('remote_temp_dir')
        if remote_temp_dir is None:
            remote_temp_dir = self.global_config.transfer_remote_temp_dir

        local_temp_dir = self.config.get('local_temp_dir')
        if local_temp_dir is None:
            local_temp_dir = self.global_config.transfer_local_temp_dir

        # 检查是否需要创建或切换host
        if not self.transfer or self.transfer.host != host:
            self.logger.info(f"创建/切换传输连接到: {host}")
            # 创建或重新初始化Transfer
            from workflow_engine.utils.transfer import FileTransfer
            self.transfer = FileTransfer(
                host=host,
                logger=self.logger,
                remote_temp_dir=remote_temp_dir,
                local_temp_dir=local_temp_dir
            )
            self.context['transfer'] = self.transfer

        # 获取传输方向
        direction = self.config.get('direction', 'remote_to_local')

        # 获取文件复制项列表
        items = self.get_param('items')
        if not items:
            self.logger.warning("文件传输任务未配置 items 参数")
            return False, "未配置文件传输项"

        # 获取传输方法（任务级别配置，默认 rsync）
        task_transfer_method = self.config.get('transfer_method', 'rsync')

        # 获取传输配置
        show_progress = self.get_param('show_progress')
        if show_progress is None:
            show_progress = self.global_config.transfer_show_progress

        compress = self.get_param('compress')
        if compress is None:
            compress = self.global_config.transfer_compress

        preserve_times = self.get_param('preserve_times')
        if preserve_times is None:
            preserve_times = self.global_config.transfer_preserve_times

        timeout = self.get_param('timeout')
        if not timeout:
            timeout = self.global_config.transfer_timeout

        # 获取预压缩配置（任务级别，默认 False）
        task_pre_compress = self.config.get('pre_compress', False)

        # 获取解压配置（任务级别 > 全局级别，默认 True）
        task_decompress = self.config.get('decompress')
        if task_decompress is None:
            task_decompress = self.global_config.transfer_decompress

        # 初始化执行上下文
        import time
        import os
        self._execution_context = {
            'direction': direction,
            'host': host,
            'start_time': time.time(),
            'compress': task_pre_compress,
            'decompress': task_decompress,
            'items': []
        }

        # 遍历复制项
        failed_items = []
        for item in items:
            # 支持新旧两种配置格式
            remote_path = item.get('remote') or item.get('remote_path')
            local_path = item.get('local') or item.get('local_path')
            recursive = item.get('recursive', False)
            exclude = item.get('exclude', [])

            # 获取传输方法（项级别 > 任务级别 > 默认rsync）
            transfer_method = item.get('method', task_transfer_method)

            # 获取预压缩设置（项级别 > 任务级别 > 默认False）
            pre_compress = item.get('pre_compress', task_pre_compress)

            # 获取解压设置（项级别 > 任务级别 > 全局级别 > 默认True）
            decompress = item.get('decompress', task_decompress)

            if not remote_path or not local_path:
                self.logger.warning(f"跳过无效的传输配置项: {item}")
                continue

            # 记录item开始时间
            item_start_time = time.time()

            # 根据方向执行传输
            if direction == 'remote_to_local':
                self.logger.info(f"从远程复制: {remote_path} -> {local_path}")
                success = self.transfer.copy_from_remote(
                    remote_path=remote_path,
                    local_path=local_path,
                    method=transfer_method,
                    recursive=recursive,
                    exclude=exclude if exclude else None,
                    show_progress=show_progress,
                    compress=compress,
                    preserve_times=preserve_times,
                    timeout=timeout,
                    pre_compress=pre_compress,
                    decompress=decompress
                )
            elif direction == 'local_to_remote':
                self.logger.info(f"传输到远程: {local_path} -> {remote_path}")
                success = self.transfer.copy_to_remote(
                    local_path=local_path,
                    remote_path=remote_path,
                    method=transfer_method,
                    recursive=recursive,
                    exclude=exclude if exclude else None,
                    show_progress=show_progress,
                    compress=compress,
                    preserve_times=preserve_times,
                    timeout=timeout,
                    pre_compress=pre_compress,
                    decompress=decompress
                )
            else:
                self.logger.error(f"未知的传输方向: {direction}")
                failed_items.append(f"{remote_path} (未知方向)")
                continue

            # 计算传输耗时
            item_transfer_time = time.time() - item_start_time

            if not success:
                self.logger.error(f"传输失败: {remote_path}")
                failed_items.append(remote_path)
            else:
                self.logger.info(f"传输完成: {remote_path}")

                # 收集item的传输信息（用于导出变量）
                if pre_compress:
                    # 预压缩模式：生成压缩文件名
                    timestamp = int(item_start_time)
                    basename = os.path.basename((remote_path if direction == 'remote_to_local' else local_path).rstrip('/'))
                    if not basename:
                        basename = "transfer"
                    archive_name = f"{basename}_transfer_{timestamp}.tar.gz"

                    # 根据方向和decompress确定压缩文件位置
                    if direction == 'remote_to_local':
                        if decompress:
                            # 远程→本地，已解压
                            archive_path = None  # 已删除
                        else:
                            # 远程→本地，未解压（保留在本地临时目录）
                            archive_path = f"{self.transfer.local_temp_dir}/{archive_name}"
                            # 注册本地临时文件用于清理
                            if 'coordinator' in self.context:
                                self.context['coordinator'].register_temp_file(archive_path)
                    else:  # local_to_remote
                        if decompress:
                            # 本地→远程，已解压
                            archive_path = None  # 已删除
                        else:
                            # 本地→远程，未解压（直接保存到目标路径）
                            archive_path = f"{remote_path}/{archive_name}"
                            # 远程文件不需要注册（只清理本地临时文件）

                    item_info = {
                        'remote_path': remote_path,
                        'local_path': local_path,
                        'pre_compress': True,
                        'decompress': decompress,
                        'archive_name': archive_name,
                        'archive_path': archive_path,
                        'transfer_time': round(item_transfer_time, 2)
                    }
                else:
                    # 普通模式
                    item_info = {
                        'remote_path': remote_path,
                        'local_path': local_path,
                        'pre_compress': False,
                        'transfer_time': round(item_transfer_time, 2)
                    }

                self._execution_context['items'].append(item_info)

        # 计算总耗时
        total_time = time.time() - self._execution_context['start_time']
        self._execution_context['total_time'] = round(total_time, 2)

        # 检查是否有失败项
        if failed_items:
            error_msg = f"部分文件传输失败: {', '.join(failed_items)}"
            return False, error_msg

        self.logger.info("所有文件传输完成")
        return True, "所有文件传输完成"

    def export_context(self) -> dict:
        """
        导出任务执行上下文（供后续任务使用）

        导出的变量包括：
        - direction: 传输方向
        - host: 目标主机
        - compress: 是否使用预压缩
        - decompress: 是否解压
        - total_time: 总耗时
        - archive_name: 压缩文件名（仅compress=True时）
        - archive_path: 压缩文件路径（仅compress=True且decompress=False时）
        - remote_path: 远程路径（第一个item）
        - local_path: 本地路径（第一个item）
        - items: 所有传输项的详细信息

        Returns:
            上下文变量字典
        """
        if not self._execution_context or not self._execution_context.get('items'):
            return {}

        # 基础信息
        exported = {
            'direction': self._execution_context.get('direction'),
            'host': self._execution_context.get('host'),
            'compress': self._execution_context.get('compress', False),
            'decompress': self._execution_context.get('decompress', True),
            'total_time': self._execution_context.get('total_time', 0),
            'items_count': len(self._execution_context.get('items', []))
        }

        # 获取第一个item的信息（作为快捷访问）
        first_item = self._execution_context['items'][0]
        exported['remote_path'] = first_item.get('remote_path')
        exported['local_path'] = first_item.get('local_path')

        # 如果使用了预压缩，导出压缩文件信息
        if first_item.get('pre_compress'):
            exported['archive_name'] = first_item.get('archive_name')
            if not first_item.get('decompress'):
                # 未解压时，导出压缩文件路径
                exported['archive_path'] = first_item.get('archive_path')

        # 导出所有items的详细信息
        exported['items'] = self._execution_context.get('items', [])

        return exported
