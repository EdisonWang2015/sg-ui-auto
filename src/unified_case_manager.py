#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的测试用例管理器
支持从多个文件（CSV和Excel混合）加载测试用例
"""

from typing import Union, List, Dict, Any, Optional
from base_test_reader import BaseTestReader, APITestCase
from test_reader_factory import create_test_reader


class UnifiedTestCaseManager:
    """统一的测试用例管理器（支持多文件）"""

    def __init__(self, file_paths: Union[str, List[str]]):
        """
        支持从多个文件加载测试用例

        Args:
            file_paths: 文件路径或路径列表（支持混合CSV和Excel）
                       单个字符串：'/path/to/file.csv'
                       列表：['/path/to/file1.csv', '/path/to/file2.xlsx']
        """
        self.test_cases: List[APITestCase] = []
        self._load_from_files(file_paths)

    def _load_from_files(self, file_paths: Union[str, List[str]]):
        """从文件列表加载测试用例"""
        import os

        # 标准化为列表
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        # 从所有文件加载测试用例
        loaded_count = 0
        for file_path in file_paths:
            try:
                if not os.path.exists(file_path):
                    print(f"⚠️  警告: 文件不存在，跳过: {file_path}")
                    continue

                reader = create_test_reader(file_path)
                cases_from_file = reader.get_all_test_cases()
                self.test_cases.extend(cases_from_file)
                loaded_count += 1

            except Exception as e:
                print(f"⚠️  警告: 加载文件失败 {file_path}: {str(e)}")
                continue

        print(f"总共从 {loaded_count}/{len(file_paths)} 个文件加载了 {len(self.test_cases)} 个测试用例")

    def get_all_test_cases(self) -> List[APITestCase]:
        """获取所有测试用例"""
        return self.test_cases

    def filter_by_tags(self, tags: str) -> List[APITestCase]:
        """
        按标签筛选测试用例

        Args:
            tags: 标签（逗号分隔）

        Returns:
            筛选后的测试用例列表
        """
        target_tags = set(tag.strip() for tag in tags.split(','))
        return [
            tc for tc in self.test_cases
            if any(tag in tc.tags for tag in target_tags)
        ]

    def filter_by_type(self, test_type: str) -> List[APITestCase]:
        """
        按类型筛选测试用例

        Args:
            test_type: 测试类型

        Returns:
            筛选后的测试用例列表
        """
        return [tc for tc in self.test_cases if tc.type == test_type]

    def filter_by_priority(self, priority: str) -> List[APITestCase]:
        """
        按优先级筛选测试用例

        Args:
            priority: 优先级

        Returns:
            筛选后的测试用例列表
        """
        return [tc for tc in self.test_cases if tc.priority == priority]

    def filter_by_device_id(self, device_id: str) -> List[APITestCase]:
        """
        按设备ID筛选测试用例

        Args:
            device_id: 设备ID

        Returns:
            筛选后的测试用例列表
        """
        return [tc for tc in self.test_cases if tc.device_id == device_id]

    def get_test_case_by_id(self, test_id: str) -> Optional[APITestCase]:
        """
        根据ID获取测试用例

        Args:
            test_id: 测试用例ID

        Returns:
            测试用例对象或None
        """
        for tc in self.test_cases:
            if tc.test_id == test_id:
                return tc
        return None

    def filter_by_criteria(
        self,
        tags: Optional[str] = None,
        test_type: Optional[str] = None,
        priority: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> List[APITestCase]:
        """
        综合筛选测试用例

        Args:
            tags: 标签筛选
            test_type: 类型筛选
            priority: 优先级筛选
            device_id: 设备ID筛选

        Returns:
            筛选后的测试用例列表
        """
        test_cases = self.test_cases

        if tags:
            test_cases = [tc for tc in test_cases if any(tag in tc.tags for tag in tags.split(','))]

        if test_type:
            test_cases = [tc for tc in test_cases if tc.type == test_type]

        if priority:
            test_cases = [tc for tc in test_cases if tc.priority == priority]

        if device_id:
            test_cases = [tc for tc in test_cases if tc.device_id == device_id]

        return test_cases

    def group_by_device_id(self) -> Dict[str, List[APITestCase]]:
        """
        按设备ID分组测试用例

        Returns:
            设备ID到测试用例列表的映射
        """
        groups = {}
        for tc in self.test_cases:
            if tc.device_id not in groups:
                groups[tc.device_id] = []
            groups[tc.device_id].append(tc)
        return groups

    def show_summary(self):
        """显示测试用例汇总信息"""
        print(f"\n测试用例汇总")
        print(f"{'='*60}")
        print(f"总用例数: {len(self.test_cases)}")

        # 按类型统计
        type_count = {}
        for tc in self.test_cases:
            type_count[tc.type] = type_count.get(tc.type, 0) + 1

        print(f"\n按类型分布:")
        for test_type, count in sorted(type_count.items()):
            print(f"  - {test_type}: {count}个")

        # 按优先级统计
        priority_count = {}
        for tc in self.test_cases:
            priority_count[tc.priority] = priority_count.get(tc.priority, 0) + 1

        print(f"\n按优先级分布:")
        priority_order = ["P0", "P1", "P2", "P3"]
        for priority in priority_order:
            if priority in priority_count:
                print(f"  - {priority}: {priority_count[priority]}个")

        # 按标签统计
        tag_count = {}
        for tc in self.test_cases:
            for tag in tc.tags:
                tag_count[tag] = tag_count.get(tag, 0) + 1

        if tag_count:
            print(f"\n按标签分布:")
            for tag, count in sorted(tag_count.items()):
                print(f"  - {tag}: {count}个")

        # 按设备统计
        device_count = {}
        for tc in self.test_cases:
            device_count[tc.device_id] = device_count.get(tc.device_id, 0) + 1

        if device_count:
            print(f"\n按设备分布:")
            for device, count in sorted(device_count.items()):
                print(f"  - {device}: {count}个")

        print(f"{'='*60}\n")
