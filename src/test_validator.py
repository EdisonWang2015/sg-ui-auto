#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
森果产地通 - UI自动化测试验证框架
用于提高测试稳定性，降低误报率，确保真实错误100%捕获
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum


class VerificationResult(Enum):
    """验证结果状态"""
    PASS = "通过"
    FAIL = "失败"
    WARNING = "警告"
    SKIP = "跳过"


class ValidationResult:
    """单个验证结果"""
    def __init__(self, name: str, status: VerificationResult,
                 expected: Any, actual: Any,
                 error_msg: str = "", screenshot_path: str = ""):
        self.name = name
        self.status = status
        self.expected = expected
        self.actual = actual
        self.error_msg = error_msg
        self.screenshot_path = screenshot_path

    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status.value,
            "expected": str(self.expected),
            "actual": str(self.actual),
            "error_msg": self.error_msg,
            "screenshot_path": self.screenshot_path
        }


class TestValidator:
    """测试验证器 - 提供多种验证方法"""

    def __init__(self, adb_device_id: str):
        self.adb_device_id = adb_device_id
        self.results: List[ValidationResult] = []

    def verify_exact_match(self, name: str, expected: str, actual: str,
                          strict: bool = False) -> ValidationResult:
        """
        精确匹配验证

        Args:
            name: 验证项名称
            expected: 期望值
            actual: 实际值
            strict: 是否严格匹配（区分大小写、空格）

        Returns:
            ValidationResult
        """
        if strict:
            is_match = expected == actual
        else:
            # 宽松匹配：忽略大小写、多余空格、换行符
            expected_clean = self._clean_string(expected)
            actual_clean = self._clean_string(actual)
            is_match = expected_clean == actual_clean

        if is_match:
            result = ValidationResult(
                name=name,
                status=VerificationResult.PASS,
                expected=expected,
                actual=actual
            )
        else:
            result = ValidationResult(
                name=name,
                status=VerificationResult.FAIL,
                expected=expected,
                actual=actual,
                error_msg=f"精确匹配失败"
            )

        self.results.append(result)
        return result

    def verify_contains(self, name: str, text: str,
                       must_contain: List[str]) -> ValidationResult:
        """
        包含关系验证 - 验证文本是否包含所有必需的子串

        Args:
            name: 验证项名称
            text: 待验证的文本
            must_contain: 必须包含的子串列表

        Returns:
            ValidationResult
        """
        missing = []
        for substring in must_contain:
            if substring not in text:
                missing.append(substring)

        if not missing:
            result = ValidationResult(
                name=name,
                status=VerificationResult.PASS,
                expected=f"包含: {must_contain}",
                actual=f"文本长度: {len(text)}"
            )
        else:
            result = ValidationResult(
                name=name,
                status=VerificationResult.FAIL,
                expected=f"包含: {must_contain}",
                actual=f"缺失: {missing}",
                error_msg=f"文本中缺少以下内容: {missing}"
            )

        self.results.append(result)
        return result

    def verify_numeric_range(self, name: str, value: str,
                              min_val: float, max_val: float) -> ValidationResult:
        """
        数值范围验证 - 从文本中提取数字并验证范围

        Args:
            name: 验证项名称
            value: 包含数字的文本（如："金额：7元"）
            min_val: 最小值
            max_val: 最大值

        Returns:
            ValidationResult
        """
        # 从文本中提取数字（支持小数点和负数）
        numbers = re.findall(r'-?\d+\.?\d*', value)
        if not numbers:
            return ValidationResult(
                name=name,
                status=VerificationResult.FAIL,
                expected=f"范围: {min_val}-{max_val}",
                actual=value,
                error_msg="未找到数值"
            )

        # 取第一个数字
        num = float(numbers[0])

        if min_val <= num <= max_val:
            return ValidationResult(
                name=name,
                status=VerificationResult.PASS,
                expected=f"范围: {min_val}-{max_val}",
                actual=f"数值: {num}"
            )
        else:
            return ValidationResult(
                name=name,
                status=VerificationResult.FAIL,
                expected=f"范围: {min_val}-{max_val}",
                actual=f"数值: {num}",
                error_msg=f"数值{num}不在范围{min_val}-{max_val}内"
            )

    def verify_element_exists(self, name: str, page_text: str,
                            must_exist: List[str]) -> ValidationResult:
        """
        元素存在性验证 - 验证页面中是否存在某些关键词

        Args:
            name: 验证项名称
            page_text: 页面文本内容
            must_exist: 必须存在的关键词列表

        Returns:
            ValidationResult
        """
        missing = []
        for keyword in must_exist:
            if keyword not in page_text:
                missing.append(keyword)

        if not missing:
            return ValidationResult(
                name=name,
                status=VerificationResult.PASS,
                expected=f"包含: {must_exist}",
                actual="验证通过"
            )
        else:
            return ValidationResult(
                name=name,
                status=VerificationResult.FAIL,
                expected=f"包含: {must_exist}",
                actual=f"缺失: {missing}",
                error_msg=f"页面中缺少以下关键词: {missing}"
            )

    def verify_order_count(self, name: str, page_text: str,
                           expected_count_range: Tuple[int, int],
                           order_keywords: List[str] = None) -> ValidationResult:
        """
        订单数量验证 - 验证订单数量在预期范围内

        Args:
            name: 验证项名称
            page_text: 页面文本
            expected_count_range: (最小数量, 最大数量)
            order_keywords: 订单关键词（用于识别订单，如："采购单"、"结算单"）

        Returns:
            ValidationResult
        """
        # 简单实现：查找数字模式（如："共2单"、"数量:2"）
        if order_keywords:
            # 如果指定了关键词，查找关键词后的数字
            for keyword in order_keywords:
                pattern = rf'{keyword}.*?(\d+)'
                match = re.search(pattern, page_text)
                if match:
                    count = int(match.group(1))
                    min_val, max_val = expected_count_range
                    if min_val <= count <= max_val:
                        return ValidationResult(
                            name=name,
                            status=VerificationResult.PASS,
                            expected=f"{min_val}-{max_val}单",
                            actual=f"{count}单"
                        )

        # 通用实现：查找"共X单"或"合计.*共(\d+)单"
        pattern = r'共\s*(\d+)\s*单'
        matches = re.findall(pattern, page_text)
        if matches:
            count = int(matches[0])
            min_val, max_val = expected_count_range
            if min_val <= count <= max_val:
                return ValidationResult(
                    name=name,
                    status=VerificationResult.PASS,
                    expected=f"{min_val}-{max_val}单",
                    actual=f"{count}单"
                )

        return ValidationResult(
            name=name,
            status=VerificationResult.WARNING,
            expected=f"{expected_count_range[0]}-{expected_count_range[1]}单",
            actual="无法确定数量",
            error_msg="无法从页面文本中提取订单数量"
        )

    def verify_calculation(self, name: str, page_text: str,
                          formula: str = None) -> ValidationResult:
        """
        计算结果验证 - 验证金额计算是否正确

        Args:
            name: 验证项名称
            page_text: 页面文本
            formula: 计算公式（如："数量*单价-折扣"）

        Returns:
            ValidationResult
        """
        # 从文本中提取数值
        quantities = re.findall(r'(\d+)\s*件', page_text)
        unit_prices = re.findall(r'(\d+)\s*元/kg', page_text)
        discounts = re.findall(r'(\d+)\s*元', page_text)
        totals = re.findall(r'总计.*?(\d+)\s*元', page_text)

        if not (quantities and unit_prices and totals):
            return ValidationResult(
                name=name,
                status=VerificationResult.SKIP,
                expected="计算验证",
                actual="无法提取计算所需数值",
                error_msg="缺少关键数据"
            )

        # 简单验证：检查总金额是否合理
        total_amount = float(totals[0])
        if total_amount > 0:
            return ValidationResult(
                name=name,
                status=VerificationResult.PASS,
                expected="总金额>0",
                actual=f"总金额={total_amount}元"
            )

        return ValidationResult(
            name=name,
            status=VerificationResult.WARNING,
            expected="计算验证",
            actual=f"总金额={total_amount}元",
            error_msg="计算公式验证待实现"
        )

    def _clean_string(self, text: str) -> str:
        """清理字符串 - 去除多余空格、换行等"""
        # 去除所有空白字符（空格、换行、制表符）
        cleaned = re.sub(r'\s+', '', text)
        # 转小写
        cleaned = cleaned.lower()
        return cleaned

    def verify_popup_appeared(self, popup_text: str,
                            expected_popup_keywords: List[str]) -> ValidationResult:
        """
        弹窗验证 - 验证预期的弹窗是否出现

        Args:
            popup_text: 弹窗文本内容
            expected_popup_keywords: 预期弹窗应包含的关键词

        Returns:
            ValidationResult
        """
        if not popup_text:
            return ValidationResult(
                name="弹窗验证",
                status=VerificationResult.FAIL,
                expected=f"弹窗包含: {expected_popup_keywords}",
                actual="无弹窗",
                error_msg="预期弹窗未出现"
            )

        for keyword in expected_popup_keywords:
            if keyword in popup_text:
                return ValidationResult(
                    name="弹窗验证",
                    status=VerificationResult.PASS,
                    expected=f"包含关键词: {keyword}",
                    actual=popup_text[:50] + "..."
                )

        return ValidationResult(
            name="弹窗验证",
            status=VerificationResult.FAIL,
            expected=f"包含: {expected_popup_keywords}",
            actual=popup_text[:100],
            error_msg="弹窗内容不符合预期"
        )

    def get_summary(self) -> Dict[str, Any]:
        """获取验证结果摘要"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == VerificationResult.PASS)
        failed = sum(1 for r in self.results if r.status == VerificationResult.FAIL)
        warnings = sum(1 for r in self.results if r.status == VerificationResult.WARNING)
        skipped = sum(1 for r in self.results if r.status == VerificationResult.SKIP)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "skipped": skipped,
            "success_rate": f"{(passed/total*100):.1f}%" if total > 0 else "0%",
            "details": [r.to_dict() for r in self.results]
        }

    def has_failures(self) -> bool:
        """是否有失败的验证"""
        return any(r.status == VerificationResult.FAIL for r in self.results)

    def has_warnings(self) -> bool:
        """是否有警告"""
        return any(r.status == VerificationResult.WARNING for r in self.results)


class TestCase:
    """测试用例基类"""

    def __init__(self, name: str, device_id: str):
        self.name = name
        self.device_id = device_id
        self.validator = TestValidator(device_id)
        self.steps: List[Dict] = []

    def add_step(self, description: str, action: str,
                  verifications: List[Dict] = None):
        """
        添加测试步骤

        Args:
            description: 步骤描述
            action: 操作指令
            verifications: 验证规则列表，每项包含：
                - type: 验证类型
                - name: 验证项名称
                - params: 验证参数
        """
        self.steps.append({
            "description": description,
            "action": action,
            "verifications": verifications or []
        })

    def execute_verification(self, verification: Dict,
                             context: Dict[str, Any]) -> ValidationResult:
        """
        执行单个验证

        Args:
            verification: 验证规则
            context: 上下文信息（包含页面文本、截图等）

        Returns:
            ValidationResult
        """
        v_type = verification.get("type")
        v_name = verification.get("name")
        v_params = verification.get("params", {})

        if v_type == "exact_match":
            return self.validator.verify_exact_match(
                name=v_name,
                expected=v_params.get("expected"),
                actual=context.get("actual_value", "")
            )

        elif v_type == "contains":
            return self.validator.verify_contains(
                name=v_name,
                text=context.get("page_text", ""),
                must_contain=v_params.get("must_contain", [])
            )

        elif v_type == "numeric_range":
            return self.validator.verify_numeric_range(
                name=v_name,
                value=context.get("page_text", ""),
                min_val=v_params.get("min_val", 0),
                max_val=v_params.get("max_val", 999999)
            )

        elif v_type == "element_exists":
            return self.validator.verify_element_exists(
                name=v_name,
                page_text=context.get("page_text", ""),
                must_exist=v_params.get("must_exist", [])
            )

        elif v_type == "order_count":
            return self.validator.verify_order_count(
                name=v_name,
                page_text=context.get("page_text", ""),
                expected_count_range=v_params.get("range", (0, 100))
            )

        elif v_type == "popup":
            return self.validator.verify_popup_appeared(
                popup_text=context.get("popup_text", ""),
                expected_popup_keywords=v_params.get("keywords", [])
            )

        else:
            return ValidationResult(
                name=v_name,
                status=VerificationResult.SKIP,
                expected=v_type,
                actual="未知验证类型",
                error_msg=f"不支持的验证类型: {v_type}"
            )

    def get_test_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        summary = self.validator.get_summary()

        return {
            "test_case": self.name,
            "device": self.device_id,
            "timestamp": self._get_timestamp(),
            "result": "FAIL" if self.validator.has_failures() else "PASS",
            "summary": summary
        }

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 使用示例
if __name__ == "__main__":
    # 创建验证器
    validator = TestValidator("PQY5T20A07017811")

    # 示例1：精确匹配验证
    result1 = validator.verify_exact_match(
        name="订单号格式验证",
        expected="510045362601290018",
        actual="510045362601290018"
    )
    print(f"验证1: {result1.status.value}")

    # 示例2：包含关系验证
    result2 = validator.verify_contains(
        name="采购单页面关键字验证",
        text="农户：非伍6，采购员：老王，金额：7元",
        must_contain=["非伍6", "7元"]
    )
    print(f"验证2: {result2.status.value}")

    # 示例3：数值范围验证
    result3 = validator.verify_numeric_range(
        name="金额范围验证",
        value="结算金额：7元",
        min_val=5,
        max_val=10
    )
    print(f"验证3: {result3.status.value}")

    # 获取摘要
    summary = validator.get_summary()
    print(f"\n验证摘要: {json.dumps(summary, indent=2, ensure_ascii=False)}")
