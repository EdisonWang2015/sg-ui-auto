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
        # 导入 DeviceService
        from device_service import DeviceService
        self.device_service = DeviceService(config)
        self.executor = APIExecutor(config, self.device_service)
        self.validator = EnhancedValidator("default")
        self.reporter = DualReporter(config.reporting.output_dir)

    def _check_devices(self) -> dict:
        """
        检查设备可用性

        Returns:
            设备检查结果字典
        """
        result = self.device_service.check_devices()

        # 转换为旧格式以保持向后兼容
        return {
            "available": result.available,
            "devices": [
                {
                    "device_id": d.device_id,
                    "status": d.status,
                    "model": d.model,
                    "name": d.name,
                    "screenshot_ok": d.screenshot_ok
                }
                for d in result.devices
            ],
            "errors": result.errors
        }

    def _validate_test_cases_before_execution(self, test_cases: List[APITestCase]):
        """
        执行前验证测试用例
        检查指令长度、操作步骤数等，给出警告或自动拆分
        """
        from test_case_validator import TestCaseValidator, ComplexityLevel

        validator = TestCaseValidator(config=self.config)
        total_warnings = 0
        over_complex_count = 0
        auto_split_count = 0

        for tc in test_cases:
            # 保存原始指令
            if not hasattr(tc, 'original_command') or not tc.original_command:
                tc.original_command = tc.task_command

            # 分析指令
            analysis = validator.analyze_command(tc.task_command)

            # 输出警告
            if analysis.warnings:
                total_warnings += len(analysis.warnings)
                print(f"  ⚠️  {tc.test_id}: {', '.join(analysis.warnings)}")

            # 统计过于复杂的用例
            if analysis.estimated_complexity == ComplexityLevel.OVER_COMPLEX:
                over_complex_count += 1

            # 如果配置了自动拆分且可以拆分
            if self.config.execution.auto_split and analysis.can_split and analysis.suggested_splits:
                tc.auto_split_commands = analysis.suggested_splits
                auto_split_count += 1
                print(f"  📝 {tc.test_id}: 自动拆分为 {len(analysis.suggested_splits)} 个子指令")

        # 输出汇总
        if total_warnings > 0:
            print(f"\n[校验汇总] 发现 {total_warnings} 个潜在问题")
            if over_complex_count > 0:
                print(f"  - {over_complex_count} 个用例过于复杂，建议拆分")
            if auto_split_count > 0:
                print(f"  - {auto_split_count} 个用例已自动拆分")
        else:
            print(f"✅ 所有测试用例校验通过")

    def _resolve_dependencies(self, test_cases: List[APITestCase]) -> List[List[APITestCase]]:
        """
        解析依赖关系，返回可以并行执行的批次

        Args:
            test_cases: 测试用例列表

        Returns:
            每个批次是可以并行执行的用例列表，批次之间需要串行执行

        Raises:
            ValueError: 如果检测到循环依赖或无法满足的依赖
        """
        # 构建依赖映射
        dependency_map = {tc.test_id: tc.depends_on for tc in test_cases}
        resolved = []
        remaining = set(tc.test_id for tc in test_cases)
        test_case_dict = {tc.test_id: tc for tc in test_cases}

        max_iterations = len(test_cases) + 1  # 防止无限循环
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1

            # 找出没有未满足依赖的用例
            ready = []
            for tc in test_cases:
                if tc.test_id in remaining:
                    deps = dependency_map.get(tc.test_id, [])
                    # 检查所有依赖是否都已满足
                    if all(dep not in remaining for dep in deps):
                        ready.append(tc)

            if not ready:
                # 没有可执行的用例，可能存在循环依赖
                raise ValueError(f"检测到循环依赖或无法满足的依赖，剩余用例: {remaining}")

            resolved.append(ready)
            for tc in ready:
                remaining.remove(tc.test_id)

        if remaining:
            raise ValueError(f"无法解析依赖关系，剩余用例: {remaining}")

        # 打印执行批次信息
        if len(resolved) > 1:
            print(f"\n[依赖解析] 用例分为 {len(resolved)} 个批次:")
            for i, batch in enumerate(resolved, 1):
                batch_ids = [tc.test_id for tc in batch]
                print(f"  批次 {i}: {', '.join(batch_ids)}")

        return resolved

    def run_tests(
        self,
        csv_files: Union[str, List[str]],
        tags: Optional[str] = None,
        test_type: Optional[str] = None,
        priority: Optional[str] = None,
        device_id: Optional[str] = None,
        max_workers: int = 1,
        skip_device_check: bool = False,
        allocator: Optional['DeviceAllocator'] = None
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
            skip_device_check: 是否跳过设备检查
            allocator: 设备分配器（可选）

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
        case_manager = UnifiedTestCaseManager(csv_files, config=self.config)
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

        # 2.5 执行前校验测试用例（如果配置启用）
        if self.config.execution.validate_commands:
            print(f"\n[测试用例校验]")
            self._validate_test_cases_before_execution(test_cases)

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

        # 4. 设备动态分配
        allocated_test_cases = []
        if allocator:
            print(f"\n[设备动态分配]")
            for tc in test_cases:
                # 保存原始设备ID
                if not hasattr(tc, 'original_device_id'):
                    tc.original_device_id = tc.device_id
                # 分配新设备
                allocated_device_id = allocator.allocate(tc)
                tc.device_id = allocated_device_id
                allocated_test_cases.append(tc)

            # 显示分配计划
            allocation_summary = allocator.get_allocation_summary()
            print(f"分配计划:")
            for device_id, count in allocation_summary.items():
                if count > 0:
                    print(f"  {device_id}: {count} 个用例")
        else:
            allocated_test_cases = test_cases

        # 5. 显示执行计划
        self._show_execution_plan(allocated_test_cases, max_workers)

        # 6. 解析依赖关系并分批执行
        try:
            batches = self._resolve_dependencies(allocated_test_cases)
        except ValueError as e:
            print(f"\n❌ 依赖解析失败: {e}")
            return {"success": False, "message": str(e)}

        # 7. 分批执行测试
        start_time = time.time()
        all_execution_results = []

        # 进度回调
        def progress_callback(test_id: str, message: str):
            print(f"[{test_id}] {message}")

        for batch_idx, batch in enumerate(batches, 1):
            if len(batches) > 1:
                print(f"\n{'='*60}")
                print(f"执行批次 {batch_idx}/{len(batches)}（{len(batch)} 个用例）")
                print(f"{'='*60}")

            execution_results = self.executor.execute_batch(
                batch,
                max_workers=max_workers,
                progress_callback=progress_callback
            )
            all_execution_results.extend(execution_results)

            # 检查是否继续执行下一批
            if not self.config.execution.continue_on_failure:
                if any(r.status in ["ERROR", "TIMEOUT"] for r in execution_results):
                    print(f"\n批次执行失败，停止后续批次")
                    # 取消未执行的批次
                    remaining_batches = len(batches) - batch_idx
                    if remaining_batches > 0:
                        print(f"剩余 {remaining_batches} 个批次已被取消")
                    break

        execution_results = all_execution_results

        # 8. 验证结果
        validated_results = self._validate_results(allocated_test_cases, execution_results)

        # 9. 生成报告
        test_cases_info = [tc.to_dict() for tc in allocated_test_cases]
        report_paths = self.reporter.generate_reports(
            validated_results,
            test_cases_info,
            self.config.to_dict()
        )

        total_time = time.time() - start_time

        # 10. 显示汇总
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

        # 构建test_id到test_case的映射，避免并发导致顺序错乱
        test_case_map = {tc.test_id: tc for tc in test_cases}

        for result in execution_results:
            # 使用test_id匹配，而不是索引
            test_case = test_case_map.get(result.test_id)

            if test_case is None:
                print(f"⚠️  警告: 找不到test_id为{result.test_id}的测试用例")
                validated_results.append(result)
                continue

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

  # 多设备并发执行（自动分配设备）
  python api_test_runner.py --csv test_cases.csv --max-workers 2 --force-allocate

  # 使用最少负载分配策略
  python api_test_runner.py --csv test_cases.csv --max-workers 3 --allocation-strategy least_loaded --force-allocate

  # 失败后继续执行
  python api_test_runner.py --csv test_cases.csv --continue-on-failure

  # 设备失败后停止该设备，其他设备继续
  python api_test_runner.py --csv test_cases.csv --max-workers 2 --on-failure stop_device --force-allocate

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
        default=None,
        help="最大并发数（默认: 使用配置文件值或1）"
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

    # 设备分配参数
    parser.add_argument(
        "--allocation-strategy",
        choices=["round_robin", "least_loaded", "random", "affinity"],
        default="round_robin",
        help="设备分配策略（默认: round_robin）"
    )
    parser.add_argument(
        "--force-allocate",
        action="store_true",
        help="强制重新分配设备，忽略用例中的设备ID"
    )

    # 失败处理参数
    parser.add_argument(
        "--on-failure",
        choices=["stop_all", "stop_device", "continue"],
        default=None,
        help="失败处理策略（默认: 使用配置文件值）"
    )

    # 配置参数
    parser.add_argument(
        "--config",
        help="配置文件路径（YAML格式）"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="报告输出目录（默认: 使用配置文件值）"
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

    # 命令行参数覆盖配置（只有当用户明确指定时才覆盖）
    if args.output_dir is not None:
        config.reporting.output_dir = args.output_dir
    if args.continue_on_failure:
        config.execution.continue_on_failure = True
    if args.max_workers is not None:
        config.execution.max_workers = args.max_workers
    if args.on_failure is not None:
        config.execution.failure_strategy = args.on_failure

    # 创建设备分配器
    from device_allocator import DeviceAllocator, AllocationStrategy

    strategy_map = {
        "round_robin": AllocationStrategy.ROUND_ROBIN,
        "least_loaded": AllocationStrategy.LEAST_LOADED,
        "random": AllocationStrategy.RANDOM,
        "affinity": AllocationStrategy.AFFINITY
    }

    allocator = DeviceAllocator(
        strategy=strategy_map[args.allocation_strategy],
        preserve_affinity=not args.force_allocate
    )

    # 显示分配器信息
    print(f"\n[设备分配器配置]")
    print(f"  分配策略: {args.allocation_strategy}")
    print(f"  强制分配: {'是' if args.force_allocate else '否（保留亲和性）'}")
    print(f"  失败策略: {config.execution.failure_strategy}")
    available_devices = allocator.get_available_devices()
    print(f"  检测到设备: {len(available_devices)}个")
    for device_id in available_devices:
        print(f"    - {device_id}")

    # 警告提示
    if not args.force_allocate and len(available_devices) > 1:
        print(f"\n⚠️  警告: 检测到多个设备但未使用 --force-allocate 参数")
        print(f"   如果所有用例的device_id相同，将无法实现并发执行")
        print(f"   建议添加 --force-allocate 参数以启用设备动态分配\n")
    elif args.max_workers is None and config.execution.max_workers <= 1:
        print(f"\n⚠️  警告: max_workers={config.execution.max_workers}，测试将串行执行")
        print(f"   建议添加 --max-workers 2 参数以启用并发执行\n")
    elif len(available_devices) >= 2 and config.execution.max_workers >= 2:
        print(f"\n✅ 并发执行已启用: {config.execution.max_workers} 个worker, {len(available_devices)} 个设备\n")

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
            max_workers=config.execution.max_workers,
            skip_device_check=args.skip_device_check,
            allocator=allocator
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
