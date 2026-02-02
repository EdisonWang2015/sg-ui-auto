#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV测试用例管理器
从CSV/Excel文件读取测试用例并管理测试执行
"""

import csv
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json


@dataclass
class APITestCase:
    """API测试用例数据结构"""
    test_id: str                          # 测试用例ID
    name: str                             # 测试名称
    type: str                             # 测试类型
    priority: str                         # 优先级
    preconditions: str                    # 前置条件
    task_command: str                     # 任务指令（自然语言描述）
    expected_results: List[str]           # 预期结果列表
    test_data: Dict[str, Any]             # 测试数据
    device_id: str                        # 设备ID
    timeout: int                          # 超时时间
    tags: List[str] = field(default_factory=list)  # 标签

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "test_id": self.test_id,
            "name": self.name,
            "type": self.type,
            "priority": self.priority,
            "preconditions": self.preconditions,
            "task_command": self.task_command,
            "expected_results": self.expected_results,
            "test_data": self.test_data,
            "device_id": self.device_id,
            "timeout": self.timeout,
            "tags": self.tags
        }


class CSVCaseManager:
    """CSV测试用例管理器"""

    def __init__(self, csv_file: str):
        """
        初始化CSV测试用例管理器

        Args:
            csv_file: CSV文件路径
        """
        self.csv_file = csv_file
        self.test_cases: List[APITestCase] = []
        self._load_test_cases()

    def _load_test_cases(self):
        """从CSV加载测试用例"""
        if not os.path.exists(self.csv_file):
            raise FileNotFoundError(f"测试用例文件不存在: {self.csv_file}")

        with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 跳过注释行和空ID行
                test_id = row.get('测试用例ID', '').strip()
                if not test_id or test_id.startswith('#'):
                    continue

                # 解析预期结果（按空格分隔）
                expected_str = row.get('预期结果', '')
                expected_results = [e.strip() for e in expected_str.split() if e.strip()]

                # 解析测试数据（键值对格式）
                test_data = self._parse_test_data(row.get('测试数据', ''))

                # 解析标签（逗号分隔）
                tags_str = row.get('标签', '')
                tags = [t.strip() for t in tags_str.split(',') if t.strip()]

                # 支持多种超时列名
                timeout_col = row.get('超时时间') or row.get('任务超时时间') or 180

                test_case = APITestCase(
                    test_id=test_id,
                    name=row.get('测试名称', ''),
                    type=row.get('测试类型', ''),
                    priority=row.get('优先级', ''),
                    preconditions=row.get('前置条件', ''),
                    task_command=row.get('测试步骤', ''),
                    expected_results=expected_results,
                    test_data=test_data,
                    device_id=row.get('设备ID', ''),
                    timeout=int(timeout_col) if timeout_col else 180,
                    tags=tags
                )
                self.test_cases.append(test_case)

        print(f"从 {self.csv_file} 加载了 {len(self.test_cases)} 个测试用例")

    def _parse_test_data(self, test_data_str: str) -> Dict[str, Any]:
        """
        解析测试数据字符串为字典

        支持格式：
        - "类目:苹果,农户:非伍6,数量:1"
        - "key1:value1,key2:value2"

        Args:
            test_data_str: 测试数据字符串

        Returns:
            解析后的字典
        """
        test_data = {}
        if not test_data_str:
            return test_data

        for item in test_data_str.split(','):
            if ':' in item:
                key, value = item.split(':', 1)
                test_data[key.strip()] = value.strip()

        return test_data

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


def main():
    """主函数 - 示例用法"""
    import argparse

    parser = argparse.ArgumentParser(description="CSV测试用例管理器")
    parser.add_argument("--csv", required=True, help="CSV测试用例文件路径")
    parser.add_argument("--filter-tags", help="按标签筛选")
    parser.add_argument("--filter-type", help="按类型筛选")
    parser.add_argument("--filter-priority", help="按优先级筛选")
    parser.add_argument("--show-summary", action="store_true", help="显示汇总信息")

    args = parser.parse_args()

    # 初始化管理器
    manager = CSVCaseManager(args.csv)

    # 显示汇总
    if args.show_summary:
        manager.show_summary()
        return

    # 筛选测试用例
    test_cases = manager.filter_by_criteria(
        tags=args.filter_tags,
        test_type=args.filter_type,
        priority=args.filter_priority
    )

    print(f"\n筛选结果: {len(test_cases)} 个测试用例")
    for tc in test_cases[:10]:
        print(f"  - {tc.test_id}: {tc.name}")
    if len(test_cases) > 10:
        print(f"  ... 还有 {len(test_cases) - 10} 个用例")


if __name__ == "__main__":
    main()
