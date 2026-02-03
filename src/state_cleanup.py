#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备状态清理模块
确保每个测试用例从干净的状态开始执行
"""

import time
import threading
import subprocess
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class CleanupResult:
    """清理执行结果"""
    success: bool
    steps_completed: int
    steps_total: int
    execution_time: float
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)


class StateCleanupManager:
    """状态清理管理器

    负责在测试用例执行前后清理应用状态，确保每个测试用例从干净状态开始。
    支持全局配置、用例级覆盖、应用特定配置等多个层次的清理策略。
    """

    def __init__(self, config):
        """初始化状态清理管理器

        Args:
            config: CleanupConfig 配置对象
        """
        self.config = config
        self._last_cleanup_time: Dict[str, float] = {}
        self._cleanup_lock: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def _get_device_lock(self, device_id: str) -> threading.Lock:
        """获取设备级锁，确保清理操作的线程安全

        Args:
            device_id: 设备ID

        Returns:
            设备对应的锁对象
        """
        if device_id not in self._cleanup_lock:
            with self._locks_lock:
                self._cleanup_lock.setdefault(device_id, threading.Lock())
        return self._cleanup_lock[device_id]

    def get_cleanup_steps(self, test_case, current_app: Optional[str] = None) -> List[str]:
        """获取测试用例的清理步骤

        根据以下优先级获取清理步骤：
        1. 用例级自定义清理（cleanup_strategy="custom"）
        2. 应用特定配置
        3. 全局默认步骤
        4. 不清理（cleanup_strategy="none"）

        支持的策略：
        - none: 不执行任何清理
        - custom: 用例级自定义清理步骤
        - inherit: 继承全局配置的清理步骤（默认）
        - auto: 自动清理（使用全局配置的步骤）
        - force_restart: 强制重启应用（杀掉进程）

        Args:
            test_case: APITestCase 测试用例对象
            current_app: 当前应用包名（可选）

        Returns:
            清理步骤列表
        """
        strategy = getattr(test_case, 'cleanup_strategy', 'inherit')

        # 策略：不执行任何清理
        if strategy == "none":
            return []

        # 策略：用例级自定义清理
        if strategy == "custom":
            custom_steps = getattr(test_case, 'cleanup_steps', None)
            if custom_steps:
                # 支持字符串或列表格式
                if isinstance(custom_steps, str):
                    return [s.strip() for s in custom_steps.split('||') if s.strip()]
                return custom_steps
            return []

        # 策略：强制重启应用（特殊标记）
        if strategy == "force_restart":
            return ["__FORCE_RESTART__"]

        # 策略：继承全局配置
        if strategy == "inherit" or strategy == "auto":
            # 检查是否启用全局清理
            if not self.config.enabled:
                return []

            # 全局策略为 force_restart
            if self.config.strategy == "force_restart":
                return ["__FORCE_RESTART__"]

            # 应用特定配置优先
            if current_app and current_app in self.config.app_specific:
                return self.config.app_specific[current_app]

            # 全局默认步骤
            return self.config.global_cleanup_steps

        return []

    def should_cleanup_before(self, test_case, device_id: str) -> bool:
        """判断是否应该在用例执行前清理

        Args:
            test_case: APITestCase 测试用例对象
            device_id: 设备ID

        Returns:
            是否应该执行清理
        """
        strategy = getattr(test_case, 'cleanup_strategy', 'inherit')

        # none策略不清理
        if strategy == "none":
            return False

        # inherit/auto策略需要全局启用
        if strategy in ["inherit", "auto"]:
            if not self.config.enabled:
                return False

        # custom策略总是执行
        if strategy == "custom":
            return True

        # 注意：已禁用智能跳过机制，确保每个用例都执行清理
        # 这样可以保证每个测试用例都从完全干净的状态开始
        return True

    def _get_current_app_package(self, device_id: str) -> Optional[str]:
        """获取当前设备上运行的应用包名

        Args:
            device_id: 设备ID

        Returns:
            应用包名，如果获取失败则返回None
        """
        try:
            # 使用 adb dumpsys 获取当前前台应用
            cmd = f"adb -s {device_id} shell dumpsys window | grep mCurrentFocus"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout:
                # 解析输出，提取包名
                # 格式类似: mCurrentFocus=Window{... u0 com.example.app/com.example.MainActivity}
                for line in result.stdout.split('\n'):
                    if 'mCurrentFocus' in line and 'mCurrentFocus=Window{' in line:
                        # 提取包名部分
                        parts = line.split()
                        for part in parts:
                            if '/' in part and not part.startswith('Window{'):
                                package_name = part.split('/')[0]
                                # 过滤掉系统应用
                                if package_name and not package_name.startswith('com.android.systemui'):
                                    return package_name
        except Exception as e:
            print(f"[WARNING] 获取当前应用包名失败: {str(e)}")

        return None

    def _force_stop_app(self, device_id: str, package_name: str) -> bool:
        """强制停止指定应用

        Args:
            device_id: 设备ID
            package_name: 应用包名

        Returns:
            是否成功
        """
        try:
            # 执行 force-stop 命令
            cmd = f"adb -s {device_id} shell am force-stop {package_name}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                print(f"[清理] 成功杀掉应用进程: {package_name}")
                return True
            else:
                print(f"[ERROR] force-stop 失败: {result.stderr}")
                return False

        except Exception as e:
            print(f"[ERROR] force-stop 异常: {str(e)}")
            return False

    def _clear_app_cache(self, device_id: str, package_name: str) -> bool:
        """清除应用缓存（可选）

        Args:
            device_id: 设备ID
            package_name: 应用包名

        Returns:
            是否成功
        """
        try:
            # 执行 pm clear 命令
            cmd = f"adb -s {device_id} shell pm clear {package_name}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                print(f"[清理] 成功清除应用缓存: {package_name}")
                return True
            else:
                print(f"[WARNING] pm clear 失败（可能非致命）: {result.stderr}")
                return False

        except Exception as e:
            print(f"[WARNING] pm clear 异常（可能非致命）: {str(e)}")
            return False

    def execute_cleanup(
        self,
        agent,
        device_id: str,
        cleanup_steps: List[str],
        test_id: str
    ) -> CleanupResult:
        """执行清理步骤

        Args:
            agent: PhoneAgent 实例
            device_id: 设备ID
            cleanup_steps: 清理步骤列表
            test_id: 测试用例ID

        Returns:
            CleanupResult 清理结果
        """
        start_time = time.time()
        steps_completed = 0
        warnings = []
        error_message = ""
        success = True

        device_lock = self._get_device_lock(device_id)

        with device_lock:
            try:
                # 检查是否是 force_restart 策略
                if cleanup_steps and "__FORCE_RESTART__" in cleanup_steps:
                    print(f"[清理 {test_id}] 执行 force_restart 策略")

                    # 获取当前应用包名
                    package_name = self._get_current_app_package(device_id)

                    if package_name:
                        print(f"[清理 {test_id}] 检测到当前应用: {package_name}")

                        # 执行 force-stop
                        if self._force_stop_app(device_id, package_name):
                            steps_completed += 1

                            # 可选：清除应用缓存（根据配置决定）
                            # 注意：清除缓存会更彻底，但可能导致应用需要重新登录
                            # self._clear_app_cache(device_id, package_name)

                            print(f"[清理 {test_id}] 应用已被强制停止，下次启动将从首页开始")
                        else:
                            error_msg = f"force-stop 执行失败"
                            warnings.append(error_msg)
                            if self.config.failure_mode == "error":
                                success = False
                                error_message = error_msg
                            steps_completed += 1  # 即使失败也标记为已尝试
                    else:
                        warning_msg = "无法获取当前应用包名，跳过 force-stop"
                        warnings.append(warning_msg)
                        print(f"[WARNING] {warning_msg}")
                        # 如果无法获取包名，视为警告但继续
                        steps_completed = 1
                else:
                    # 常规清理步骤
                    for i, step in enumerate(cleanup_steps, 1):
                        try:
                            print(f"[清理 {test_id}] 执行步骤 {i}/{len(cleanup_steps)}: {step}")

                            # 使用agent执行清理步骤
                            result = agent.run(step)

                            steps_completed += 1

                            # 检查是否成功（简单检查结果是否为空或包含错误）
                            if result and ("错误" in result or "失败" in result or "error" in result.lower()):
                                warning_msg = f"清理步骤可能失败: {step} - {result[:100]}"
                                warnings.append(warning_msg)
                                print(f"[WARNING] {warning_msg}")

                        except Exception as e:
                            error_msg = f"清理步骤失败: {step} - {str(e)}"
                            warnings.append(error_msg)
                            print(f"[ERROR] {error_msg}")

                            # 根据失败模式决定是否继续
                            if self.config.failure_mode == "error":
                                success = False
                                error_message = error_msg
                                break
                            elif self.config.failure_mode == "warn":
                                # warn模式继续执行，但记录警告
                                steps_completed += 1
                            else:
                                # ignore模式继续执行
                                steps_completed += 1

                # 更新最后清理时间
                self._last_cleanup_time[device_id] = time.time()

            except Exception as e:
                success = False
                error_message = f"清理过程异常: {str(e)}"
                print(f"[ERROR] {error_message}")

        execution_time = time.time() - start_time

        return CleanupResult(
            success=success,
            steps_completed=steps_completed,
            steps_total=len(cleanup_steps),
            execution_time=execution_time,
            error_message=error_message,
            warnings=warnings
        )

    def record_cleanup_time(self, device_id: str):
        """记录清理时间（用于外部手动控制清理时机）

        Args:
            device_id: 设备ID
        """
        self._last_cleanup_time[device_id] = time.time()

    def reset_cleanup_state(self, device_id: Optional[str] = None):
        """重置清理状态（用于测试或特殊场景）

        Args:
            device_id: 设备ID，如果为None则重置所有设备
        """
        if device_id:
            self._last_cleanup_time.pop(device_id, None)
        else:
            self._last_cleanup_time.clear()
