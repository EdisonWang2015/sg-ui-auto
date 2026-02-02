# Open-AutoGLM 测试框架

基于 Open-AutoGLM 的自动化测试框架，支持 CSV 测试用例管理、HTML+JSON 双格式报告生成。

## 特性

- **CSV 测试用例管理**：通过 CSV 文件管理测试用例，支持非技术人员使用
- **直接 API 调用**：直接调用 PhoneAgent API，无需 subprocess，性能提升 30-50%
- **设备检查**：运行前自动检查设备可用性和截图功能
- **失败截图**：测试失败时自动保存截图并在报告中展示
- **双格式报告**：生成 HTML 和 JSON 双格式测试报告
- **详细报告**：报告中包含测试步骤、预期结果、验证详情
- **灵活筛选**：支持按标签、类型、优先级、设备 ID 筛选测试用例

## 快速开始

### 1. 安装依赖

```bash
pip install pyyaml
```

### 2. 配置

编辑 `config/config.yaml`，设置 API 密钥和设备信息：

```yaml
api:
  api_key: "your_api_key_here"

devices:
  - device_id: "YOUR_DEVICE_ID"
    name: "测试设备"
```

或者设置环境变量：

```bash
export AUTOGLM_API_KEY="your_api_key_here"
```

### 3. 准备测试用例

参考 `examples/test_cases.csv` 创建测试用例 CSV 文件。

CSV 格式：

```csv
测试用例ID,测试名称,测试类型,优先级,前置条件,测试步骤,预期结果,测试数据,设备ID,超时时间,标签
TC001,测试用例名称,功能测试,P1,设备已连接,打开xxx应用...,✅任务完成 ✅操作成功,关键数据:值,DEVICE_ID,180,smoke
```

### 4. 运行测试

```bash
# 运行所有测试
python src/api_test_runner.py --csv examples/test_cases.csv --config config/config.yaml

# 只运行 smoke 测试
python src/api_test_runner.py --csv examples/test_cases.csv --filter-tags smoke

# 指定设备运行
python src/api_test_runner.py --csv examples/test_cases.csv --device-id YOUR_DEVICE_ID

# 失败后继续执行
python src/api_test_runner.py --csv examples/test_cases.csv --continue-on-failure
```

### 5. 查看报告

测试完成后，在 `test_reports/` 目录下生成：

- **HTML 报告**：`test_reports/html/test_report_YYYYMMDD_HHMMSS.html`
- **JSON 报告**：`test_reports/json/test_report_YYYYMMDD_HHMMSS.json`
- **失败截图**：`test_reports/screenshots/TEST_ID_YYYYMMDD_HHMMSS.png`

## 项目结构

```
sg-ui-auto/
├── README.md                   # 本文件
├── src/                        # 源代码
│   ├── api_test_runner.py      # 主控制器
│   ├── csv_case_manager.py     # CSV 用例管理器
│   ├── api_executor.py         # API 执行引擎
│   ├── enhanced_validator.py   # 增强验证器
│   ├── dual_reporter_enhanced.py  # 双格式报告生成器
│   ├── test_config.py          # 配置管理
│   └── test_validator.py       # 基础验证器
├── config/                     # 配置文件
│   └── config.yaml             # 框架配置
├── examples/                   # 示例文件
│   └── test_cases.csv          # 示例测试用例
├── docs/                       # 文档
│   └── 完整文档.md             # 详细技术文档
└── test_reports/               # 测试报告目录（自动创建）
    ├── html/                   # HTML 报告
    ├── json/                   # JSON 报告
    └── screenshots/            # 失败截图
```

## 核心优势

| 特性 | 优势 |
|------|------|
| 直接 API 调用 | 性能提升 30-50%，支持 Agent 实例复用 |
| CSV 用例管理 | 非技术人员友好，易于维护 |
| 设备检查 | 运行前自动检查设备健康状态 |
| 失败截图 | 快速定位问题，报告中直接查看 |
| 双格式报告 | HTML 可视化 + JSON 机器可读 |

## 命令行参数

```
--csv                  CSV 测试用例文件路径（必需）
--config               配置文件路径（默认：config/config.yaml）
--filter-tags          按标签筛选（逗号分隔）
--filter-type          按类型筛选（purchase/sales/mixed）
--filter-priority      按优先级筛选（P0/P1/P2/P3）
--device-id            指定设备 ID
--max-workers          最大并发数（默认：1）
--continue-on-failure  失败后继续执行
--skip-device-check    跳过设备检查（不推荐）
--output-dir           报告输出目录（默认：test_reports）
--verbose              详细输出
```

## CSV 测试用例格式

| 列名 | 说明 | 示例 |
|------|------|------|
| 测试用例ID | 唯一标识 | TC-P001 |
| 测试名称 | 测试用例名称 | 新建采购单 |
| 测试类型 | 类型分类 | 采购单/销售单 |
| 优先级 | P0-P3 | P1 |
| 前置条件 | 执行前条件 | 设备已连接 |
| 测试步骤 | 任务指令（自然语言） | 打开森果产地通... |
| 预期结果 | 验证要点（空格分隔） | ✅任务完成 ✅金额：7元 |
| 测试数据 | 键值对数据（逗号分隔） | 类目:苹果,农户:非伍6 |
| 设备ID | 目标设备 | PQY5T20A07017811 |
| 超时时间 | 超时秒数 | 180 |
| 标签 | 标签（逗号分隔） | smoke,regression |

## 验证规则

框架支持多种验证类型：

1. **关键词验证**：检查输出是否包含预期关键词
2. **金额验证**：验证金额是否正确（允许 ±0.5 元误差）
3. **业务数据验证**：验证农户、客户、类目等业务数据
4. **弹窗验证**：验证预期弹框是否出现
5. **任务完成验证**：验证任务是否成功完成

## 报告示例

HTML 报告包含：

- 测试汇总卡片（总数、通过率、耗时）
- 每个测试用例的详细信息
- 测试步骤和预期结果展示
- 验证结果的可视化展示
- 失败截图的嵌入式显示
- 执行时间线

## 文档

详细技术文档请参考：[docs/完整文档.md](docs/完整文档.md)

## 依赖

- Python 3.9+
- pyyaml
- Open-AutoGLM（需要在项目根目录）

## 注意事项

1. 确保 ADB 设备已连接
2. 确保设备已解锁
3. 确保应用已安装
4. 建议使用真实设备进行测试
5. API 密钥请妥善保管，不要提交到 Git

## 许可证

本项目基于 Open-AutoGLM 项目开发。
