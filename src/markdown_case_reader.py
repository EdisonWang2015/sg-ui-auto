#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown测试用例读取器
从Markdown文件(.md, .markdown)读取测试用例
支持单文件多测试用例格式
"""

import os
import re
from typing import List, Dict, Any, Optional

from base_test_reader import BaseTestReader, APITestCase


class MarkdownCaseReader(BaseTestReader):
    """Markdown测试用例读取器"""

    def _load_test_cases(self):
        """从Markdown加载测试用例"""
        if not self.file_path.endswith(('.md', '.markdown')):
            raise ValueError("不支持的文件格式，请使用.md或.markdown文件")

        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"测试用例文件不存在: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析MD文件，提取所有测试用例
        test_cases = self._parse_markdown(content)

        if not test_cases:
            raise ValueError(f"MD文件中未找到有效的测试用例: {self.file_path}")

        # 过滤掉以 '#' 开头的注释用例和非标准ID的用例
        valid_test_cases = []
        for tc in test_cases:
            # 检查测试用例ID是否以 TC 开头（或其他标准前缀）
            if tc.test_id and (tc.test_id.startswith('TC') or tc.test_id.startswith('T')):
                valid_test_cases.append(tc)

        if not valid_test_cases:
            raise ValueError(f"MD文件中未找到有效的测试用例（ID需要以 TC 或 T 开头）: {self.file_path}")

        for tc in valid_test_cases:
            self.test_cases.append(tc)

        print(f"从 {self.file_path} 加载了 {len(self.test_cases)} 个测试用例")

    def _parse_markdown(self, content: str) -> List[APITestCase]:
        """
        解析Markdown内容，提取测试用例

        支持的格式：
        1. ## 用例：TC001 - 测试名称
        2. ## TC001 - 测试名称
        3. ## TC001

        Args:
            content: Markdown文件内容

        Returns:
            测试用例列表
        """
        test_cases = []

        # 按二级标题分割测试用例（## 用例：或 ##）
        # 匹配 ## 用例：xxx 或 ## TCxxx 格式
        pattern = r'^##\s+(?:用例：)?\s*(.+?)(?:\s+-\s+(.+))?$'
        splits = re.split(pattern, content, flags=re.MULTILINE)

        # splits 格式: ['', test_id, test_name, content_of_case, '', next_test_id, ...]
        # 跳过第一个空字符串
        parts = splits[1:]

        i = 0
        while i < len(parts):
            if i + 2 < len(parts):
                test_id_part = parts[i].strip()
                test_name_part = parts[i + 1].strip() if parts[i + 1] else ''
                case_content = parts[i + 2]

                # 解析测试用例ID和名称
                test_id, name = self._parse_test_id_and_name(test_id_part, test_name_part)

                # 解析测试用例内容
                test_case = self._parse_case_content(test_id, name, case_content)
                if test_case:
                    test_cases.append(test_case)

                i += 3
            else:
                break

        return test_cases

    def _parse_test_id_and_name(self, test_id_part: str, test_name_part: str) -> tuple:
        """
        解析测试用例ID和名称

        Args:
            test_id_part: ID部分（如 "TC001" 或 "TC001 - 新建采购单"）
            test_name_part: 名称部分（如果有）

        Returns:
            (test_id, name) 元组
        """
        # 检查 test_id_part 是否包含名称
        if ' - ' in test_id_part:
            parts = test_id_part.split(' - ', 1)
            test_id = parts[0].strip()
            name = parts[1].strip()
        else:
            test_id = test_id_part.strip()
            name = test_name_part.strip() if test_name_part else test_id

        return test_id, name

    def _parse_case_content(self, test_id: str, name: str, content: str) -> Optional[APITestCase]:
        """
        解析单个测试用例的内容

        Args:
            test_id: 测试用例ID
            name: 测试名称
            content: 用例内容

        Returns:
            APITestCase对象或None
        """
        # 跳过注释用例
        if test_id.startswith('#'):
            return None

        # 默认值
        test_type = ''
        priority = ''
        preconditions = ''
        task_command = ''
        expected_results = []
        test_data = {}
        device_id = ''
        timeout = 180
        tags = []
        cleanup_strategy = 'inherit'
        cleanup_steps = None
        require_clean_state = False

        # 解析表格格式的字段
        table_data = self._parse_table_fields(content)
        if table_data:
            test_type = table_data.get('测试类型', '')
            priority = table_data.get('优先级', '')
            device_id = table_data.get('设备ID', '')
            timeout_str = table_data.get('超时时间', table_data.get('超时', '180'))
            try:
                timeout = int(timeout_str)
            except (ValueError, TypeError):
                timeout = 180

            tags_str = table_data.get('标签', '')
            tags = [t.strip() for t in tags_str.split(',') if t.strip()]

            cleanup_strategy = table_data.get('清理策略', 'inherit')
            cleanup_steps = table_data.get('清理步骤', '') or None
            require_clean_state_str = table_data.get('需要干净状态', 'false')
            require_clean_state = require_clean_state_str.lower() in ('true', '1', 'yes', '是')

        # 解析前置条件
        preconditions = self._extract_field(content, ['前置条件', '前置', 'Precondition'])

        # 解析测试步骤
        task_command = self._extract_field(content, ['测试步骤', '步骤', 'Steps', '任务指令'])

        # 解析预期结果
        expected_str = self._extract_field(content, ['预期结果', '预期', 'Expected'])
        if expected_str:
            expected_results = [e.strip() for e in expected_str.split() if e.strip()]

        # 解析测试数据
        test_data_str = self._extract_field(content, ['测试数据', 'TestData'])
        test_data = self._parse_test_data(test_data_str)

        # 验证必需字段
        if not task_command:
            print(f"⚠️  警告: 测试用例 {test_id} 缺少测试步骤，跳过")
            return None

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

    def _parse_table_fields(self, content: str) -> Dict[str, str]:
        """
        解析Markdown表格格式的字段

        支持格式：
        | 字段 | 值 |
        |------|------|
        | 测试类型 | 采购单 |
        | 优先级 | P1 |

        Args:
            content: 用例内容

        Returns:
            字段字典
        """
        fields = {}

        # 查找表格部分
        table_pattern = r'\|[\s\S]*?\|[\r\n]+(?:\|[-:\s|]+\|[\r\n]+)?([\s\S]*?)(?=\n\n|\n\*\*|\n---|$)'
        table_matches = re.findall(table_pattern, content)

        for table_content in table_matches:
            # 解析每一行
            lines = table_content.strip().split('\n')
            for line in lines:
                if '|' in line:
                    # 分割表格单元格
                    cells = [cell.strip() for cell in line.split('|')]
                    # 过滤掉首尾的空单元格（由于 | 开头和结尾导致）
                    cells = [c for c in cells if c]

                    if len(cells) >= 2:
                        field_name = cells[0].rstrip('*').strip()  # 去除可能的 ** 标记
                        field_value = cells[1].strip()
                        fields[field_name] = field_value

        return fields

    def _extract_field(self, content: str, labels: List[str]) -> str:
        """
        从内容中提取指定字段值

        支持格式：
        **前置条件**：设备已连接
        **测试步骤**：打开应用...

        Args:
            content: 用例内容
            labels: 可能的标签列表（按优先级）

        Returns:
            字段值
        """
        for label in labels:
            # 匹配 **label**：value 或 **label**: value 格式
            patterns = [
                rf'\*\*{label}\*\*[:：]\s*(.+?)(?:\n|$)',
                rf'\*\*{label}\*\*\s*[:：]\s*(.+?)(?:\n|$)',
            ]

            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    # 去除末尾的 ** 标记
                    value = re.sub(r'\s*\*\*$', '', value)
                    return value

        return ''

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
