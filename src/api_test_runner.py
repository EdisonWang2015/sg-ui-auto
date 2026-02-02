#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoGLM API测试运行器 - 主控制器
支持CSV测试用例管理、直接API调用、HTML+JSON双格式报告
"""

import argparse
import sys
import os
import time
from typing import Optional, List, Union

from test_config import load_config, TestFrameworkConfig
from unified_case_manager import UnifiedTestCaseManager
from csv_case_manager import APITestCase
from api_executor import APIExecutor, ExecutionResult
from enhanced_validator import EnhancedValidator
from dual_reporter_enhanced import DualReporter


class APITestRunner:
    """API测试运行器 - 主控制器"""

    def __init__(self, config: TestFrameworkConfig):
        """
        初始化测试运行器

        Args:
            config: 测试框架配置
        """
        self.config = config
        self.executor = APIExecutor(config)
        self.validator = EnhancedValidator("default")
        self.reporter = DualReporter(config.reporting.output_dir)

    def _check_devices(self) -> dict:
        """
        检查设备可用性

        Returns:
            设备检查结果字典
        """
        import subprocess
        from phone_agent.device_factory import get_device_factory

        result = {
            "available": False,
            "devices": [],
            "errors": []
        }

        try:
            device_factory = get_device_factory()
            devices = device_factory.list_devices()

            if not devices:
                result["errors"].append("未找到已连接的设备")
                return result

            for device in devices:
                device_info = {
                    "device_id": device.device_id,
                    "status": device.status,
                    "model": getattr(device, 'model', 'Unknown'),
                    "name": getattr(device, 'device_name', 'Unknown')
                }

                if device.status != "device":
                    result["errors"].append(f"设备 {device.device_id} 状态异常: {device.status}")
                else:
                    # 测试截图功能是否正常
                    try:
                        screenshot = device_factory.get_screenshot(device.device_id)
                        device_info["screenshot_ok"] = True
                    except Exception as e:
                        device_info["screenshot_ok"] = False
                        result["errors"].append(f"设备 {device.device_id} 截图失败: {str(e)}")

                result["devices"].append(device_info)

            # 只要有至少一个可用设备就返回成功
            result["available"] = any(
                d["status"] == "device" and d.get("screenshot_ok", False)
                for d in result["devices"]
            )

        except Exception as e:
            result["errors"].append(f"设备检查异常: {str(e)}")

        return result

    def run_tests(
        self,
        csv_files: Union[str, List[str]],
        tags: Optional[str] = None,
        test_type: Optional[str] = None,
        priority: Optional[str] = None,
        device_id: Optional[str] = None,
        max_workers: int = 1,
        skip_device_check: bool = False
    ) -> dict:
        """
        运行测试

        Args:
            csv_files: CSV/Excel测试用例文件（支持单个文件路径或文件列表）
            tags: 标签筛选
            test_type: 类型筛选
            priority: 优先级筛选
            device_id: 设备ID筛选
            max_workers: 最大并发数

        Returns:
            测试结果字典
        """
        print(f"\n{'='*60}")
        print(f"AutoGLM API 测试运行器")
        print(f"{'='*60}\n")

        # 1. 加载测试用例（支持多文件）
        if isinstance(csv_files, str):
            files_str = csv_files
        else:
            files_str = ', '.join(csv_files)

        print(f"正在加载测试用例: {files_str}")
        case_manager = UnifiedTestCaseManager(csv_files)
        case_manager.show_summary()

        # 2. 筛选测试用例
        test_cases = case_manager.filter_by_criteria(
            tags=tags,
            test_type=test_type,
            priority=priority,
            device_id=device_id
        )

        if not test_cases:
            print("❌ 没有匹配的测试用例")
            return {"success": False, "message": "没有匹配的测试用例"}

        print(f"\n筛选后将执行 {len(test_cases)} 个测试用例")

        # 3. 设备检查
        if not skip_device_check:
            print(f"\n检查设备可用性...")
            device_check = self._check_devices()

            if not device_check["available"]:
                print(f"❌ 设备检查失败:")
                for error in device_check["errors"]:
                    print(f"  - {error}")

                # 生成包含设备错误的报告
                device_error_result = {
                    "success": False,
                    "message": "设备检查失败",
                    "device_check": device_check,
                    "test_cases_count": len(test_cases)
                }

                # 生成报告
                test_cases_info = [tc.to_dict() for tc in test_cases]
                self.reporter.generate_device_error_report(
                    device_error_result,
                    test_cases_info,
                    self.config.to_dict()
                )

                return device_error_result

            print(f"✅ 设备检查通过:")
            for device in device_check["devices"]:
                status_icon = "✓" if device["status"] == "device" and device.get("screenshot_ok") else "✗"
                print(f"  {status_icon} {device['device_id']} - {device.get('model', 'Unknown')}")

        # 4. 显示执行计划
        self._show_execution_plan(test_cases, max_workers)

        # 5. 执行测试
        start_time = time.time()

        # 进度回调
        def progress_callback(test_id: str, message: str):
            print(f"[{test_id}] {message}")

        execution_results = self.executor.execute_batch(
            test_cases,
            max_workers=max_workers,
            progress_callback=progress_callback
        )

        # 6. 验证结果
        validated_results = self._validate_results(test_cases, execution_results)

        # 7. 生成报告
        test_cases_info = [tc.to_dict() for tc in test_cases]
        report_paths = self.reporter.generate_reports(
            validated_results,
            test_cases_info,
            self.config.to_dict()
        )

        total_time = time.time() - start_time

        # 8. 显示汇总
        self._print_final_summary(validated_results, total_time, report_paths)

        return {
            "success": True,
            "total": len(validated_results),
            "passed": sum(1 for r in validated_results if r.status == "PASS"),
            "failed": sum(1 for r in validated_results if r.status in ["FAIL", "ERROR", "TIMEOUT"]),
            "reports": report_paths
        }

    def _show_execution_plan(self, test_cases: List[APITestCase], max_workers: int):
        """显示执行计划"""
        print(f"\n执行计划:")
        print(f"  - 测试用例数: {len(test_cases)}")
        print(f"  - 并发数: {max_workers}")

        # 按设备分组
        device_groups: dict = {}
        for tc in test_cases:
            if tc.device_id not in device_groups:
                device_groups[tc.device_id] = []
            device_groups[tc.device_id].append(tc)

        print(f"  - 涉及设备: {len(device_groups)}个")
        for device_id, cases in device_groups.items():
            print(f"    * {device_id}: {len(cases)}个用例")

        print(f"  - 继续执行失败: {'是' if self.config.execution.continue_on_failure else '否'}")

    def _validate_results(
        self,
        test_cases: List[APITestCase],
        execution_results: List[ExecutionResult]
    ) -> List[ExecutionResult]:
        """验证执行结果"""
        validated_results = []

        for i, result in enumerate(execution_results):
            test_case = test_cases[i]

            # 如果执行出错或超时，直接跳过验证
            if result.status in ["ERROR", "TIMEOUT"]:
                validated_results.append(result)
                continue

            # 验证输出
            validation_result = self.validator.validate_autoGLM_result(
                result.output,
                test_case.expected_results,
                test_case.test_data
            )

            # 更新验证状态
            result.validation_passed = validation_result.all_passed
            result.validation_details = validation_result.to_dict()

            # 根据验证结果更新状态
            if result.validation_passed:
                result.status = "PASS"
            else:
                result.status = "FAIL"
                # 保存失败截图
                screenshot_path = self.executor._save_failure_screenshot(test_case)
                result.screenshot_path = screenshot_path

            validated_results.append(result)

        return validated_results

    def _print_final_summary(
        self,
        results: List[ExecutionResult],
        total_time: float,
        report_paths: dict
    ):
        """打印最终汇总"""
        total = len(results)
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        errors = sum(1 for r in results if r.status in ["ERROR", "TIMEOUT"])

        print(f"\n{'='*60}")
        print(f"测试执行完成")
        print(f"{'='*60}")
        print(f"总用例数: {total}")
        print(f"通过: {passed} ({(passed/total*100):.1f}%)" if total > 0 else "通过: 0")
        print(f"失败: {failed}")
        print(f"错误: {errors}")
        print(f"总耗时: {total_time:.2f}秒")
        print(f"\n报告已生成:")
        print(f"  HTML: {report_paths['html']}")
        print(f"  JSON: {report_paths['json']}")
        print(f"{'='*60}\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="AutoGLM API测试运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法（CSV文件）
  python api_test_runner.py --csv test_cases.csv

  # 基本用法（Excel文件）
  python api_test_runner.py --csv test_cases.xlsx

  # 多文件支持（混合CSV和Excel）
  python api_test_runner.py --csv test_cases.csv additional_cases.xlsx

  # 只运行smoke测试
  python api_test_runner.py --csv test_cases.csv --filter-tags smoke

  # 指定设备和并发数
  python api_test_runner.py --csv test_cases.csv --device-id PQY5T20A07017811 --max-workers 2

  # 失败后继续执行
  python api_test_runner.py --csv test_cases.csv --continue-on-failure

  # 使用自定义配置文件
  python api_test_runner.py --csv test_cases.csv --config my_config.yaml
        """
    )

    # 必需参数
    parser.add_argument(
        "--csv",
        dest="csv_files",
        nargs="+",
        required=True,
        help="测试用例文件路径（支持多个CSV/Excel文件）"
    )

    # 筛选参数
    parser.add_argument(
        "--filter-tags",
        help="按标签筛选（逗号分隔，如：smoke,regression）"
    )
    parser.add_argument(
        "--filter-type",
        help="按类型筛选（purchase/sales/mixed）"
    )
    parser.add_argument(
        "--filter-priority",
        help="按优先级筛选（P0/P1/P2/P3）"
    )
    parser.add_argument(
        "--device-id",
        help="指定设备ID"
    )

    # 执行参数
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="最大并发数（默认: 1）"
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="失败后继续执行"
    )
    parser.add_argument(
        "--skip-device-check",
        action="store_true",
        help="跳过设备检查（不推荐）"
    )

    # 配置参数
    parser.add_argument(
        "--config",
        help="配置文件路径（YAML格式）"
    )
    parser.add_argument(
        "--output-dir",
        default="test_reports",
        help="报告输出目录（默认: test_reports）"
    )

    # 其他参数
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出"
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 命令行参数覆盖配置
    if args.output_dir:
        config.reporting.output_dir = args.output_dir
    if args.continue_on_failure:
        config.execution.continue_on_failure = True
    if args.max_workers:
        config.execution.max_workers = args.max_workers

    # 检查测试用例文件是否存在
    missing_files = [f for f in args.csv_files if not os.path.exists(f)]
    if missing_files:
        print(f"❌ 测试用例文件不存在:")
        for f in missing_files:
            print(f"  - {f}")
        sys.exit(1)

    # 检查API密钥
    if not config.api.api_key or config.api.api_key == "EMPTY":
        print("⚠️  警告: 未设置API密钥，请通过环境变量 AUTOGLM_API_KEY 或配置文件设置")

    # 创建测试运行器
    runner = APITestRunner(config)

    # 运行测试
    try:
        result = runner.run_tests(
            csv_files=args.csv_files,
            tags=args.filter_tags,
            test_type=args.filter_type,
            priority=args.filter_priority,
            device_id=args.device_id,
            max_workers=args.max_workers,
            skip_device_check=args.skip_device_check
        )

        # 根据结果返回退出码
        if result["success"]:
            sys.exit(0 if result["failed"] == 0 else 1)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 测试执行异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
