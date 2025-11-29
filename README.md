# YAWE (Yet Another Workflow Engine)

一个轻量级、灵活、配置驱动的工作流任务编排框架。

## 核心特性

- **完全配置驱动**: 通过 YAML 配置文件定义工作流，无需编写代码
- **断点续传**: 任务级别的状态管理和恢复，失败后可从断点继续
- **SSH 远程执行**: 内置 SSH 执行器，支持远程命令执行和文件传输
- **灵活的错误处理**: 支持任务级别的错误处理策略和通知
- **任务间变量传递**: 支持任务导出变量供后续任务使用
- **Jinja2 模板**: 命令支持模板渲染和变量替换
- **并发防护**: 使用文件锁防止工作流并发执行

## 快速开始

### 安装

```bash
# 方式1: 从源码安装（开发模式）
git clone https://github.com/tomjamescn/yawe.git
cd yawe
pip install -e .

# 方式2: 从 PyPI 安装
pip install yawe

# 方式3: 最小安装（仅依赖）
pip install -r requirements.txt
```

### 5分钟上手

**1. 创建配置文件** `my_workflow.yaml`:

```yaml
logger:
  log_dir: logs
  level: INFO

workflow:
  settings:
    stop_on_first_error: true

  tasks:
    - name: hello
      type: command
      executor: local
      command: "echo 'Hello from YAWE!'"
```

**2. 编写执行脚本** `run.py`:

```python
from workflow_engine import Config, Logger, WorkflowEngine

config = Config("my_workflow.yaml")
logger = Logger(log_dir=config.log_dir, level=config.log_level)

context = {'logger': logger, 'config': config}
engine = WorkflowEngine(config.get('workflow'), context)

exit_code = engine.run()
print(f"Exit code: {exit_code}")
```

**3. 运行**:

```bash
python run.py
```

### 常用任务示例

#### SSH远程命令

```yaml
- name: remote_task
  type: command
  executor: ssh
  host: my_server  # 在 ~/.ssh/config 中配置
  command: "python script.py"
  timeout: 3600
```

#### 本地命令带参数

```yaml
- name: template_task
  type: command
  executor: local
  command_template: |
    echo "Processing {{ count }} items"
    for i in {1..{{ count }}}; do
      echo "Item $i"
    done
  params:
    count: 5
```

#### 文件传输

```yaml
- name: sync_files
  type: transfer
  host: my_server
  direction: remote_to_local  # 或 local_to_remote
  params:
    items:
      - remote: /data/results
        local: ./results
        recursive: true
        exclude:
          - "*.tmp"
          - "*.log"
```

#### 带重试的SSH任务

```yaml
- name: critical_job
  type: command
  executor: ssh
  host: my_server
  command: "python important_script.py"
  retry:
    max_retries: 3
    retry_interval: 300  # 5分钟
```

### SSH配置

在 `~/.ssh/config` 中配置主机:

```
Host my_server
    HostName 192.168.1.100
    User username
    Port 22
    IdentityFile ~/.ssh/id_rsa
```

然后在任务中使用 `host: my_server`。

## 支持的任务类型

### 1. Command Task (命令任务)

执行 SSH 远程命令或本地命令。

```yaml
- name: my_command
  type: command
  executor: ssh  # 或 local
  host: server1  # SSH时必需
  command_template: |
    cd {{ workspace }}
    python script.py --arg {{ value }}
  params:
    workspace: /home/user
    value: 123
  timeout: 3600
```

**高级特性**:
- Jinja2 模板渲染
- 多重验证机制（退出码、错误关键词、成功关键词、输出文件）
- 自动重试机制
- 使用前置任务的导出变量

### 2. Transfer Task (文件传输)

支持 rsync 和 scp 两种传输方式。

```yaml
- name: sync_data
  type: transfer
  host: server1
  direction: remote_to_local  # 或 local_to_remote
  transfer_method: rsync  # 或 scp
  pre_compress: true  # 预压缩传输（适合慢速网络）
  params:
    items:
      - remote: /data/model
        local: ./models
        recursive: true
        exclude:
          - "*.tmp"
          - "*.log"
```

## 断点续传

系统自动保存工作流状态，失败后可以从断点恢复:

```bash
# 正常运行
python run.py

# 从上次失败处恢复
python run.py -r

# 从指定任务开始执行
python run.py --from-task "task_name"
```

## 任务间变量传递

任务可以导出变量供后续任务使用:

