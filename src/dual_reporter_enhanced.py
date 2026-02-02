#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双格式报告生成器 - 增强版
生成HTML + JSON双格式测试报告，支持截图显示
"""

import os
import json
import time
import base64
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from api_executor import ExecutionResult


@dataclass
class TestSummary:
    """测试汇总信息"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    timeouts: int = 0
    total_time: float = 0.0
    start_time: str = ""
    end_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "success_rate": f"{(self.passed/self.total*100):.1f}%" if self.total > 0 else "0%",
            "total_time": f"{self.total_time:.2f}秒",
            "start_time": self.start_time,
            "end_time": self.end_time
        }


class DualReporterEnhanced:
    """双格式报告生成器 - 增强版"""

    def __init__(self, output_dir: str = "test_reports"):
        """
        初始化报告生成器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = output_dir
        self.html_dir = os.path.join(output_dir, "html")
        self.json_dir = os.path.join(output_dir, "json")
        self.screenshot_dir = os.path.join(output_dir, "screenshots")

        # 创建目录
        os.makedirs(self.html_dir, exist_ok=True)
        os.makedirs(self.json_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def generate_device_error_report(
        self,
        error_result: Dict[str, Any],
        test_cases_info: List[Dict[str, Any]],
        config: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """生成设备错误报告"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # 准备报告数据
        report_data = {
            "summary": {
                "total": error_result.get("test_cases_count", 0),
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "timeouts": 0,
                "success_rate": "0%",
                "total_time": "0秒",
                "device_check_failed": True,
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "device_check": error_result.get("device_check", {}),
            "test_results": [],
            "config": config or {},
            "timestamp": timestamp
        }

        # 添加测试用例信息（未执行）
        for test_info in test_cases_info:
            report_data["test_results"].append({
                "execution": {
                    "test_id": test_info.get("test_id", ""),
                    "test_name": test_info.get("name", ""),
                    "status": "SKIPPED",
                    "error_message": "设备检查失败，测试未执行"
                },
                "test_case": test_info
            })

        # 生成JSON报告
        json_path = os.path.join(self.json_dir, f"device_error_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # 生成HTML报告
        html_path = os.path.join(self.html_dir, f"device_error_{timestamp}.html")
        self._generate_device_error_html(report_data, html_path)

        return {
            "json": json_path,
            "html": html_path
        }

    def generate_reports(
        self,
        execution_results: List[ExecutionResult],
        test_cases_info: List[Dict[str, Any]] = None,
        config: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        生成HTML和JSON报告

        Args:
            execution_results: 执行结果列表
            test_cases_info: 测试用例信息列表（可选）
            config: 配置信息（可选）

        Returns:
            生成的报告文件路径字典
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # 计算汇总信息
        summary = self._calculate_summary(execution_results)

        # 准备报告数据
        report_data = {
            "summary": summary.to_dict(),
            "test_results": [],
            "config": config or {},
            "timestamp": timestamp
        }

        # 合并执行结果和测试用例信息
        for i, result in enumerate(execution_results):
            test_info = test_cases_info[i] if test_cases_info and i < len(test_cases_info) else {}

            # 转换ExecutionResult为字典
            result_dict = result.__dict__ if hasattr(result, '__dict__') else result

            # 如果有截图，转换为base64用于HTML显示
            screenshot_base64 = ""
            if result.screenshot_path and os.path.exists(result.screenshot_path):
                with open(result.screenshot_path, 'rb') as f:
                    image_data = f.read()
                    screenshot_base64 = base64.b64encode(image_data).decode('utf-8')

            result_dict['screenshot_base64'] = screenshot_base64

            report_data["test_results"].append({
                "execution": result_dict,
                "test_case": test_info
            })

        # 生成JSON报告
        json_path = os.path.join(self.json_dir, f"test_report_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # 生成HTML报告
        html_path = os.path.join(self.html_dir, f"test_report_{timestamp}.html")
        self._generate_html_report(report_data, html_path)

        return {
            "json": json_path,
            "html": html_path
        }

    def _calculate_summary(self, execution_results: List[ExecutionResult]) -> TestSummary:
        """计算测试汇总信息"""
        summary = TestSummary()

        if execution_results:
            summary.start_time = min(r.start_time for r in execution_results)
            summary.end_time = max(r.end_time for r in execution_results)
            summary.total = len(execution_results)

            for result in execution_results:
                summary.total_time += result.execution_time
                if result.status == "PASS":
                    summary.passed += 1
                elif result.status == "FAIL":
                    summary.failed += 1
                elif result.status == "ERROR":
                    summary.errors += 1
                elif result.status == "TIMEOUT":
                    summary.timeouts += 1

        return summary

    def _generate_html_report(self, report_data: Dict[str, Any], output_path: str):
        """生成HTML报告"""
        html_content = self._build_html_content(report_data)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def _build_html_content(self, report_data: Dict[str, Any]) -> str:
        """构建HTML内容"""
        summary = report_data["summary"]
        test_results = report_data["test_results"]

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoGLM 测试报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        .header .timestamp {{
            opacity: 0.9;
            font-size: 1.1em;
        }}

        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}

        .summary-card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            transition: transform 0.2s;
        }}

        .summary-card:hover {{
            transform: translateY(-5px);
        }}

        .summary-card .label {{
            color: #6c757d;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}

        .summary-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}

        .summary-card.pass .value {{ color: #28a745; }}
        .summary-card.fail .value {{ color: #dc3545; }}
        .summary-card.error .value {{ color: #ffc107; }}

        .test-results {{
            padding: 30px;
        }}

        .test-result {{
            border: 1px solid #e9ecef;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        }}

        .test-result-header {{
            padding: 15px 20px;
            background: #f8f9fa;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .test-result-header:hover {{
            background: #e9ecef;
        }}

        .test-result-header .test-info {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .test-result-header .status {{
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }}

        .test-result-header .status.pass {{
            background: #d4edda;
            color: #155724;
        }}

        .test-result-header .status.fail {{
            background: #f8d7da;
            color: #721c24;
        }}

        .test-result-header .status.error {{
            background: #fff3cd;
            color: #856404;
        }}

        .test-result-header .status.timeout {{
            background: #fce4ec;
            color: #880e4f;
        }}

        .test-result-body {{
            padding: 20px;
            display: none;
        }}

        .test-result-body.show {{
            display: block;
        }}

        .detail-section {{
            margin-bottom: 20px;
        }}

        .detail-section h3 {{
            color: #495057;
            font-size: 1.1em;
            margin-bottom: 10px;
            padding-bottom: 5px;
            border-bottom: 2px solid #667eea;
        }}

        .detail-row {{
            display: flex;
            margin-bottom: 10px;
        }}

        .detail-row .label {{
            font-weight: bold;
            width: 120px;
            color: #495057;
            flex-shrink: 0;
        }}

        .detail-row .value {{
            color: #6c757d;
            word-break: break-word;
        }}

        .test-steps {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 10px;
        }}

        .test-steps ol {{
            margin: 0;
            padding-left: 20px;
        }}

        .test-steps li {{
            margin-bottom: 5px;
            color: #495057;
        }}

        .expected-results {{
            background: #e7f3ff;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 10px;
        }}

        .expected-results ul {{
            margin: 0;
            padding-left: 20px;
        }}

        .expected-results li {{
            margin-bottom: 5px;
            color: #495057;
        }}

        .screenshot-container {{
            text-align: center;
            margin: 20px 0;
        }}

        .screenshot-container img {{
            max-width: 100%;
            max-height: 600px;
            border-radius: 5px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border: 1px solid #dee2e6;
        }}

        .validation-details {{
            margin-top: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
        }}

        .validation-item {{
            padding: 8px 0;
            border-bottom: 1px solid #dee2e6;
        }}

        .validation-item:last-child {{
            border-bottom: none;
        }}

        .footer {{
            padding: 20px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
            border-top: 1px solid #e9ecef;
        }}

        .toggle-icon {{
            transition: transform 0.3s;
        }}

        .toggle-icon.rotate {{
            transform: rotate(180deg);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AutoGLM 测试报告</h1>
            <div class="timestamp">生成时间: {report_data["timestamp"]}</div>
        </div>

        <div class="summary">
            <div class="summary-card">
                <div class="label">总用例数</div>
                <div class="value">{summary['total']}</div>
            </div>
            <div class="summary-card {'pass' if summary['passed'] > 0 else ''}">
                <div class="label">通过</div>
                <div class="value">{summary['passed']}</div>
            </div>
            <div class="summary-card {'fail' if summary['failed'] > 0 else ''}">
                <div class="label">失败</div>
                <div class="value">{summary['failed']}</div>
            </div>
            <div class="summary-card {'error' if summary['errors'] > 0 else ''}">
                <div class="label">错误</div>
                <div class="value">{summary['errors']}</div>
            </div>
            <div class="summary-card">
                <div class="label">通过率</div>
                <div class="value">{summary['success_rate']}</div>
            </div>
            <div class="summary-card">
                <div class="label">总耗时</div>
                <div class="value">{summary['total_time']}</div>
            </div>
        </div>

        <div class="test-results">
            <h2 style="margin-bottom: 20px; color: #495057;">测试结果详情</h2>
"""

        # 添加每个测试用例的结果
        for i, result in enumerate(test_results):
            exec_result = result["execution"]
            test_case = result.get("test_case", {})

            status_class = exec_result.get("status", "unknown").lower()
            if status_class == "completed":
                status_class = "pass" if exec_result.get("validation_passed", False) else "fail"

            # 构建测试步骤HTML
            steps_html = ""
            if test_case.get("task_command"):
                steps = test_case["task_command"].split(". ")
                steps_html = "<div class='test-steps'><h3>测试步骤：</h3><ol>"
                for step in steps:
                    steps_html += f"<li>{step.strip()}</li>"
                steps_html += "</ol></div>"

            # 构建预期结果HTML
            expected_html = ""
            if test_case.get("expected_results"):
                expected_html = "<div class='expected-results'><h3>预期结果：</h3><ul>"
                for expected in test_case["expected_results"]:
                    expected_html += f"<li>{expected}</li>"
                expected_html += "</ul></div>"

            # 截图HTML（仅失败时显示）
            screenshot_html = ""
            if exec_result.get("screenshot_path") and exec_result.get("screenshot_base64") and status_class == "fail":
                screenshot_html = f"""
                <div class="screenshot-container">
                    <h3>失败截图：</h3>
                    <img src="data:image/png;base64,{exec_result.get('screenshot_base64')}" alt="失败截图">
                </div>
                """

            html += f"""
            <div class="test-result">
                <div class="test-result-header" onclick="toggleResult({i})">
                    <div class="test-info">
                        <span class="status {status_class}">{exec_result.get('status', 'UNKNOWN')}</span>
                        <strong>{exec_result.get('test_name', 'Unknown')}</strong>
                        <span style="color: #6c757d;">({exec_result.get('test_id', '')})</span>
                    </div>
                    <div>
                        <span>耗时: {exec_result.get('execution_time', 0):.2f}秒</span>
                        <span class="toggle-icon" id="icon-{i}">▼</span>
                    </div>
                </div>
                <div class="test-result-body" id="body-{i}">
                    <div class="detail-section">
                        <h3>基本信息</h3>
                        <div class="detail-row">
                            <span class="label">测试ID:</span>
                            <span class="value">{exec_result.get('test_id', '')}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">设备ID:</span>
                            <span class="value">{exec_result.get('device_id', '')}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">开始时间:</span>
                            <span class="value">{exec_result.get('start_time', '')}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">结束时间:</span>
                            <span class="value">{exec_result.get('end_time', '')}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">执行步数:</span>
                            <span class="value">{exec_result.get('steps_taken', 0)}</span>
                        </div>
                    </div>

                    {steps_html}

                    {expected_html}

                    {screenshot_html}
"""

            # 如果有错误信息
            if exec_result.get("error_message"):
                html += f"""
                    <div class="detail-section">
                        <h3>错误信息</h3>
                        <div class="detail-row">
                            <span class="value" style="color: #dc3545;">{exec_result.get('error_message', '')}</span>
                        </div>
                    </div>
"""

            # 如果有验证详情
            if exec_result.get("validation_details"):
                html += self._build_validation_html(exec_result["validation_details"])

            html += """
                </div>
            </div>
"""

        html += """
        </div>

        <div class="footer">
            <p>Generated by AutoGLM Test Framework</p>
        </div>
    </div>

    <script>
        function toggleResult(index) {
            const body = document.getElementById('body-' + index);
            const icon = document.getElementById('icon-' + index);

            if (body.classList.contains('show')) {
                body.classList.remove('show');
                icon.classList.remove('rotate');
            } else {
                body.classList.add('show');
                icon.classList.add('rotate');
            }
        }

        // 默认展开失败/错误的测试
        document.addEventListener('DOMContentLoaded', function() {
            const failedTests = document.querySelectorAll('.test-result-header .status.fail, .test-result-header .status.error, .test-result-header .status.timeout');
            if (failedTests.length > 0) {
                failedTests[0].click();
            }
        });
    </script>
</body>
</html>
"""
        return html

    def _build_validation_html(self, validation_details: Dict[str, Any]) -> str:
        """构建验证详情HTML"""
        html = '<div class="validation-details">'
        html += f'<strong>验证详情: {validation_details.get("passed_checks", 0)}/{validation_details.get("total_checks", 0)} 通过</strong>'

        for detail in validation_details.get("details", []):
            status_icon = "✅" if detail.get("passed", False) else "❌"
            html += f'''
            <div class="validation-item">
                {status_icon} <strong>{detail.get("type", "")}:</strong> {detail.get("message", detail.get("expected", ""))}
            </div>
            '''

        html += '</div>'
        return html

    def _generate_device_error_html(self, report_data: Dict[str, Any], output_path: str):
        """生成设备错误HTML报告"""
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoGLM 设备错误报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 40px;
        }}

        .error-icon {{
            font-size: 4em;
            text-align: center;
            margin-bottom: 20px;
        }}

        h1 {{
            color: #dc3545;
            text-align: center;
            margin-bottom: 30px;
        }}

        .error-list {{
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}

        .error-list h3 {{
            color: #721c24;
            margin-bottom: 10px;
        }}

        .error-list ul {{
            margin-left: 20px;
        }}

        .error-list li {{
            margin-bottom: 5px;
            color: #721c24;
        }}

        .device-info {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}

        .device-info h3 {{
            margin-bottom: 10px;
            color: #495057;
        }}

        .test-cases {{
            background: #fff;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 20px;
        }}

        .test-case {{
            padding: 10px 0;
            border-bottom: 1px solid #dee2e6;
        }}

        .test-case:last-child {{
            border-bottom: none;
        }}

        .test-case .badge {{
            display: inline-block;
            padding: 2px 8px;
            background: #6c757d;
            color: white;
            border-radius: 3px;
            font-size: 0.85em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">⚠️</div>
        <h1>设备检查失败</h1>

        <div class="error-list">
            <h3>错误信息:</h3>
            <ul>
"""

        for error in report_data.get("device_check", {}).get("errors", []):
            html += f"                <li>{error}</li>\n"

        html += """            </ul>
        </div>
"""

        if report_data.get("device_check", {}).get("devices"):
            html += """
        <div class="device-info">
            <h3>检测到的设备:</h3>
"""
            for device in report_data["device_check"]["devices"]:
                status_icon = "✓" if device.get("status") == "device" else "✗"
                html += f"            <p>{status_icon} <strong>{device['device_id']}</strong> - {device.get('model', 'Unknown')}</p>\n"

            html += """        </div>
"""

        if report_data.get("test_results"):
            html += """
        <div class="test-cases">
            <h3>测试用例（未执行）:</h3>
"""
            for result in report_data["test_results"]:
                test_case = result.get("test_case", {})
                html += f"""
            <div class="test-case">
                <span class="badge">{test_case.get("test_id", "")}</span>
                <strong>{test_case.get("name", "")}</strong>
                <br>
                <small style="color: #6c757d;">{test_case.get("type", "")} | {test_case.get("priority", "")}</small>
            </div>
"""

            html += """        </div>
"""

        html += """
    </div>

    <div style="text-align: center; margin-top: 30px; color: #6c757d;">
        <p>请检查：</p>
        <ul style="text-align: left; display: inline-block;">
            <li>设备是否已连接并开启USB调试</li>
            <li>设备是否已授权此电脑进行USB调试</li>
            <li>adb服务是否正常运行</li>
        </ul>
    </div>
</body>
</html>
"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)


# 创建别名
DualReporter = DualReporterEnhanced
