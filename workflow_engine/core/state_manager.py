"""
工作流状态管理器

负责工作流执行状态的持久化、恢复、验证和清理
"""

import os
import json
import hashlib
import glob
import fcntl
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path


class WorkflowStateManager:
    """工作流状态管理器"""

    STATE_VERSION = "1.0"
    STATE_DIR = "logs/.workflow_state"
    LOCK_FILE = "logs/.workflow_state/.lock"

    def __init__(self, config, logger):
        """
        初始化状态管理器

        Args:
            config: 配置对象
            logger: 日志记录器
        """
        self.config = config
        self.logger = logger
        self.config_file = getattr(config, 'config_file', 'config.yaml')
        self.lock_fd = None

        # 确保状态目录存在
        os.makedirs(self.STATE_DIR, exist_ok=True)

    def calculate_config_hash(self) -> str:
        """
        计算配置文件的MD5哈希值

        Returns:
            配置文件哈希值(前8位)
        """
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return hashlib.md5(content.encode()).hexdigest()[:8]
        except Exception as e:
            self.logger.warning(f"计算配置哈希失败: {e}, 使用默认值")
            return "00000000"

    def create_state(self, workflow_config: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """
        创建新的工作流状态

        Args:
            workflow_config: 工作流配置
            run_id: 运行ID

        Returns:
            状态字典
        """
        tasks_config = workflow_config.get('tasks', [])
        settings = workflow_config.get('settings', {})

        # 创建任务状态列表
        tasks = []
        for idx, task_config in enumerate(tasks_config, 1):
            task_state = {
                'name': task_config.get('name', f'task_{idx}'),
                'type': task_config.get('type', 'unknown'),
                'status': 'pending',
                'start_time': None,
                'end_time': None,
                'message': '',
                'exported_context': {}
            }
            tasks.append(task_state)

        # 创建状态结构
        state = {
            'version': self.STATE_VERSION,
            'metadata': {
                'config_file': self.config_file,
                'config_hash': self.calculate_config_hash(),
                'run_id': run_id,
                'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'workflow_status': 'running',
                'stop_on_first_error': settings.get('stop_on_first_error', True),
                'total_tasks': len(tasks)
            },
            'tasks': tasks,
            'workflow_context': {}
        }

        return state

    def save_state(self, state: Dict[str, Any]):
        """
        保存状态到文件(使用原子写入)

        Args:
            state: 状态字典
        """
        try:
            # 更新最后修改时间
            state['metadata']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 生成状态文件路径
            state_file = self._get_state_file_path(state['metadata'])

            # 使用临时文件+原子rename确保写入完整性
            temp_file = f"{state_file}.tmp"

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            # 原子操作
            os.rename(temp_file, state_file)

            self.logger.debug(f"状态已保存: {state_file}")

        except Exception as e:
            self.logger.error(f"保存状态文件失败: {e}")

    def load_latest_failed_state(self) -> Optional[Dict[str, Any]]:
        """
        加载最近的失败状态

        Returns:
            状态字典,如果没有找到返回None
        """
        try:
            # 查找所有状态文件
            pattern = os.path.join(self.STATE_DIR, "workflow_state_*.json")
            state_files = glob.glob(pattern)

            if not state_files:
                self.logger.debug("未找到任何状态文件")
                return None

            # 查找失败或中断的状态文件
            failed_states = []

            for state_file in state_files:
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)

                    workflow_status = state.get('metadata', {}).get('workflow_status', '')

                    # 只考虑失败或中断的状态
                    if workflow_status in ('failed', 'interrupted'):
                        last_update = state['metadata'].get('last_update', '')
                        failed_states.append((state_file, last_update, state))

                except Exception as e:
                    self.logger.warning(f"读取状态文件失败 {state_file}: {e}")
                    continue

            if not failed_states:
                self.logger.debug("未找到失败或中断的状态文件")
                return None

            # 按最后更新时间排序,返回最新的
            failed_states.sort(key=lambda x: x[1], reverse=True)
            latest_file, _, latest_state = failed_states[0]

            self.logger.info(f"找到最近的失败状态: {os.path.basename(latest_file)}")
            return latest_state

        except Exception as e:
            self.logger.error(f"加载失败状态时出错: {e}")
            return None

    def validate_state(self, state: Dict[str, Any], force: bool = False) -> Tuple[bool, str]:
        """
        验证状态文件的有效性

        Args:
            state: 状态字典
            force: 是否强制恢复(忽略配置变更)

        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 1. 检查版本
            version = state.get('version')
            if version != self.STATE_VERSION:
                return False, f"状态文件版本不兼容 (文件版本: {version}, 当前版本: {self.STATE_VERSION})"

            # 2. 检查必要字段
            if 'metadata' not in state or 'tasks' not in state:
                return False, "状态文件缺少必要字段"

            metadata = state['metadata']
            required_fields = ['config_hash', 'run_id', 'start_time']
            for field in required_fields:
                if field not in metadata:
                    return False, f"元数据缺少必要字段: {field}"

            # 3. 检查配置文件是否变更
            if not force:
                current_hash = self.calculate_config_hash()
                state_hash = metadata.get('config_hash')

                if current_hash != state_hash:
                    error_msg = (
                        f"配置文件已变更,无法恢复!\n"
                        f"状态文件配置hash: {state_hash}\n"
                        f"当前配置文件hash: {current_hash}\n\n"
                        f"解决方案:\n"
                        f"1. 放弃恢复,重新运行: python3 src/coordinator.py\n"
                        f"2. 强制恢复(使用新配置): python3 src/coordinator.py -r --force\n\n"
                        f"注意: 强制恢复可能导致不一致,请谨慎使用!"
                    )
                    return False, error_msg

            return True, ""

        except Exception as e:
            return False, f"验证状态文件时出错: {str(e)}"

    def cleanup_old_states(self, older_than_days: int = 30) -> int:
        """
        清理旧的状态文件

        Args:
            older_than_days: 清理多少天前的成功状态文件

        Returns:
            清理的文件数量
        """
        try:
            pattern = os.path.join(self.STATE_DIR, "workflow_state_*.json")
            state_files = glob.glob(pattern)

            removed_count = 0
            current_time = time.time()
            cutoff_time = current_time - (older_than_days * 24 * 3600)

            for state_file in state_files:
                try:
                    # 读取状态文件
                    with open(state_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)

                    workflow_status = state.get('metadata', {}).get('workflow_status', '')

                    # 只清理成功的状态文件
                    if workflow_status == 'success':
                        file_mtime = os.path.getmtime(state_file)

                        if file_mtime < cutoff_time:
                            os.remove(state_file)
                            removed_count += 1
                            self.logger.debug(f"清理旧状态文件: {os.path.basename(state_file)}")

                except Exception as e:
                    self.logger.warning(f"清理状态文件失败 {state_file}: {e}")
                    continue

            if removed_count > 0:
                self.logger.info(f"清理了 {removed_count} 个超过 {older_than_days} 天的成功状态文件")

            return removed_count

        except Exception as e:
            self.logger.error(f"清理状态文件时出错: {e}")
            return 0

    def acquire_lock(self) -> bool:
        """
        获取工作流执行锁

        Returns:
            是否成功获取锁
        """
        try:
            # 确保锁文件目录存在
            os.makedirs(os.path.dirname(self.LOCK_FILE), exist_ok=True)

            # 打开锁文件
            self.lock_fd = open(self.LOCK_FILE, 'w')

            # 尝试获取排他锁(非阻塞)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # 写入当前进程PID
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()

            self.logger.debug(f"成功获取工作流锁: {self.LOCK_FILE}")
            return True

        except IOError:
            # 锁已被其他进程持有
            self.logger.debug("工作流锁已被其他进程持有")
            return False
        except Exception as e:
            self.logger.error(f"获取工作流锁失败: {e}")
            return False

    def release_lock(self):
        """释放工作流执行锁"""
        try:
            if self.lock_fd:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
                self.lock_fd = None

                # 删除锁文件
                if os.path.exists(self.LOCK_FILE):
                    os.remove(self.LOCK_FILE)

                self.logger.debug("已释放工作流锁")

        except Exception as e:
            self.logger.warning(f"释放工作流锁失败: {e}")

    def _get_state_file_path(self, metadata: Dict[str, Any]) -> str:
        """
        获取状态文件路径

        Args:
            metadata: 元数据字典

        Returns:
            状态文件路径
        """
        config_hash = metadata.get('config_hash', '00000000')
        run_id = metadata.get('run_id', 'unknown')
        filename = f"workflow_state_{config_hash}_{run_id}.json"
        return os.path.join(self.STATE_DIR, filename)


# 模块测试
if __name__ == "__main__":
    # 简单的测试代码
    class MockConfig:
        config_file = "config.yaml"

    class MockLogger:
        def debug(self, msg): print(f"[DEBUG] {msg}")
        def info(self, msg): print(f"[INFO] {msg}")
        def warning(self, msg): print(f"[WARNING] {msg}")
        def error(self, msg): print(f"[ERROR] {msg}")

    config = MockConfig()
    logger = MockLogger()

    manager = WorkflowStateManager(config, logger)

    # 测试创建状态
    workflow_config = {
        'settings': {'stop_on_first_error': True},
        'tasks': [
            {'name': 'task1', 'type': 'command'},
            {'name': 'task2', 'type': 'transfer'}
        ]
    }

    state = manager.create_state(workflow_config, '20251129_120000')
    print("\n创建的状态:")
    print(json.dumps(state, indent=2, ensure_ascii=False))

    # 测试保存状态
    print("\n保存状态...")
    manager.save_state(state)

    # 测试加载状态
    print("\n加载最近的失败状态...")
    # (因为状态是running,不会被load_latest_failed_state找到)

    print("\n测试完成!")