```yaml
workflow:
  tasks:
    # 任务1: 上传文件到服务器（预压缩，不解压）
    - name: upload_data
      type: transfer
      host: file_server
      direction: local_to_remote
      pre_compress: true
      decompress: false  # 保留压缩文件
      params:
        items:
          - local: ./data
            remote: /www/downloads

    # 任务2: 使用任务1导出的变量
    - name: download_on_target
      type: command
      executor: ssh
      host: target_machine
      command_template: |
        # 使用前置任务导出的变量
        wget http://file_server/downloads/{{ upload_data.archive_name }}
        tar -xzf {{ upload_data.archive_name }}
```

## 配置说明

### 全局配置

```yaml
# 通知配置（可选）
notifier:
  api_url: "https://your-notification-api.com"
  timeout: 10
  verify_ssl: false

# 日志配置
logger:
  log_dir: logs
  level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# 任务默认配置
tasks:
  command_timeout: 3600  # 命令默认超时（秒）
  local_shell: "/bin/bash"  # 本地命令默认shell
  transfer:
    timeout: 600  # 传输默认超时（秒）
    show_progress: true
    compress: true
    preserve_times: true
```

### 任务通知

每个任务可以配置独立的成功/失败通知:

```yaml
- name: critical_task
  type: command
  executor: ssh
  host: server1
  command: "python important_script.py"
  notify_on_success: true
  notify_on_failure: true
  notification:
    success:
      title: "重要任务完成"
      message: "任务执行成功"
    failure:
      title: "重要任务失败"
      message: "请检查日志"
```

## 扩展开发

### 自定义任务类型

```python
from workflow_engine.tasks import Task, TaskFactory
from typing import Tuple

class MyCustomTask(Task):
    """自定义任务"""

    def execute(self) -> Tuple[bool, str]:
        """执行任务逻辑"""
        self.logger.info(f"执行自定义任务: {self.name}")

        # 获取配置参数
        param1 = self.get_param('param1')

        # 执行自定义逻辑
        # ...

        return True, "任务执行成功"

    def export_context(self) -> dict:
        """导出变量供后续任务使用"""
        return {
            'result': 'some_value',
            'timestamp': '2025-11-29'
        }

# 注册任务类型
TaskFactory.register('my_custom', MyCustomTask)
```

然后在配置文件中使用:

```yaml
workflow:
  tasks:
    - name: custom_job
      type: my_custom
      params:
        param1: value1
```

## 更多示例

查看 `examples/` 目录:
- `basic_workflow.yaml` - 基础工作流
- `run_basic.py` - 运行示例

## 系统要求

- Python 3.6+
- rsync（用于文件传输，可选）
- SSH 配置（~/.ssh/config）

## 发布到 PyPI

如果你 fork 了这个项目并想发布自己的版本，按照以下步骤操作：

### 1. 准备工作

```bash
# 安装构建工具
uv pip install build twine setuptools wheel

# 更新版本号
# 编辑 pyproject.toml 和 workflow_engine/__init__.py 中的版本号
```

### 2. 构建分发包

```bash
# 清理旧的构建文件
rm -rf dist/ build/ *.egg-info/

# 构建
python -m build --no-isolation

# 验证构建结果
python -m twine check dist/*
```

### 3. 注册 PyPI 账号

- 正式环境：https://pypi.org/account/register/
- 测试环境：https://test.pypi.org/account/register/

### 4. 配置 API Token

1. 登录 PyPI，进入 Account Settings → API tokens
2. 创建 API token 并保存
3. 配置 `~/.pypirc`：

```bash
cat > ~/.pypirc << 'EOF'
[pypi]
  username = __token__
  password = pypi-你的API-token

[testpypi]
  username = __token__
  password = pypi-你的TestPyPI-token
EOF

chmod 600 ~/.pypirc
```

### 5. 先上传到 TestPyPI（推荐）

```bash
# 上传到测试环境
python -m twine upload --repository testpypi dist/*

# 测试安装
pip install --index-url https://test.pypi.org/simple/ yawe
```

### 6. 上传到正式 PyPI

```bash
# 确认测试无误后上传
python -m twine upload dist/*

# 等待几分钟后测试安装
pip install yawe
```

### 7. 验证发布

```bash
# 验证导入
python -c "from workflow_engine import WorkflowEngine, Config, Logger; print('Success!')"
```

发布成功后，项目将出现在：https://pypi.org/project/yawe/

## License

MIT License - 详见 LICENSE 文件

## 贡献

欢迎提交 Issue 和 Pull Request!
