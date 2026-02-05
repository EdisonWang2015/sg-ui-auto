#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API执行引擎
直接调用PhoneAgent API，避免使用subprocess
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from io import StringIO
import sys

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

from test_config import TestFrameworkConfig, APIConfig, AgentConfig as TestAgentConfig
from csv_case_manager import APITestCase
from adb_lock import ADBLockManager, get_adb_lock_manager


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

    # 新增：AI 思考过程字段
    thinking_process: List[Dict[str, Any]] = field(default_factory=list)  # AI 每步的思考过程


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

    def __init__(self, config: TestFrameworkConfig, device_service=None):
        """
        初始化API执行引擎

        Args:
            config: 测试框架配置
            device_service: DeviceService 实例（可选，用于依赖注入）
        """
        self.config = config
        self.device_service = device_service

        # 使用 AgentPoolManager 管理 Agent 生命周期
        from agent_pool_manager import AgentPoolManager
        self.agent_pool_manager = AgentPoolManager(config)

        # 新增：ADB 锁管理器（防止并发 ADB 调用冲突）
        self.adb_lock_manager = get_adb_lock_manager()
        self._adb_lock_enabled = getattr(config.execution, 'adb_lock_enabled', True)

        # 新增：清理管理器（传入 device_service）
        from state_cleanup import StateCleanupManager
        self.cleanup_manager = StateCleanupManager(config.cleanup, device_service)

    def _get_device_service(self):
        """获取 DeviceService（延迟加载）"""
        if self.device_service is None:
            from device_service import DeviceService
            self.device_service = DeviceService(self.config)
        return self.device_service

    def _infer_target_app_name(self, test_case: APITestCase) -> Optional[str]:
        """从测试描述中推断目标应用名称（用于前置复位）"""
        try:
            from phone_agent.config.apps import APP_PACKAGES
        except Exception:
            return None

        text = f"{test_case.preconditions or ''} {test_case.task_command or ''}"
        if not text.strip():
            return None

        candidates = [name for name in APP_PACKAGES.keys() if name in text]
        if not candidates:
            return None

        # 选择最长匹配（避免子串误匹配）
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    def _is_system_package(self, package_name: str, system_packages: List[str]) -> bool:
        """判断是否为系统包（避免误杀桌面/系统UI）"""
        if not package_name:
            return True
        for pkg in system_packages:
            if package_name == pkg or package_name.startswith(pkg):
                return True
        return False

    def _preflight_prepare_device(
        self, test_case: APITestCase, logger: TestLogger
    ) -> Tuple[bool, str]:
        """用例前置复位：回桌面、清理干扰App、启动目标App并验证前台"""
        preflight = getattr(self.config, "preflight", None)
        if not preflight or not preflight.enabled:
            return True, ""

        device_id = test_case.device_id
        device_service = self._get_device_service()

        try:
            from phone_agent.device_factory import get_device_factory
            device_factory = get_device_factory()
        except Exception as e:
            return False, f"获取设备工厂失败: {str(e)}"

        # 目标应用名/包名
        target_app_name = preflight.target_app_name or self._infer_target_app_name(test_case)
        target_package = preflight.target_package
        if target_app_name and not target_package:
            try:
                from phone_agent.config.apps import APP_PACKAGES
                target_package = APP_PACKAGES.get(target_app_name)
            except Exception:
                target_package = None

        logger.info(
            f"前置复位: target_app_name={target_app_name or '未识别'} "
            f"target_package={target_package or '未知'}"
        )

        # 回桌面
        if preflight.home_before_start:
            try:
                device_factory.home(device_id)
                time.sleep(0.5)
            except Exception as e:
                return False, f"回桌面失败: {str(e)}"

        # 强杀当前前台（非系统）
        if preflight.force_stop_foreground:
            try:
                current_pkg = device_service.get_current_app(device_id)
                if current_pkg and not self._is_system_package(current_pkg, preflight.system_packages):
                    if target_package and current_pkg == target_package and not preflight.always_force_stop_target:
                        pass
                    else:
                        device_service.force_stop_app(device_id, current_pkg)
                        logger.info(f"前置复位: 已强杀前台应用 {current_pkg}")
            except Exception as e:
                logger.warning(f"前置复位: 获取/强杀前台应用失败: {str(e)}")

        # 强杀黑名单应用
        for pkg in preflight.blacklisted_packages:
            try:
                device_service.force_stop_app(device_id, pkg)
            except Exception:
                # 黑名单非关键路径
                pass

        # 强制停止目标应用
        if preflight.always_force_stop_target and target_package:
            try:
                device_service.force_stop_app(device_id, target_package)
            except Exception as e:
                logger.warning(f"前置复位: 强杀目标应用失败: {str(e)}")

        # 启动目标应用
        if target_app_name:
            launched = device_factory.launch_app(target_app_name, device_id)
            if not launched:
                return False, f"启动目标应用失败: {target_app_name}"
            if preflight.wait_after_launch > 0:
                time.sleep(preflight.wait_after_launch)
        else:
            logger.warning("前置复位: 未识别目标应用，跳过启动步骤")

        # 验证前台应用
        if preflight.verify_foreground and target_package:
            start_time = time.time()
            while time.time() - start_time < preflight.verify_timeout:
                current_pkg = device_service.get_current_app(device_id)
                if current_pkg == target_package:
                    return True, ""
                time.sleep(0.5)
            return False, f"前置复位超时：前台应用非目标应用 ({current_pkg})"

        return True, ""

    def _get_agent(self, device_id: str) -> PhoneAgent:
        """
        获取或创建Agent实例（支持复用和设备级并发）

        Args:
            device_id: 设备ID

        Returns:
            PhoneAgent实例
        """
        return self.agent_pool_manager.get_agent(device_id)

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

        # ========== 前置复位（确保稳定入口） ==========
        try:
            preflight_ok, preflight_error = self._preflight_prepare_device(test_case, logger)
            if not preflight_ok:
                logger.error(f"前置复位失败: {preflight_error}")
                if getattr(self.config.preflight, "fail_on_preflight_error", True):
                    if progress_callback:
                        progress_callback(test_case.test_id, "前置复位失败")
                    return ExecutionResult(
                        test_id=test_case.test_id,
                        test_name=test_case.name,
                        status="ERROR",
                        execution_time=time.time() - start_time,
                        start_time=start_time_str,
                        end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                        device_id=test_case.device_id,
                        original_device_id=original_device_id,
                        error_message=f"前置复位失败: {preflight_error}",
                        cleanup_executed=cleanup_executed,
                        cleanup_success=cleanup_success,
                        cleanup_time=cleanup_time,
                        cleanup_warnings=cleanup_warnings,
                        execution_log=logger.get_logs()
                    )
        except Exception as e:
            logger.error(f"前置复位异常: {str(e)}")
            if getattr(self.config.preflight, "fail_on_preflight_error", True):
                if progress_callback:
                    progress_callback(test_case.test_id, "前置复位异常")
                return ExecutionResult(
                    test_id=test_case.test_id,
                    test_name=test_case.name,
                    status="ERROR",
                    execution_time=time.time() - start_time,
                    start_time=start_time_str,
                    end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                    device_id=test_case.device_id,
                    original_device_id=original_device_id,
                    error_message=f"前置复位异常: {str(e)}",
                    cleanup_executed=cleanup_executed,
                    cleanup_success=cleanup_success,
                    cleanup_time=cleanup_time,
                    cleanup_warnings=cleanup_warnings,
                    execution_log=logger.get_logs()
                )

        try:
            # 构造任务描述
            task_description = test_case.task_command
            if test_case.test_data:
                # 将测试数据作为上下文信息附加
                data_str = ", ".join([f"{k}:{v}" for k, v in test_case.test_data.items()])
                task_description = f"[测试数据参考: {data_str}] 任务: {test_case.task_command}"

            logger.info(f"任务描述: {task_description}")
            logger.ai_interaction(f"发送任务给AutoGLM: {task_description}")

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
                # 获取设备级ADB锁（防止同一设备的并发ADB调用冲突）
                # 【方案二改进】不同设备使用独立的锁，可以实现真正的跨设备并发
                adb_lock = None
                if self._adb_lock_enabled:
                    device_lock_name = f"device_{test_case.device_id}"
                    adb_lock = self.adb_lock_manager.get_lock(device_lock_name)
                    lock_time = time.strftime("%H:%M:%S", time.localtime())
                    print(f"[{lock_time}] [设备锁] {test_case.test_id} 等待设备锁: {device_lock_name}")
                    logger.debug(f"获取设备级ADB锁: {device_lock_name}")
                    try:
                        adb_lock.acquire(timeout=60)
                        lock_acquired_time = time.strftime("%H:%M:%S", time.localtime())
                        print(f"[{lock_acquired_time}] [设备锁] {test_case.test_id} 成功获取锁: {device_lock_name}")
                        logger.debug(f"成功获取设备锁: {device_lock_name}")
                    except TimeoutError as e:
                        logger.error(f"获取设备级ADB锁超时 ({device_lock_name}): {e}")
                        result_container["error"] = f"获取设备级ADB锁超时 ({device_lock_name}): {str(e)}"
                        result_container["finished"] = True
                        return

                try:
                    logger.debug("Agent开始执行任务")
                    print(f"[DEBUG] Agent开始执行: {task_description[:50]}...")

                    # 收集 AI 思考过程
                    thinking_steps = []

                    # 使用 step() 逐步执行以收集思考过程
                    step_num = 0
                    final_result = None

                    # 单步超时时间（从配置读取或使用默认值）
                    step_timeout = getattr(self.config.agent, 'step_timeout', 60)  # 每步最多60秒

                    while True:
                        # 为每个 step() 调用添加超时控制
                        step_result = None
                        step_timeout_occurred = False

                        try:
                            # 使用 ThreadPoolExecutor 为单个 step() 调用添加超时
                            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

                            with ThreadPoolExecutor(max_workers=1) as step_executor:
                                step_future = step_executor.submit(
                                    agent.step,
                                    task_description if step_num == 0 else None
                                )

                                try:
                                    step_result = step_future.result(timeout=step_timeout)
                                except FutureTimeoutError:
                                    step_timeout_occurred = True
                                    logger.error(f"步骤 {step_num + 1} 超时（超过{step_timeout}秒）")
                                    print(f"[ERROR] Agent 步骤 {step_num + 1} 超时（超过{step_timeout}秒），尝试恢复...")

                                    # 尝试重置 Agent
                                    try:
                                        agent.reset()
                                        logger.info("Agent 已重置")
                                    except Exception as reset_error:
                                        logger.error(f"重置 Agent 失败: {reset_error}")

                                    # 标记为超时错误
                                    final_result = f"步骤 {step_num + 1} 执行超时（超过{step_timeout}秒）"
                                    break

                        except Exception as step_error:
                            # step() 调用本身抛出异常
                            logger.error(f"步骤 {step_num + 1} 异常: {str(step_error)}")
                            final_result = f"步骤 {step_num + 1} 异常: {str(step_error)}"
                            break

                        # 如果超时，已经在上面的 except 块中处理了
                        if step_timeout_occurred:
                            break

                        if step_result is None:
                            final_result = f"步骤 {step_num + 1} 返回空结果"
                            break

                        if not step_result.success:
                            final_result = f"步骤执行失败: {step_result.message}"
                            break

                        # 记录思考过程
                        if step_result.thinking:
                            thinking_data = {
                                "step": step_num + 1,
                                "thinking": step_result.thinking,
                                "action": step_result.action,
                                "message": step_result.message
                            }
                            thinking_steps.append(thinking_data)

                            # 打印思考过程到控制台
                            print(f"\n{'='*60}")
                            print(f"[AI 思考] 步骤 {step_num + 1}")
                            print(f"{'='*60}")
                            print(f"💭 {step_result.thinking}")
                            if step_result.action:
                                print(f"\n[动作] {step_result.action}")
                            if step_result.message:
                                print(f"\n[消息] {step_result.message}")
                            print(f"{'='*60}\n")

                            logger.ai_interaction(f"步骤 {step_num + 1} 思考: {step_result.thinking}")

                        step_num += 1

                        if step_result.finished:
                            final_result = step_result.message or "任务完成"
                            break

                        if step_num >= self.config.agent.max_steps:
                            final_result = f"达到最大步数 ({self.config.agent.max_steps})"
                            break

                    result_container["result"] = final_result
                    result_container["finished"] = True
                    result_container["thinking_steps"] = thinking_steps
                    result_container["steps_taken"] = step_num

                    logger.ai_interaction(f"AutoGLM响应: {final_result if final_result else 'None'}")
                    logger.debug(f"Agent执行完成, 步数: {step_num}")
                    print(f"[DEBUG] Agent执行完成，结果: {final_result[:50] if final_result else 'None'}...")

                except Exception as e:
                    result_container["error"] = str(e)
                    result_container["finished"] = True
                    import traceback
                    result_container["traceback"] = traceback.format_exc()
                    logger.error(f"Agent执行异常: {str(e)}")
                    print(f"[DEBUG] Agent执行异常: {str(e)}")

                finally:
                    # 释放设备级ADB锁
                    if adb_lock is not None:
                        lock_release_time = time.strftime("%H:%M:%S", time.localtime())
                        print(f"[{lock_release_time}] [设备锁] {test_case.test_id} 释放锁: {device_lock_name}")
                        adb_lock.release()

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
                    execution_log=logger.get_logs(),
                    thinking_process=result_container.get("thinking_steps", [])
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
                    execution_log=logger.get_logs(),
                    thinking_process=result_container.get("thinking_steps", [])
                )

            # 成功执行
            logger.info(f"测试执行完成, 总耗时: {time.time() - start_time:.2f}秒")
            if progress_callback:
                progress_callback(test_case.test_id, "执行完成")

            execution_time = time.time() - start_time

            # 记录Agent输出
            if result_container.get("output"):
                logger.debug(f"Agent输出: {result_container['output']}")

            steps_taken = result_container.get("steps_taken", agent.step_count)

            return ExecutionResult(
                test_id=test_case.test_id,
                test_name=test_case.name,
                status="COMPLETED",
                execution_time=execution_time,
                start_time=start_time_str,
                end_time=time.strftime("%Y-%m-%d %H:%M:%S"),
                device_id=test_case.device_id,
                original_device_id=original_device_id,
                output=result_container["result"] if result_container["result"] else f"执行成功，步数: {steps_taken}",
                output_preview=result_container["result"][:100] if result_container["result"] else f"执行成功，步数: {steps_taken}",
                steps_taken=steps_taken,
                cleanup_executed=cleanup_executed,
                cleanup_success=cleanup_success,
                cleanup_time=cleanup_time,
                cleanup_warnings=cleanup_warnings,
                execution_log=logger.get_logs(),
                thinking_process=result_container.get("thinking_steps", [])
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
                execution_log=logger.get_logs(),
                thinking_process=[]
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
            # 【方案二：设备级锁】不再按设备分组，直接提交所有用例到线程池
            # 不同设备使用独立的锁，可以实现真正的跨设备并发执行
            print(f"\n[并发执行] 提交 {len(test_cases)} 个任务到线程池（max_workers={max_workers}）")
            print(f"[并发模式] 设备级ADB锁已启用，不同设备可真正并发")

            # 统计每个设备的任务数
            device_task_count = {}
            for tc in test_cases:
                device_task_count[tc.device_id] = device_task_count.get(tc.device_id, 0) + 1

            print(f"[任务分配] 按设备统计:")
            for device_id, count in device_task_count.items():
                print(f"  - {device_id}: {count} 个任务")

            import time
            batch_start_time = time.time()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                submitted_count = 0

                # 直接提交所有用例到线程池
                for tc in test_cases:
                    submit_time = time.strftime("%H:%M:%S", time.localtime())
                    print(f"[{submit_time}] [提交任务] {tc.test_id} -> 设备 {tc.device_id}")
                    future = executor.submit(self.execute_test_case, tc, progress_callback)
                    futures[future] = tc
                    submitted_count += 1

                print(f"[并发执行] 已提交 {submitted_count} 个任务，开始并发执行...\n")

                # 收集结果
                completed_count = 0
                for future in as_completed(futures):
                    try:
                        # 获取对应的测试用例
                        test_case = futures[future]

                        result = future.result()
                        results.append(result)
                        completed_count += 1

                        # 【并发验证】添加时间戳，观察不同设备的执行时间是否重叠
                        complete_time = time.strftime("%H:%M:%S", time.localtime())
                        elapsed_time = time.time() - batch_start_time
                        print(f"[{complete_time}] [任务完成] {test_case.test_id} -> 设备 {test_case.device_id} | "
                              f"状态: {result.status} | 耗时: {elapsed_time:.1f}s")

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

        try:
            # 创建截图目录
            screenshot_dir = os.path.join(
                self.config.reporting.output_dir,
                "screenshots"
            )
            os.makedirs(screenshot_dir, exist_ok=True)

            # 使用 DeviceService 保存截图
            if self.device_service:
                return self.device_service.save_screenshot(
                    test_case.device_id,
                    screenshot_dir,
                    prefix=test_case.test_id
                )

            # Fallback 到旧方式
            import base64
            from phone_agent.device_factory import get_device_factory

            device_factory = get_device_factory()
            screenshot = device_factory.get_screenshot(test_case.device_id)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{test_case.test_id}_{timestamp}.png"
            screenshot_path = os.path.join(screenshot_dir, filename)

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
        self.agent_pool_manager.reset_agent(device_id)

    def cleanup(self):
        """清理资源"""
        self.agent_pool_manager.cleanup_all()
