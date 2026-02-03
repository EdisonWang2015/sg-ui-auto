#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel测试用例读取器
从Excel文件(.xlsx, .xls)读取测试用例
"""

import os
from typing import List, Dict, Any, Optional
from openpyxl import load_workbook

from base_test_reader import BaseTestReader, APITestCase


class ExcelCaseReader(BaseTestReader):
    """Excel测试用例读取器"""

    def _load_test_cases(self):
        """从Excel加载测试用例"""
        if not self.file_path.endswith(('.xlsx', '.xls')):
            raise ValueError("不支持的文件格式，请使用.xlsx或.xls文件")

        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"测试用例文件不存在: {self.file_path}")

        # 使用read_only模式提升性能
        wb = load_workbook(self.file_path, read_only=True, data_only=True)
        ws = wb.active  # 使用第一个工作表

        # 检查工作表是否为空
        if ws.max_row < 2:
            wb.close()
            raise ValueError("Excel文件没有数据行（至少需要表头和一行数据）")

        # 读取表头（第一行）
        headers = [cell.value for cell in ws[1]]

        # 检查必需列
        required_columns = ['测试用例ID', '测试名称', '测试步骤']
        missing_columns = [col for col in required_columns if col not in headers]
        if missing_columns:
            wb.close()
            raise ValueError(f"缺少必需列: {', '.join(missing_columns)}")

        # 构建列名映射
        col_mapping = self._build_column_mapping(headers)

        # 从第二行开始读取数据
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                test_id = str(row[col_mapping['测试用例ID']] or '').strip()

                # 跳过空行和注释行
                if not test_id or test_id.startswith('#'):
                    continue

                # 解析测试用例数据
                test_case = self._parse_test_row(row, col_mapping)
                self.test_cases.append(test_case)

            except Exception as e:
                print(f"⚠️  警告: 第{row_idx}行解析失败: {str(e)}")
                continue

        wb.close()
        print(f"从 {self.file_path} 加载了 {len(self.test_cases)} 个测试用例")

    def _build_column_mapping(self, headers: List[str]) -> Dict[str, int]:
        """
        构建列名到索引的映射

        Args:
            headers: 表头列表

        Returns:
            列名到索引的映射字典
        """
        mapping = {}
        for idx, header in enumerate(headers):
            if header:
                mapping[header] = idx
        return mapping

    def _parse_test_row(self, row: tuple, col_mapping: Dict[str, int]) -> APITestCase:
        """
        解析单行测试数据

        Args:
            row: 行数据元组
            col_mapping: 列名映射

        Returns:
            测试用例对象
        """
        # 辅助函数：安全获取单元格值
        def get_cell_value(column_name: str, default_index: int = 0, default_value: str = '') -> str:
            """安全获取单元格值"""
            col_idx = col_mapping.get(column_name, default_index)
            if col_idx is not None and col_idx < len(row):
                return str(row[col_idx] or '').strip()
            return default_value

        # 获取各列数据（使用get方法处理可能缺失的列）
        test_id = get_cell_value('测试用例ID', 0)
        name = get_cell_value('测试名称', 1)
        test_type = get_cell_value('测试类型', 2)
        priority = get_cell_value('优先级', 3)
        preconditions = get_cell_value('前置条件', 4)
        task_command = get_cell_value('测试步骤', 5)

        # 解析预期结果（按空格分隔）
        expected_str = get_cell_value('预期结果', 6)
        expected_results = [e.strip() for e in expected_str.split() if e.strip()]

        # 解析测试数据（键值对格式）
        test_data_str = get_cell_value('测试数据', 7)
        test_data = self._parse_test_data(test_data_str)

        # 支持多种超时列名
        timeout_idx = col_mapping.get('超时时间') or col_mapping.get('任务超时时间')
        timeout = 180  # 默认值
        if timeout_idx is not None and timeout_idx < len(row) and row[timeout_idx]:
            try:
                timeout = int(row[timeout_idx])
            except (ValueError, TypeError):
                timeout = 180

        # 解析标签（逗号分隔）
        tags_str = get_cell_value('标签', 9)
        tags = [t.strip() for t in tags_str.split(',') if t.strip()]

        # 设备ID
        device_id = get_cell_value('设备ID', 10)

        # 新增：状态清理相关字段
        cleanup_strategy = get_cell_value('清理策略', 11, 'inherit')
        cleanup_steps = get_cell_value('清理步骤', 12, '') or None
        require_clean_state_str = get_cell_value('需要干净状态', 13, 'false')
        require_clean_state = require_clean_state_str.lower() in ('true', '1', 'yes', '是')

        return APITestCase(
            test_id=test_id,
            name=name,
            type=test_type,
            priority=priority,
            preconditions=preconditions,
            task_command=task_command,
            expected_results=expected_results,
            test_data=test_data,
            device_id=device_id,
            timeout=timeout,
            tags=tags,
            cleanup_strategy=cleanup_strategy,
            cleanup_steps=cleanup_steps,
            require_clean_state=require_clean_state
        )

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
