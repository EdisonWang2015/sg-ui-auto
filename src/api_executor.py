#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API执行引擎
直接调用PhoneAgent API，避免使用subprocess
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from io import StringIO
import sys

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

from test_config import TestFrameworkConfig, APIConfig, AgentConfig as TestAgentConfig
from csv_case_manager import APITestCase


@dataclass
class ExecutionResult:
    """单个测试用例的执行结果"""
    test_id: str
    test_name: str
    status: str                          # PASS, FAIL, ERROR, TIMEOUT
    execution_time: float                # 执行时间（秒）
    start_time: str                      # 开始时间
    end_time: str                        # 结束时间
    device_id: str
    output: str = ""                     # 完整输出
    output_preview: str = ""             # 输出预览
    error_message: str = ""              # 错误信息
    validation_passed: bool = False      # 验证是否通过
    validation_details: Dict[str, Any] = field(default_factory=dict)
    steps_taken: int = 0                 # 执行步数
    screenshot_path: str = ""            # 失败时的截图路径


class OutputCapture:
    """捕获标准输出的工具类"""

    def __init__(self):
        self._buffer = StringIO()
        self._original_stdout = None

    def start(self):
        """开始捕获输出"""
        self._original_stdout = sys.stdout
        sys.stdout = self._buffer

    def stop(self) -> str:
        """停止捕获并返回捕获的内容"""
        if self._original_stdout:
            sys.stdout = self._original_stdout
            self._original_stdout = None
        return self._buffer.getvalue()

    def get_output(self) -> str:
        """获取当前捕获的内容"""
        return self._buffer.getvalue()


