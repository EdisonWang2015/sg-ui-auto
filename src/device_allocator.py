#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备动态分配器
支持多种分配策略：轮询、最少负载、随机、亲和性
"""

import threading
from typing import List, Optional, Dict
from enum import Enum


class AllocationStrategy(Enum):
    """设备分配策略"""
    ROUND_ROBIN = "round_robin"        # 轮询分配（默认）
    LEAST_LOADED = "least_loaded"      # 最少负载优先
    RANDOM = "random"                  # 随机分配
    AFFINITY = "affinity"              # 亲和性（保留原有分配）


class DeviceAllocator:
    """设备动态分配器"""

    def __init__(
        self,
        strategy: AllocationStrategy = AllocationStrategy.ROUND_ROBIN,
        available_devices: Optional[List[str]] = None,
        preserve_affinity: bool = False
    ):
        """
        初始化设备分配器

        Args:
            strategy: 分配策略
            available_devices: 可用设备列表（None则自动检测）
            preserve_affinity: 是否保留已有设备ID的亲和性
        """
        self.strategy = strategy
        self.preserve_affinity = preserve_affinity
        self._lock = threading.Lock()
        self._round_robin_index = 0
        self.device_loads: Dict[str, int] = {}

        # 初始化设备列表
        if available_devices is None:
            self._auto_detect_devices()
        else:
            self.available_devices = available_devices
            for device_id in self.available_devices:
                self.device_loads[device_id] = 0

    def _auto_detect_devices(self):
        """自动检测可用设备"""
        try:
            from phone_agent.device_factory import get_device_factory
            factory = get_device_factory()
            devices = factory.list_devices()
            self.available_devices = [
                d.device_id for d in devices
                if d.status == "device"
            ]
            for device_id in self.available_devices:
                self.device_loads[device_id] = 0
            print(f"[DeviceAllocator] 自动检测到 {len(self.available_devices)} 个可用设备")
        except Exception as e:
            print(f"[DeviceAllocator] 设备检测失败: {e}")
            self.available_devices = []

    def allocate(self, test_case) -> str:
        """
        为测试用例分配设备

        Args:
            test_case: 测试用例对象

        Returns:
            分配的设备ID
        """
        with self._lock:
            # 获取用例的原始设备ID
            original_device_id = getattr(test_case, 'device_id', '') or ''

            # 如果用例已有设备ID且开启亲和性保留，并且设备ID有效（非空且在可用设备列表中）
            if (self.preserve_affinity and
                original_device_id and
                original_device_id.strip() and
                original_device_id in self.available_devices):
                return original_device_id

            # 如果原始设备ID为空或不在可用列表中，总是需要分配
            # 根据策略分配设备
            if self.strategy == AllocationStrategy.ROUND_ROBIN:
                device_id = self.available_devices[self._round_robin_index]
                self._round_robin_index = (self._round_robin_index + 1) % len(self.available_devices)
            elif self.strategy == AllocationStrategy.LEAST_LOADED:
                device_id = min(self.device_loads.items(), key=lambda x: x[1])[0]
            elif self.strategy == AllocationStrategy.RANDOM:
                import random
                device_id = random.choice(self.available_devices)
            else:  # AFFINITY or default
                # 优先使用原设备ID（如果有效）
                if original_device_id and original_device_id.strip() and original_device_id in self.available_devices:
                    device_id = original_device_id
                else:
                    # 原设备ID无效，使用轮询
                    device_id = self.available_devices[self._round_robin_index]
                    self._round_robin_index = (self._round_robin_index + 1) % len(self.available_devices)

            # 更新负载计数
            self.device_loads[device_id] += 1

            return device_id

    def deallocate(self, device_id: str):
        """
        释放设备（减少负载计数）

        Args:
            device_id: 设备ID
        """
        with self._lock:
            if device_id in self.device_loads and self.device_loads[device_id] > 0:
                self.device_loads[device_id] -= 1

    def get_allocation_summary(self) -> Dict:
        """获取分配汇总信息"""
        with self._lock:
            return dict(self.device_loads)

    def get_available_devices(self) -> List[str]:
        """获取可用设备列表"""
        return self.available_devices.copy()
