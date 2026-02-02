#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强测试验证器
继承test_validator.py，增强AutoGLM特定验证逻辑
"""

import os
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
        self._keyword_cache = {}  # 关键词提取缓存

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
        关键词验证（使用 LLM 智能提取关键词）

        Args:
            output: AutoGLM输出
            expected: 预期关键词

        Returns:
            验证结果字典
        """
        clean_expected = expected.lstrip('✅❌⚠️')

        # 使用 LLM 提取关键词
        try:
            keywords = self._extract_keywords_with_llm(clean_expected)
        except Exception as e:
            # 如果 LLM 失败，回退到规则提取
            print(f"[INFO] LLM 关键词提取失败，使用规则提取: {e}")
            keywords_str = self._extract_keywords_with_rules(clean_expected)
            keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]

        # 验证所有关键词是否都在输出中
        found_keywords = [kw for kw in keywords if kw in output]
        passed = len(found_keywords) == len(keywords)

        return {
            "type": AutoGLMValidationType.KEYWORD.value,
            "expected": expected,
            "actual": f"找到关键词: {found_keywords}",
            "passed": passed,
            "message": f"关键词匹配 {len(found_keywords)}/{len(keywords)}",
            "keywords": {
                "extracted_by": "LLM" if found_keywords else "Rule-based",
                "expected": keywords,
                "found": found_keywords,
                "missing": [kw for kw in keywords if kw not in output]
            }
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

    def _extract_keywords_with_llm(self, expected: str) -> List[str]:
        """
        使用 LLM 从预期结果中提取关键验证点

        Args:
            expected: 预期结果描述（如："验证页面底部出现'新建采购单'按钮"）

        Returns:
            关键词列表（如：["新建采购单", "按钮"]）
        """
        # 检查缓存
        if expected in self._keyword_cache:
            return self._keyword_cache[expected]

        prompt = f"""从以下测试预期结果中提取关键验证点（只返回关键词，用逗号分隔）：

预期结果：{expected}

提取规则：
1. 提取需要验证的核心元素（如：采购单、按钮、金额等）
2. 移除无关的描述性词语（如：验证、页面、底部、出现等）
3. 提取引号中的内容
4. 只返回关键词，不要解释

示例：
输入: "验证页面底部出现'新建采购单'按钮"
输出: 新建采购单, 按钮

输入: "跳转后的页面，顶部有'采购单'文字显示"
输出: 采购单

输入: "页面显示'订单数量：5'"
输出: 订单数量, 5
"""

        try:
            response = self._call_llm_api(prompt)
            keywords = [kw.strip() for kw in response.split(',') if kw.strip()]

            # 保存到缓存
            self._keyword_cache[expected] = keywords
            return keywords

        except Exception as e:
            print(f"[INFO] LLM 关键词提取失败，使用规则提取: {e}")
            keywords_str = self._extract_keywords_with_rules(expected)
            keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
            self._keyword_cache[expected] = keywords
            return keywords

    def _call_llm_api(self, prompt: str, model: str = "glm-4-flash") -> str:
        """
        调用智谱 AI API 进行关键词提取

        Args:
            prompt: 提示词
            model: 模型名称（默认使用 glm-4-flash，速度快且便宜）

        Returns:
            LLM 响应文本
        """
        try:
            from zhipuai import ZhipuAI

            # 优先从环境变量获取 API key，否则从配置文件读取
            api_key = os.getenv("ZHIPUAI_API_KEY")

            if not api_key:
                # 从配置文件读取 API key
                try:
                    import yaml
                    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.yaml')
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        api_key = config.get('api', {}).get('api_key', '')
                except Exception as e:
                    print(f"[INFO] 无法从配置文件读取 API key: {e}")

            if not api_key:
                raise ValueError("ZHIPUAI_API_KEY 环境变量未设置且配置文件中也未找到")

            client = ZhipuAI(api_key=api_key)

            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                max_tokens=100,
                temperature=0,  # 使用低温度以获得一致的输出
            )

            return response.choices[0].message.content

        except Exception as e:
            # 如果 LLM 调用失败，抛出异常让调用方处理
            print(f"[WARNING] 智谱 AI API 调用失败: {e}，使用规则提取作为后备")
            raise e

    def _extract_keywords_with_rules(self, text: str) -> str:
        """
        使用规则提取关键词（LLM 的后备方案）

        Args:
            text: 预期结果文本

        Returns:
            逗号分隔的关键词字符串
        """
        keywords = []

        # 1. 提取引号内容（支持英文和中文引号）
        # 英文引号
        keywords.extend(re.findall(r'"([^"]+)"', text))
        keywords.extend(re.findall(r"'([^']+)'", text))
        # 中文引号 "" (U+201C, U+201D)
        chinese_left_quote = chr(8220)   # "
        chinese_right_quote = chr(8221)  # "
        keywords.extend(re.findall(f'{re.escape(chinese_left_quote)}([^{re.escape(chinese_right_quote)}]+){re.escape(chinese_right_quote)}', text))
        # 中文引号 '' (U+2018, U+2019)
        chinese_single_left = chr(8216)  # '
        chinese_single_right = chr(8217) # '
        keywords.extend(re.findall(f'{re.escape(chinese_single_left)}([^{re.escape(chinese_single_right)}]+){re.escape(chinese_single_right)}', text))

        # 2. 如果没有提取到引号内容，使用简单规则
        if not keywords:
            # 移除常见的无意义词
            stop_words = {
                "验证", "检查", "确认", "显示", "出现", "页面", "底部", "顶部",
                "是否有", "是否", "应该", "需要", "包含", "存在", "跳转后", "的"
            }

            # 分词（简单按空格和标点分割）
            words = re.split(r'[,，.。、\s]+', text)
            keywords = [w for w in words if w and w not in stop_words and len(w) > 1]

        # 去重并返回
        unique_keywords = list(dict.fromkeys(keywords))
        return ", ".join(unique_keywords)

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
