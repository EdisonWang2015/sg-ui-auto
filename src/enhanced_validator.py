#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强测试验证器
继承test_validator.py，增强AutoGLM特定验证逻辑
"""

import re
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from test_validator import TestValidator, VerificationResult, ValidationResult


class AutoGLMValidationType(Enum):
    """AutoGLM验证类型"""
    KEYWORD = "关键词验证"
    AMOUNT = "金额验证"
    BUSINESS_DATA = "业务数据验证"
    POPUP = "弹窗验证"
    ORDER_COUNT = "订单数量验证"
    TASK_COMPLETION = "任务完成验证"


@dataclass
class EnhancedValidationResult:
    """增强验证结果"""
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "warning_checks": self.warning_checks,
            "success_rate": f"{(self.passed_checks/self.total_checks*100):.1f}%" if self.total_checks > 0 else "0%",
            "details": self.details
        }

    @property
    def all_passed(self) -> bool:
        """是否全部通过"""
        return self.failed_checks == 0


class EnhancedValidator:
    """
    增强测试验证器

    提供针对AutoGLM的增强验证逻辑：
    - 关键词匹配（支持模糊匹配）
    - 数值范围验证（金额验证，允许±0.5误差）
    - 业务数据验证（农户、客户、类目等）
    - UI元素验证（弹框出现）
    """

    def __init__(self, device_id: str):
        """
        初始化增强验证器

        Args:
            device_id: 设备ID
        """
        self.base_validator = TestValidator(device_id)
        self.device_id = device_id

    def validate_autoGLM_result(
        self,
        output: str,
        expected_results: List[str],
        test_data: Dict[str, Any]
    ) -> EnhancedValidationResult:
        """
        验证AutoGLM执行结果

        Args:
            output: AutoGLM输出
            expected_results: 预期结果列表
            test_data: 测试数据

        Returns:
            EnhancedValidationResult
        """
        result = EnhancedValidationResult()

        # 1. 关键词验证
        for expected in expected_results:
            check = self._verify_keyword(output, expected)
            result.details.append(check)
            result.total_checks += 1
            if check["passed"]:
                result.passed_checks += 1
            else:
                result.failed_checks += 1

        # 2. 金额验证（如果测试数据中有预期金额）
        if test_data and "预期金额" in test_data:
            check = self._verify_amount(output, test_data["预期金额"])
            result.details.append(check)
            result.total_checks += 1
            if check["passed"]:
                result.passed_checks += 1
            else:
                result.failed_checks += 1

        # 3. 业务数据验证
        if test_data:
            for field_name in ["农户", "客户", "类目"]:
                if field_name in test_data:
                    check = self._verify_business_data(output, field_name, test_data[field_name])
                    result.details.append(check)
                    result.total_checks += 1
                    if check["passed"]:
                        result.passed_checks += 1
                    else:
                        result.failed_checks += 1

        return result

    def _verify_keyword(self, output: str, expected: str) -> Dict[str, Any]:
        """
        关键词验证

        Args:
            output: AutoGLM输出
            expected: 预期关键词

        Returns:
            验证结果字典
        """
        # 移除✅等前缀符号进行匹配
        clean_expected = expected.lstrip('✅❌⚠️')

        # 检查是否包含
        passed = clean_expected in output

        return {
            "type": AutoGLMValidationType.KEYWORD.value,
            "expected": expected,
            "actual": "found" if passed else "not found",
            "passed": passed,
            "message": "关键词匹配成功" if passed else f"未找到关键词: {clean_expected}"
        }

    def _verify_amount(self, output: str, expected_amount_str: str) -> Dict[str, Any]:
        """
        金额验证（允许±0.5误差）

        Args:
            output: AutoGLM输出
            expected_amount_str: 预期金额字符串（如"7"）

        Returns:
            验证结果字典
        """
        try:
            expected_amount = float(expected_amount_str)

            # 从输出中查找所有金额
            amounts = re.findall(r'(\d+(?:\.\d+)?)\s*元', output)

            if not amounts:
                return {
                    "type": AutoGLMValidationType.AMOUNT.value,
                    "expected": f"{expected_amount}元",
                    "actual": "未找到金额",
                    "passed": False,
                    "message": "输出中未找到金额信息"
                }

            # 使用最后一个金额（通常是最终结算金额）
            actual_amount = float(amounts[-1])

            # 允许±0.5元误差
            tolerance = 0.5
            passed = abs(actual_amount - expected_amount) <= tolerance

            return {
                "type": AutoGLMValidationType.AMOUNT.value,
                "expected": f"{expected_amount}元 (±{tolerance}元)",
                "actual": f"{actual_amount}元",
                "passed": passed,
                "message": f"金额验证{'通过' if passed else '失败'}，差异: {abs(actual_amount - expected_amount):.2f}元"
            }

        except (ValueError, TypeError) as e:
            return {
                "type": AutoGLMValidationType.AMOUNT.value,
                "expected": f"{expected_amount_str}元",
                "actual": "解析失败",
                "passed": False,
                "message": f"金额解析错误: {str(e)}"
            }

    def _verify_business_data(
        self,
        output: str,
        field_name: str,
        expected_value: str
    ) -> Dict[str, Any]:
        """
        业务数据验证（农户、客户、类目等）

        Args:
            output: AutoGLM输出
            field_name: 字段名称
            expected_value: 预期值

        Returns:
            验证结果字典
        """
        passed = expected_value in output

        return {
            "type": AutoGLMValidationType.BUSINESS_DATA.value,
            "expected": f"{field_name}: {expected_value}",
            "actual": f"{'找到' if passed else '未找到'} {field_name}",
            "passed": passed,
            "message": f"{field_name}验证{'通过' if passed else '失败'}"
        }

    def verify_popup_appeared(
        self,
        output: str,
        expected_keywords: List[str]
    ) -> Dict[str, Any]:
        """
        弹窗验证

        Args:
            output: AutoGLM输出
            expected_keywords: 预期弹窗关键词列表

        Returns:
            验证结果字典
        """
        found_keywords = [kw for kw in expected_keywords if kw in output]
        passed = len(found_keywords) > 0

        return {
            "type": AutoGLMValidationType.POPUP.value,
            "expected": f"包含任一关键词: {expected_keywords}",
            "actual": f"找到: {found_keywords}",
            "passed": passed,
            "message": f"弹窗验证{'通过' if passed else '失败'}"
        }

    def verify_task_completion(self, output: str) -> Dict[str, Any]:
        """
        任务完成验证

        Args:
            output: AutoGLM输出

        Returns:
            验证结果字典
        """
        completion_indicators = ["任务完成", "执行完成", "操作成功", "done", "completed", "success"]
        passed = any(indicator in output.lower() for indicator in completion_indicators)

        return {
            "type": AutoGLMValidationType.TASK_COMPLETION.value,
            "expected": "包含任务完成标识",
            "actual": "找到完成标识" if passed else "未找到完成标识",
            "passed": passed,
            "message": f"任务完成状态{'确认' if passed else '未确认'}"
        }

    def print_validation_details(self, result: EnhancedValidationResult):
        """
        打印验证详情

        Args:
            result: 增强验证结果
        """
        print(f"\n{'─'*60}")
        print(f"验证详情: {result.passed_checks}/{result.total_checks} 通过")
        if result.total_checks > 0:
            print(f"通过率: {(result.passed_checks/result.total_checks*100):.1f}%")
        print(f"{'─'*60}")

        for check in result.details:
            status_icon = "✅" if check["passed"] else "❌"
            print(f"{status_icon} {check['type']}: {check.get('message', check.get('expected', ''))}")

        print(f"{'─'*60}\n")


# 便捷函数
def validate_autoGLM_test(
    output: str,
    expected_results: List[str],
    test_data: Dict[str, Any],
    device_id: str = "unknown"
) -> Tuple[bool, EnhancedValidationResult]:
    """
    验证AutoGLM测试结果的便捷函数

    Args:
        output: AutoGLM输出
        expected_results: 预期结果列表
        test_data: 测试数据
        device_id: 设备ID

    Returns:
        (是否通过, 验证结果)
    """
    validator = EnhancedValidator(device_id)
    result = validator.validate_autoGLM_result(output, expected_results, test_data)
    return result.all_passed, result