class APIExecutor:
    """API执行引擎 - 直接调用PhoneAgent"""

    def __init__(self, config: TestFrameworkConfig):
        """
        初始化API执行引擎

        Args:
            config: 测试框架配置
        """
        self.config = config
        self._agent_pool: Dict[str, PhoneAgent] = {}
        self._lock = threading.Lock()

    def _get_agent(self, device_id: str) -> PhoneAgent:
        """
        获取或创建Agent实例（支持复用）

        Args:
            device_id: 设备ID

        Returns:
            PhoneAgent实例
        """
        with self._lock:
            if device_id not in self._agent_pool:
                # 创建ModelConfig
                model_config = ModelConfig(
                    base_url=self.config.api.base_url,
                    model_name=self.config.api.model_name,
                    api_key=self.config.api.api_key,
                    lang=self.config.agent.lang
                )

                # 创建AgentConfig
                agent_config = AgentConfig(
                    max_steps=self.config.agent.max_steps,
                    device_id=device_id,
                    verbose=self.config.agent.verbose,
                    lang=self.config.agent.lang
                )

                # 创建PhoneAgent实例
                agent = PhoneAgent(
                    model_config=model_config,
                    agent_config=agent_config
                )

                self._agent_pool[device_id] = agent

            return self._agent_pool[device_id]

    def execute_test_case(
        self,
        test_case: APITestCase,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> ExecutionResult:
        """
        执行单个测试用例

        Args:
            test_case: 测试用例
            progress_callback: 进度回调函数 (test_id, message)

        Returns:
            ExecutionResult
        """
        start_time = time.time()
        start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{'='*60}")
        print(f"执行测试: {test_case.name} ({test_case.test_id})")
        print(f"类型: {test_case.type}")
        print(f"优先级: {test_case.priority}")
        print(f"标签: {','.join(test_case.tags)}")
        print(f"设备: {test_case.device_id}")
        print(f"超时: {test_case.timeout}秒")
        print(f"{'='*60}\n")

        if progress_callback:
            progress_callback(test_case.test_id, "开始执行")

        try:
            # 构造任务描述
            task_description = test_case.task_command
            if test_case.test_data:
                # 将测试数据作为上下文信息附加
                data_str = ", ".join([f"{k}:{v}" for k, v in test_case.test_data.items()])
                task_description = f"[测试数据参考: {data_str}] 任务: {test_case.task_command}"

            # 获取Agent实例
            agent = self._get_agent(test_case.device_id)

            # 设置超时执行
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"测试超时（超过{test_case.timeout}秒）")

            # 注意：Windows不支持signal.alarm，这里使用线程方式实现超时
            result_container = {"result": None, "error": None, "finished": False}

            def run_agent():
                try:
                    print(f"[DEBUG] Agent开始执行: {task_description[:50]}...")
                    # 不捕获输出，让PhoneAgent的输出直接显示
                    result = agent.run(task_description)
                    result_container["result"] = result
                    result_container["finished"] = True
                    print(f"[DEBUG] Agent执行完成，结果: {result[:50] if result else 'None'}...")
                except Exception as e:
                    result_container["error"] = str(e)
                    result_container["finished"] = True
                    import traceback
                    result_container["traceback"] = traceback.format_exc()
                    print(f"[DEBUG] Agent执行异常: {str(e)}")

            # 使用线程实现超时控制
            thread = threading.Thread(target=run_agent)
            thread.daemon = False  # 改为非守护线程
            thread.start()

            # 等待线程完成或超时
            thread.join(timeout=test_case.timeout)

            print(f"[DEBUG] 线程join结束，is_alive={thread.is_alive()}, finished={result_container.get('finished')}")

            if thread.is_alive():
                # 线程仍在运行，表示超时
                if progress_callback:
                    progress_callback(test_case.test_id, "执行超时")
                return ExecutionResult(
                    test_id=test_case.test_id,
                    test_name=test_case.name,
                    status="TIMEOUT",
                    execution_time=time.time() - start_time,
                    start_time=start_time_str,
                    end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                    device_id=test_case.device_id,
                    error_message=f"执行超过{test_case.timeout}秒"
                )

            if result_container["error"]:
                if progress_callback:
                    progress_callback(test_case.test_id, f"执行错误: {result_container['error']}")
                return ExecutionResult(
                    test_id=test_case.test_id,
                    test_name=test_case.name,
                    status="ERROR",
                    execution_time=time.time() - start_time,
                    start_time=start_time_str,
                    end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                    device_id=test_case.device_id,
                    error_message=result_container["error"],
                    output=result_container.get("traceback", "")
                )

            # 成功执行
            if progress_callback:
                progress_callback(test_case.test_id, "执行完成")

            execution_time = time.time() - start_time

            return ExecutionResult(
                test_id=test_case.test_id,
                test_name=test_case.name,
                status="COMPLETED",
                execution_time=execution_time,
                start_time=start_time_str,
                end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                device_id=test_case.device_id,
                output=result_container["result"] if result_container["result"] else f"执行成功，步数: {agent.step_count}",
                output_preview=result_container["result"][:100] if result_container["result"] else f"执行成功，步数: {agent.step_count}",
                steps_taken=agent.step_count
            )

        except Exception as e:
            if progress_callback:
                progress_callback(test_case.test_id, f"异常: {str(e)}")
            return ExecutionResult(
                test_id=test_case.test_id,
                test_name=test_case.name,
                status="ERROR",
                execution_time=time.time() - start_time,
                start_time=start_time_str,
                end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                device_id=test_case.device_id,
                error_message=str(e)
            )

    def execute_batch(
        self,
        test_cases: List[APITestCase],
        max_workers: int = 1,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> List[ExecutionResult]:
        """
        批量执行测试用例（支持并发）

        Args:
            test_cases: 测试用例列表
            max_workers: 最大并发数
            progress_callback: 进度回调函数

        Returns:
            执行结果列表
        """
        results = []

        # 如果只有一个worker或测试用例很少，使用串行执行
        if max_workers <= 1 or len(test_cases) <= 1:
            for test_case in test_cases:
                result = self.execute_test_case(test_case, progress_callback)
                results.append(result)

                # 失败后是否继续
                if result.status in ["ERROR", "TIMEOUT"] and not self.config.execution.continue_on_failure:
                    print(f"\n测试失败，停止执行")
                    break
        else:
            # 使用线程池并发执行（按设备分组，避免设备冲突）
            device_groups: Dict[str, List[APITestCase]] = {}
            for tc in test_cases:
                if tc.device_id not in device_groups:
                    device_groups[tc.device_id] = []
                device_groups[tc.device_id].append(tc)

            # 按设备组并发执行
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for device_id, device_test_cases in device_groups.items():
                    for tc in device_test_cases:
                        future = executor.submit(self.execute_test_case, tc, progress_callback)
                        futures[future] = tc

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)

                    # 失败后是否继续
                    if result.status in ["ERROR", "TIMEOUT"] and not self.config.execution.continue_on_failure:
                        # 取消剩余任务
                        for f in futures:
                            f.cancel()
                        print(f"\n测试失败，停止执行")
                        break

        return results

    def _save_failure_screenshot(self, test_case: APITestCase) -> str:
        """
        保存失败时的截图

        Args:
            test_case: 测试用例

        Returns:
            截图文件路径
        """
        import os
        import base64
        from phone_agent.device_factory import get_device_factory

        try:
            # 创建截图目录
            screenshot_dir = os.path.join(
                self.config.reporting.output_dir,
                "screenshots"
            )
            os.makedirs(screenshot_dir, exist_ok=True)

            # 获取截图
            device_factory = get_device_factory()
            screenshot = device_factory.get_screenshot(test_case.device_id)

            # 保存截图
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{test_case.test_id}_{timestamp}.png"
            screenshot_path = os.path.join(screenshot_dir, filename)

            # 将base64转换为图片并保存
            image_data = base64.b64decode(screenshot.base64_data)
            with open(screenshot_path, 'wb') as f:
                f.write(image_data)

            print(f"已保存失败截图: {screenshot_path}")
            return screenshot_path

        except Exception as e:
            print(f"保存截图失败: {str(e)}")
            return ""

    def reset_agent(self, device_id: str):
        """
        重置指定设备的Agent状态

        Args:
            device_id: 设备ID
        """
        with self._lock:
            if device_id in self._agent_pool:
                self._agent_pool[device_id].reset()

    def cleanup(self):
        """清理资源"""
        with self._lock:
            self._agent_pool.clear()
