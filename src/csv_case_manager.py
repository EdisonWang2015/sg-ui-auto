#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV测试用例管理器
从CSV文件读取测试用例并管理测试执行
"""

import csv
import os
from typing import List, Dict, Any, Optional
from base_test_reader import BaseTestReader, APITestCase


class CSVCaseManager(BaseTestReader):
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

                # 新增：状态清理相关字段
                cleanup_strategy = row.get('清理策略', 'inherit')
                cleanup_steps = row.get('清理步骤', '') or None
                require_clean_state_str = row.get('需要干净状态', 'false')
                require_clean_state = require_clean_state_str.lower() in ('true', '1', 'yes', '是')

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
                    tags=tags,
                    cleanup_strategy=cleanup_strategy,
                    cleanup_steps=cleanup_steps,
                    require_clean_state=require_clean_state
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
