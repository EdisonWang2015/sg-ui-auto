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
    original_device_id: str = ""         # 原始设备ID（用于追溯）

    # 新增：清理信息字段
    cleanup_executed: bool = False       # 是否执行了清理
    cleanup_success: bool = True         # 清理是否成功
    cleanup_time: float = 0.0            # 清理耗时（秒）
    cleanup_warnings: List[str] = field(default_factory=list)  # 清理警告信息

    # 新增：执行日志字段
    execution_log: List[Dict[str, str]] = field(default_factory=list)  # 执行日志


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


class TestLogger:
    """测试执行日志记录器"""

    def __init__(self, test_id: str):
        """
        初始化日志记录器

        Args:
            test_id: 测试用例ID
        """
        self.test_id = test_id
        self.logs = []
        self.start_time = time.time()

    def log(self, level: str, message: str):
        """
        记录日志

        Args:
            level: 日志级别 (INFO, DEBUG, WARNING, ERROR, AI)
            message: 日志消息
        """
        elapsed = time.time() - self.start_time
        timestamp = time.strftime("%H:%M:%S", time.localtime(self.start_time + elapsed))
        self.logs.append({
            "timestamp": timestamp,
            "elapsed": f"{elapsed:.2f}s",
            "level": level,
            "message": message
        })

    def info(self, message: str):
        """记录INFO级别日志"""
        self.log("INFO", message)

    def debug(self, message: str):
        """记录DEBUG级别日志"""
        self.log("DEBUG", message)

    def warning(self, message: str):
        """记录WARNING级别日志"""
        self.log("WARNING", message)

    def error(self, message: str):
        """记录ERROR级别日志"""
        self.log("ERROR", message)

    def ai_interaction(self, message: str):
        """记录AI交互日志"""
        self.log("AI", message)

    def get_logs(self) -> List[Dict[str, str]]:
        """获取所有日志"""
        return self.logs


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
        self._lock = threading.Lock()  # 用于agent_pool的线程安全
        # 设备级锁字典，每个设备独立锁，支持真正的并发执行
        self._device_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # 用于device_locks的线程安全

        # 新增：清理管理器
        from state_cleanup import StateCleanupManager
        self.cleanup_manager = StateCleanupManager(config.cleanup)

    def _get_agent(self, device_id: str) -> PhoneAgent:
        """
        获取或创建Agent实例（支持复用和设备级并发）

        Args:
            device_id: 设备ID

        Returns:
            PhoneAgent实例
        """
        # 确保设备有对应的锁
        if device_id not in self._device_locks:
            with self._locks_lock:
                self._device_locks.setdefault(device_id, threading.Lock())

        # 使用设备级锁而不是全局锁，支持不同设备并发访问
        device_lock = self._device_locks[device_id]

        with device_lock:
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

        # 保存原始设备ID（用于追溯）
        original_device_id = test_case.device_id

        # 创建日志记录器
        logger = TestLogger(test_case.test_id)
        logger.info(f"开始执行测试: {test_case.name} ({test_case.test_id})")
        logger.info(f"测试类型: {test_case.type}, 优先级: {test_case.priority}")
        logger.info(f"标签: {','.join(test_case.tags)}")
        logger.info(f"设备: {test_case.device_id}, 超时: {test_case.timeout}秒")

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

        # ========== 前置清理 ==========
        cleanup_executed = False
        cleanup_success = True
        cleanup_time = 0.0
        cleanup_warnings = []

        if self.cleanup_manager.should_cleanup_before(test_case, test_case.device_id):
            if progress_callback:
                progress_callback(test_case.test_id, "执行状态清理")

            logger.info("开始执行状态清理")
            agent = self._get_agent(test_case.device_id)

            # 获取当前应用（用于应用特定配置）
            try:
                from phone_agent.device_factory import get_device_factory
                device_factory = get_device_factory()
                current_app = device_factory.get_current_app(test_case.device_id)
                app_name = getattr(current_app, 'package_name', None)
                logger.debug(f"检测到当前应用: {app_name or '未知'}")
            except Exception as e:
                app_name = None
                logger.warning(f"无法获取当前应用: {str(e)}")

            # 获取并执行清理步骤
            cleanup_steps = self.cleanup_manager.get_cleanup_steps(test_case, app_name)
            logger.info(f"清理策略: {test_case.cleanup_strategy or '默认'}, 步骤数: {len(cleanup_steps)}")

            if cleanup_steps:
                print(f"[清理] 执行 {len(cleanup_steps)} 个清理步骤")
                cleanup_result = self.cleanup_manager.execute_cleanup(
                    agent=agent,
                    device_id=test_case.device_id,
                    cleanup_steps=cleanup_steps,
                    test_id=test_case.test_id
                )

                cleanup_executed = True
                cleanup_success = cleanup_result.success
                cleanup_time = cleanup_result.execution_time
                cleanup_warnings = cleanup_result.warnings

                logger.info(f"清理执行完成, 耗时: {cleanup_time:.2f}秒, 成功: {cleanup_success}")

                # 处理清理失败
                if not cleanup_result.success:
                    logger.error(f"状态清理失败: {cleanup_result.error_message}")
                    if self.config.cleanup.failure_mode == "error":
                        if progress_callback:
                            progress_callback(test_case.test_id, f"状态清理失败")
                        return ExecutionResult(
                            test_id=test_case.test_id,
                            test_name=test_case.name,
                            status="ERROR",
                            execution_time=time.time() - start_time,
                            start_time=start_time_str,
                            end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                            device_id=test_case.device_id,
                            original_device_id=original_device_id,
                            error_message=f"状态清理失败: {cleanup_result.error_message}",
                            cleanup_executed=cleanup_executed,
                            cleanup_success=cleanup_success,
                            cleanup_time=cleanup_time,
                            cleanup_warnings=cleanup_warnings,
                            execution_log=logger.get_logs()
                        )
                    # warn/ignore 模式记录警告但继续
                    for warning in cleanup_warnings:
                        logger.warning(f"清理警告: {warning}")
                        print(f"[WARNING] {warning}")

        try:
            # 构造任务描述
            task_description = test_case.task_command
            if test_case.test_data:
                # 将测试数据作为上下文信息附加
                data_str = ", ".join([f"{k}:{v}" for k, v in test_case.test_data.items()])
                task_description = f"[测试数据参考: {data_str}] 任务: {test_case.task_command}"

            logger.info(f"任务描述: {task_description[:100]}{'...' if len(task_description) > 100 else ''}")
            logger.ai_interaction(f"发送任务给AutoGLM: {task_description[:200]}")

            # 获取Agent实例
            agent = self._get_agent(test_case.device_id)
            logger.debug(f"已获取Agent实例 (设备: {test_case.device_id})")

            # 设置超时执行
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"测试超时（超过{test_case.timeout}秒）")

            # 注意：Windows不支持signal.alarm，这里使用线程方式实现超时
            result_container = {"result": None, "error": None, "finished": False, "output": ""}

            def run_agent():
                try:
                    logger.debug("Agent开始执行任务")
                    print(f"[DEBUG] Agent开始执行: {task_description[:50]}...")

                    # 使用OutputCapture捕获Agent的输出
                    capture = OutputCapture()
                    capture.start()

                    try:
                        result = agent.run(task_description)
                        result_container["result"] = result
                        result_container["finished"] = True

                        # 获取捕获的输出
                        captured_output = capture.stop()
                        result_container["output"] = captured_output

                        logger.ai_interaction(f"AutoGLM响应: {result[:100] if result else 'None'}{'...' if result and len(result) > 100 else ''}")
                        logger.debug(f"Agent执行完成, 步数: {agent.step_count}")
                        print(f"[DEBUG] Agent执行完成，结果: {result[:50] if result else 'None'}...")
                    except Exception as e:
                        capture.stop()
                        raise

                except Exception as e:
                    result_container["error"] = str(e)
                    result_container["finished"] = True
                    import traceback
                    result_container["traceback"] = traceback.format_exc()
                    logger.error(f"Agent执行异常: {str(e)}")
                    print(f"[DEBUG] Agent执行异常: {str(e)}")

            # 使用线程实现超时控制
            thread = threading.Thread(target=run_agent)
            thread.daemon = True  # 使用守护线程，确保主线程退出时子线程也会终止
            thread.start()

            # 等待线程完成或超时
            thread.join(timeout=test_case.timeout)

            print(f"[DEBUG] 线程join结束，is_alive={thread.is_alive()}, finished={result_container.get('finished')}")

            if thread.is_alive():
                # 线程仍在运行，表示超时
                logger.error(f"执行超时（超过{test_case.timeout}秒）")
                logger.warning(f"Agent线程仍在运行，已标记为守护线程，将在主线程退出时自动终止")

                # 重置Agent状态，清理可能正在进行的操作
                try:
                    logger.debug(f"尝试重置Agent状态 (设备: {test_case.device_id})")
                    self.reset_agent(test_case.device_id)
                    logger.info(f"Agent状态已重置")
                except Exception as e:
                    logger.error(f"重置Agent状态失败: {str(e)}")

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
                    original_device_id=original_device_id,
                    error_message=f"执行超过{test_case.timeout}秒",
                    cleanup_executed=cleanup_executed,
                    cleanup_success=cleanup_success,
                    cleanup_time=cleanup_time,
                    cleanup_warnings=cleanup_warnings,
                    execution_log=logger.get_logs()
                )

            if result_container["error"]:
                logger.error(f"执行错误: {result_container['error']}")
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
                    original_device_id=original_device_id,
                    error_message=result_container["error"],
                    output=result_container.get("traceback", ""),
                    cleanup_executed=cleanup_executed,
                    cleanup_success=cleanup_success,
                    cleanup_time=cleanup_time,
                    cleanup_warnings=cleanup_warnings,
                    execution_log=logger.get_logs()
                )

            # 成功执行
            logger.info(f"测试执行完成, 总耗时: {time.time() - start_time:.2f}秒")
            if progress_callback:
                progress_callback(test_case.test_id, "执行完成")

            execution_time = time.time() - start_time

            # 记录Agent输出
            if result_container.get("output"):
                logger.debug(f"Agent输出: {result_container['output'][:200]}{'...' if len(result_container['output']) > 200 else ''}")

            return ExecutionResult(
                test_id=test_case.test_id,
                test_name=test_case.name,
                status="COMPLETED",
                execution_time=execution_time,
                start_time=start_time_str,
                end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                device_id=test_case.device_id,
                original_device_id=original_device_id,
                output=result_container["result"] if result_container["result"] else f"执行成功，步数: {agent.step_count}",
                output_preview=result_container["result"][:100] if result_container["result"] else f"执行成功，步数: {agent.step_count}",
                steps_taken=agent.step_count,
                cleanup_executed=cleanup_executed,
                cleanup_success=cleanup_success,
                cleanup_time=cleanup_time,
                cleanup_warnings=cleanup_warnings,
                execution_log=logger.get_logs()
            )

        except Exception as e:
            logger.error(f"测试异常: {str(e)}")
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
                original_device_id=original_device_id,
                error_message=str(e),
                cleanup_executed=cleanup_executed,
                cleanup_success=cleanup_success,
                cleanup_time=cleanup_time,
                cleanup_warnings=cleanup_warnings,
                execution_log=logger.get_logs()
            )

    def execute_batch(
        self,
        test_cases: List[APITestCase],
        max_workers: int = 1,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> List[ExecutionResult]:
        """
        批量执行测试用例（支持真正的并发执行）

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
            # 【关键修改】不再按设备分组，直接提交所有用例到线程池
            # 这样可以实现真正的跨设备并发执行
            print(f"\n[并发执行] 提交 {len(test_cases)} 个任务到线程池（max_workers={max_workers}）")

            # 统计每个设备的任务数
            device_task_count = {}
            for tc in test_cases:
                device_task_count[tc.device_id] = device_task_count.get(tc.device_id, 0) + 1

            print(f"[任务分配] 按设备统计:")
            for device_id, count in device_task_count.items():
                print(f"  - {device_id}: {count} 个任务")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                submitted_count = 0

                # 直接提交所有用例到线程池
                for tc in test_cases:
                    print(f"[提交任务] {tc.test_id} -> 设备 {tc.device_id}")
                    future = executor.submit(self.execute_test_case, tc, progress_callback)
                    futures[future] = tc
                    submitted_count += 1

                print(f"[并发执行] 已提交 {submitted_count} 个任务")

                # 收集结果
                completed_count = 0
                for future in as_completed(futures):
                    try:
                        # 获取对应的测试用例
                        test_case = futures[future]

                        result = future.result()
                        results.append(result)
                        completed_count += 1

                        # 失败处理逻辑（支持多种策略）
                        if result.status in ["ERROR", "TIMEOUT"]:
                            # 获取失败策略（默认从配置读取，可扩展为命令行参数）
                            failure_strategy = getattr(self.config.execution, 'failure_strategy', 'stop_all')

                            if failure_strategy == "stop_all":
                                # 停止所有任务
                                for f in futures:
                                    if not f.done():
                                        f.cancel()
                                print(f"\n测试失败（策略: stop_all），停止所有执行")
                                break
                            elif failure_strategy == "stop_device":
                                # 取消同一设备的剩余任务
                                device_id = result.device_id
                                for f, tc in futures.items():
                                    if tc.device_id == device_id and not f.done():
                                        f.cancel()
                                print(f"\n设备 {device_id} 测试失败（策略: stop_device），停止该设备剩余任务")
                            # "continue" 策略不做任何处理，继续执行
                    except Exception as e:
                        # 捕获future.result()可能抛出的异常
                        test_case = futures.get(future)
                        test_id = test_case.test_id if test_case else "UNKNOWN"
                        test_name = test_case.name if test_case else "Unknown Test"

                        print(f"\n[错误] 测试用例 {test_id} 获取结果异常: {str(e)}")

                        # 创建一个ERROR状态的ExecutionResult
                        import traceback
                        error_result = ExecutionResult(
                            test_id=test_id,
                            test_name=test_name,
                            status="ERROR",
                            execution_time=0,
                            start_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                            end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                            device_id=test_case.device_id if test_case else "UNKNOWN",
                            error_message=f"获取结果异常: {str(e)}",
                            execution_log=[]
                        )
                        results.append(error_result)

                print(f"\n[并发执行] 已完成 {completed_count}/{submitted_count} 个任务")

                # 检查是否有未完成的任务
                for future, tc in futures.items():
                    if not future.done():
                        print(f"[警告] 测试用例 {tc.test_id} 未完成，可能被取消或仍在运行")

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
