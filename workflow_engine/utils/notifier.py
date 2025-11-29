"""
通知发送器模块

通过HTTP API发送通知消息。
"""

import json
import requests
from datetime import datetime
from typing import Optional

# 为了避免循环导入，使用Optional类型
try:
    from logger import Logger
except ImportError:
    Logger = None


class Notifier:
    """通知发送器"""
    
    def __init__(
        self, 
        api_url: str, 
        logger: Optional['Logger'] = None,
        timeout: int = 10,
        verify_ssl: bool = False
    ):
        """
        初始化通知发送器
        
        Args:
            api_url: 通知API的URL
            logger: 日志记录器实例
            timeout: 请求超时时间（秒）
            verify_ssl: 是否验证SSL证书
        """
        self.api_url = api_url
        self.logger = logger
        self.timeout = timeout
        self.verify_ssl = verify_ssl
    
    def send_notification(
        self, 
        title: Optional[str] = None,
        body: Optional[str] = None,
        description: Optional[str] = None,
        extra_data: Optional[dict] = None
    ) -> bool:
        """
        发送通知
        
        Args:
            title: 通知标题，默认为当前日期
            body: 通知正文
            description: 通知详情
            extra_data: 额外的数据字典
            
        Returns:
            发送是否成功
        """
        # 设置默认值
        if title is None:
            title = f"{datetime.now().strftime('%Y-%m-%d')} - title"
        if body is None:
            body = "body"
        if description is None:
            description = "description"
        
        if self.logger:
            self.logger.info(f"发送通知: {title}")
        
        # 构建payload
        payload = {
            "title": title,
            "body": body,
            "description": description
        }
        
        # 添加额外数据
        if extra_data:
            payload.update(extra_data)
        
        try:
            response = requests.post(
                self.api_url,
                headers={"Content-Type": "application/json; charset=utf-8"},
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                if self.logger:
                    self.logger.info("通知发送成功")
                return True
            else:
                if self.logger:
                    self.logger.warning(
                        f"通知发送失败: HTTP {response.status_code}, "
                        f"响应: {response.text[:200]}"
                    )
                return False
                
        except requests.exceptions.Timeout:
            error_msg = f"通知发送超时（超过{self.timeout}秒）"
            if self.logger:
                self.logger.error(error_msg)
            return False
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"通知发送连接错误: {str(e)}"
            if self.logger:
                self.logger.error(error_msg)
            return False
            
        except Exception as e:
            error_msg = f"通知发送异常: {str(e)}"
            if self.logger:
                self.logger.error(error_msg)
            return False
    
    def send_success(
        self, 
        task_name: str,
        details: Optional[str] = None
    ) -> bool:
        """
        发送成功通知（快捷方法）
        
        Args:
            task_name: 任务名称
            details: 详细信息
            
        Returns:
            发送是否成功
        """
        return self.send_notification(
            title=f"{task_name}成功",
            body=f"{task_name}执行成功",
            description=details or f"{task_name}执行完成"
        )
    
    def send_failure(
        self, 
        task_name: str,
        error_msg: Optional[str] = None,
        retry_info: Optional[str] = None
    ) -> bool:
        """
        发送失败通知（快捷方法）
        
        Args:
            task_name: 任务名称
            error_msg: 错误信息
            retry_info: 重试信息
            
        Returns:
            发送是否成功
        """
        body = f"{task_name}执行失败"
        if retry_info:
            body += f"，{retry_info}"
        
        description = error_msg or f"{task_name}执行失败"
        if retry_info:
            description += f"，{retry_info}"
        
        return self.send_notification(
            title=f"{task_name}失败",
            body=body,
            description=description
        )
    
    def send_warning(
        self, 
        task_name: str,
        warning_msg: str
    ) -> bool:
        """
        发送警告通知（快捷方法）
        
        Args:
            task_name: 任务名称
            warning_msg: 警告信息
            
        Returns:
            发送是否成功
        """
        return self.send_notification(
            title=f"{task_name}警告",
            body=warning_msg,
            description=warning_msg
        )
    
    def set_api_url(self, api_url: str):
        """
        动态设置API URL
        
        Args:
            api_url: 新的API URL
        """
        self.api_url = api_url
        if self.logger:
            self.logger.debug(f"更新通知API URL: {api_url}")


# 使用示例
if __name__ == "__main__":
    # 不使用logger
    notifier = Notifier(
        api_url="https://reminderapi.joyslinktech.com/v1/push/key/YOUR_KEY"
    )
    
    # 基础发送
    success = notifier.send_notification(
        title="测试通知",
        body="这是一条测试消息",
        description="测试Python重写的通知功能"
    )
    print(f"发送结果: {'成功' if success else '失败'}")
    
    # 快捷方法
    notifier.send_success("数据同步", "成功同步1000条记录")
    notifier.send_failure("模型训练", "内存不足", "将在10分钟后重试")
    notifier.send_warning("磁盘空间", "剩余空间不足20%")
    
    # 带logger使用
    try:
        from logger import Logger
        logger = Logger()
        
        notifier_with_log = Notifier(
            api_url="https://reminderapi.joyslinktech.com/v1/push/key/YOUR_KEY",
            logger=logger
        )
        
        notifier_with_log.send_notification(
            title="带日志的通知",
            body="这条通知会记录到日志"
        )
    except ImportError:
        print("Logger模块未找到，跳过带日志的示例")
    
    # 带额外数据
    notifier.send_notification(
        title="完整示例",
        body="包含额外数据",
        description="演示完整功能",
        extra_data={
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "status": "completed"
        }
    )