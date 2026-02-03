#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试用例读取器工厂
根据文件扩展名自动创建对应的读取器
"""

from typing import Union, List
from base_test_reader import BaseTestReader, APITestCase
from csv_case_manager import CSVCaseManager
from excel_case_reader import ExcelCaseReader
from markdown_case_reader import MarkdownCaseReader


def create_test_reader(file_path: str, config=None) -> BaseTestReader:
    """
    根据文件扩展名创建对应的读取器

    Args:
        file_path: 测试用例文件路径
        config: 测试框架配置（可选），用于传递给读取器

    Returns:
        测试用例读取器实例

    Raises:
        ValueError: 不支持的文件格式
        FileNotFoundError: 文件不存在
    """
    import os

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"测试用例文件不存在: {file_path}")

    if file_path.endswith('.csv'):
        return CSVCaseManager(file_path, config=config)
    elif file_path.endswith(('.xlsx', '.xls')):
        return ExcelCaseReader(file_path, config=config)
    elif file_path.endswith(('.md', '.markdown')):
        return MarkdownCaseReader(file_path, config=config)
    else:
        raise ValueError(
            f"不支持的文件格式: {file_path}. "
            f"支持的格式: .csv, .xlsx, .xls, .md, .markdown"
        )


def create_test_reader_from_files(file_paths: Union[str, List[str]]) -> 'UnifiedTestCaseManager':
    """
    从一个或多个文件创建统一的测试用例管理器

    Args:
        file_paths: 文件路径或路径列表（支持混合CSV和Excel）

    Returns:
        统一的测试用例管理器实例

    Examples:
        >>> # 单个文件
        >>> manager = create_test_reader_from_files('test_cases.csv')

        >>> # 多个文件（混合格式）
        >>> manager = create_test_reader_from_files([
        ...     'test_cases.csv',
        ...     'test_cases.xlsx',
        ...     'test_cases.md'
        ... ])
    """
    from unified_case_manager import UnifiedTestCaseManager
    return UnifiedTestCaseManager(file_paths)


def detect_file_type(file_path: str) -> str:
    """
    检测文件类型

    Args:
        file_path: 文件路径

    Returns:
        文件类型字符串 ('csv', 'xlsx', 'xls', 'markdown', 'unknown')
    """
    if file_path.endswith('.csv'):
        return 'csv'
    elif file_path.endswith('.xlsx'):
        return 'xlsx'
    elif file_path.endswith('.xls'):
        return 'xls'
    elif file_path.endswith(('.md', '.markdown')):
        return 'markdown'
    else:
        return 'unknown'
