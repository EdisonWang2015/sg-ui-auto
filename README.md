# Open-AutoGLM 测试框架

基于 Open-AutoGLM 的自动化测试框架，支持 CSV/Excel/Markdown 测试用例管理、HTML+JSON 双格式报告生成。

## 特性

- **多格式测试用例管理**：支持 CSV、Excel、Markdown 三种格式，支持单文件多测试用例
- **CSV/Excel 测试用例管理**：支持 CSV 和 Excel 文件管理测试用例，支持非技术人员使用
- **直接 API 调用**：直接调用 PhoneAgent API，无需 subprocess，性能提升 30-50%
- **状态隔离**：每个测试用例执行前自动清理应用状态，支持多种清理策略
- **强制重启策略**：使用 `adb force-stop` 强制停止应用进程，确保完全从干净状态开始
- **设备检查**：运行前自动检查设备可用性和截图功能
- **失败截图**：测试失败时自动保存截图并在报告中展示
- **双格式报告**：生成 HTML 和 JSON 双格式测试报告
- **详细报告**：报告中包含测试步骤、预期结果、验证详情、清理信息
- **灵活筛选**：支持按标签、类型、优先级、设备 ID 筛选测试用例
- **并发执行**：支持多设备并发执行，提高测试效率

## 快速开始

### 1. 安装依赖

```bash
pip install pyyaml
```

### 2. 配置

编辑 `config/config.yaml`，设置 API 密钥、设备信息和状态清理策略：

```yaml
api:
  api_key: "your_api_key_here"

devices:
  - device_id: "YOUR_DEVICE_ID"
    name: "测试设备"

# 状态清理配置（推荐）
cleanup:
  enabled: true
  strategy: "force_restart"    # 推荐使用强制重启策略
  failure_mode: "warn"         # warn/error/ignore
  force_stop_delay: 2.0        # force-stop后延迟时间（秒），用于观察应用被杀掉、返回系统桌面的效果
```

**状态清理策略说明：**

| 策略 | 说明 | 推荐度 |
|------|------|--------|
| `force_restart` | 强制停止应用进程（推荐） | ⭐⭐⭐⭐⭐ |
| `auto_home` | 返回应用首页 + 关闭弹窗 | ⭐⭐⭐ |
| `custom` | 用例级自定义清理步骤 | ⭐⭐ |
| `none` | 不执行清理 | ⭐ |

或者设置环境变量：

```bash
export AUTOGLM_API_KEY="your_api_key_here"
```

### 3. 准备测试用例

参考 `examples/test_cases.xlsx`、`examples/test_cases.csv` 或 `examples/test_cases.md` 创建测试用例文件。

**支持 CSV、Excel 和 Markdown 三种格式：**

CSV 格式：

```csv
测试用例ID,测试名称,测试类型,优先级,前置条件,测试步骤,预期结果,测试数据,设备ID,超时时间,标签,清理策略
TC001,测试用例名称,功能测试,P1,设备已连接,打开xxx应用...,✅任务完成 ✅操作成功,关键数据:值,DEVICE_ID,180,smoke,inherit
```

Excel 格式（推荐）：

| 测试用例ID | 测试名称 | 测试类型 | 优先级 | 前置条件 | 测试步骤 | 预期结果 | 设备ID | 超时时间 | 清理策略 |
|-----------|---------|---------|--------|---------|---------|---------|---------|---------|---------|
| TC001 | 测试登录 | 功能测试 | P1 | 设备已连接 | 打开应用并登录 | ✅登录成功 | DEVICE_ID | 180 | force_restart |
| TC002 | 测试下单 | 功能测试 | P1 | 设备已连接 | 执行下单流程 | ✅下单成功 | DEVICE_ID | 180 | inherit |

**Markdown 格式（推荐，支持单文件多用例）：**

```markdown
# 测试套件：功能测试

## 用例：TC001 - 新建采购单

| 字段 | 值 |
|------|------|
| 测试用例ID | TC001 |
| 测试名称 | 新建采购单 |
| 测试类型 | 采购单 |
| 优先级 | P1 |
| 标签 | smoke,regression |
| 设备ID | PQY5T20A07017811 |
| 超时时间 | 180 |

**前置条件**：设备已连接，森果产地通应用已打开

**测试步骤**：打开森果产地通应用，点击新建采购单，选择类目为"苹果"，农户选择"非伍6"，数量输入"1"，点击提交保存

**预期结果**：✅任务完成 ✅操作成功 ✅保存成功

**测试数据**：类目:苹果, 农户:非伍6, 数量:1

---

## 用例：TC002 - 编辑采购单

...
```

**清理策略列说明：**
- `inherit` - 继承全局配置（默认）
- `force_restart` - 强制停止应用（推荐）
- `auto_home` - 返回首页 + 关闭弹窗
- `custom` - 自定义清理步骤（需填写"清理步骤"列）
- `none` - 不执行清理

### 4. 运行测试

```bash
# 运行所有测试（支持 CSV、Excel 和 Markdown）
python src/api_test_runner.py --csv examples/test_cases.md --config config/config.yaml

# 只运行 smoke 测试
python src/api_test_runner.py --csv examples/test_cases.md --filter-tags smoke

# 多设备并发执行
python src/api_test_runner.py --csv examples/test_cases.md --max-workers 2 --force-allocate

# 指定设备运行
python src/api_test_runner.py --csv examples/test_cases.md --device-id YOUR_DEVICE_ID

# 失败后继续执行
python src/api_test_runner.py --csv examples/test_cases.md --continue-on-failure

# 混合格式支持（CSV + Excel + Markdown）
python src/api_test_runner.py --csv test_cases.csv test_cases.xlsx test_cases.md
```

### 5. 状态清理功能

框架提供了强大的状态隔离功能，确保每个测试用例从干净的状态开始执行。

**工作原理：**

```
用例1: 检查采购单 → 执行完成
    ↓
清理: force_restart (杀掉应用进程)
    ↓
用例2: 检查销售单 → 从首页开始 ✅
```

**force_restart 策略优势：**

- ✅ **完全清理** - 杀掉进程清除所有内存、缓存、状态
- ✅ **快速执行** - 仅需 0.16 秒
- ✅ **可靠稳定** - 不依赖 UI 操作，直接使用 adb 命令
- ✅ **自动进入首页** - 应用重启后自动从首页开始

**配置方式：**

1. **全局配置（推荐）** - 在 `config/config.yaml` 中设置：
```yaml
cleanup:
  enabled: true
  strategy: "force_restart"
```

2. **用例级配置** - 在 Excel/CSV 中为特定用例设置：
   - Excel: `清理策略` 列填写 `force_restart`
   - CSV: `清理策略` 列填写 `force_restart`

3. **应用特定配置** - 为不同应用设置不同清理策略：
```yaml
cleanup:
  app_specific:
    "森果产地通": "force_restart"
    "淘宝": "none"  # 保持登录状态
```

### 6. 查看报告

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
│   ├── excel_case_reader.py    # Excel 用例读取器
│   ├── markdown_case_reader.py # Markdown 用例读取器 ⭐
│   ├── unified_case_manager.py # 统一用例管理器
│   ├── api_executor.py         # API 执行引擎
│   ├── state_cleanup.py        # 状态清理管理器 ⭐
│   ├── enhanced_validator.py   # 增强验证器
│   ├── dual_reporter_enhanced.py  # 双格式报告生成器
│   ├── test_config.py          # 配置管理
│   └── base_test_reader.py     # 测试用例基类
├── config/                     # 配置文件
│   └── config.yaml             # 框架配置
├── examples/                   # 示例文件
│   ├── test_cases.csv          # 示例测试用例（CSV）
│   ├── test_cases.xlsx         # 示例测试用例（Excel）
│   └── test_cases.md           # 示例测试用例（Markdown）⭐
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
| 多格式用例管理 | CSV/Excel/Markdown 三种格式，Markdown 支持单文件多用例 |
| 状态隔离（force_restart） | 每个用例从干净状态开始，提升测试稳定性 |
| 设备检查 | 运行前自动检查设备健康状态 |
| 多设备并发 | 支持多设备并行执行，提高测试效率 |
| 失败截图 | 快速定位问题，报告中直接查看 |
| 双格式报告 | HTML 可视化 + JSON 机器可读 |

## 命令行参数

```
--csv                  CSV/Excel/Markdown 测试用例文件路径（必需）
--config               配置文件路径（默认：config/config.yaml）
--filter-tags          按标签筛选（逗号分隔）
--filter-type          按类型筛选（purchase/sales/mixed）
--filter-priority      按优先级筛选（P0/P1/P2/P3）
--device-id            指定设备 ID
--max-workers          最大并发数（默认：1）
--force-allocate        强制重新分配设备，忽略用例中的设备ID
--allocation-strategy   设备分配策略（round_robin/least_loaded/random/affinity）
--continue-on-failure  失败后继续执行
--on-failure           失败处理策略（stop_all/stop_device/continue）
--skip-device-check    跳过设备检查（不推荐）
--output-dir           报告输出目录（默认：test_reports）
--verbose              详细输出
```

## CSV/Excel/Markdown 测试用例格式

**支持 CSV、Excel 和 Markdown 三种格式，推荐使用 Excel 或 Markdown 格式。**

### Markdown 格式说明（推荐）

**基本结构：**

- **一级标题 (#)**：测试套件名称
- **二级标题 (##)**：测试用例分隔符，支持以下格式：
  - `## 用例：TC001 - 测试名称`
  - `## TC001 - 测试名称`
  - `## TC001`
- **表格**：定义测试用例的元数据字段
- **加粗字段**：定义前置条件、测试步骤、预期结果、测试数据

**用例分隔符示例：**

```markdown
## 用例：TC001 - 新建采购单

| 字段 | 值 |
|------|------|
| 测试用例ID | TC001 |
| 测试名称 | 新建采购单 |
| 测试类型 | 采购单 |
| 优先级 | P1 |
| 标签 | smoke,regression |
| 设备ID | PQY5T20A07017811 |
| 超时时间 | 180 |

**前置条件**：设备已连接，森果产地通应用已打开

**测试步骤**：打开森果产地通应用，点击新建采购单，选择类目为"苹果"，农户选择"非伍6"，数量输入"1"，点击提交保存

**预期结果**：✅任务完成 ✅操作成功 ✅保存成功

**测试数据**：类目:苹果, 农户:非伍6, 数量:1

---
```

### CSV/Excel 格式说明

| 列名 | 必填 | 说明 | 示例 |
|------|------|------|------|
| 测试用例ID | ✅ | 唯一标识 | TC-P001 |
| 测试名称 | ✅ | 测试用例名称 | 新建采购单 |
| 测试类型 | ✅ | 类型分类 | 采购单/销售单 |
| 优先级 | ✅ | P0-P3 | P1 |
| 前置条件 | ✅ | 执行前条件 | 设备已连接 |
| 测试步骤 | ✅ | 任务指令（自然语言） | 打开森果产地通... |
| 预期结果 | ✅ | 验证要点（空格分隔） | ✅任务完成 ✅金额：7元 |
| 测试数据 | | 键值对数据（逗号分隔） | 类目:苹果,农户:非伍6 |
| 设备ID | | 目标设备（留空自动分配） | PQY5T20A07017811 |
| 超时时间 | | 超时秒数（默认180） | 180 |
| 标签 | | 标签（逗号分隔） | smoke,regression |
| **清理策略** | | **状态清理策略** | **force_restart/inherit/none** |
| **清理步骤** | | **自定义清理步骤** | **返回首页\|\|清除缓存** |
| **需要干净状态** | | **是否需要干净状态** | **true/false** |

**清理策略列说明：**

| 策略值 | 说明 | 推荐场景 |
|--------|------|---------|
| `inherit` | 继承全局配置（默认） | 大多数场景 |
| `force_restart` | 强制停止应用进程 | ⭐ 推荐用于需要完全清理的场景 |
| `auto_home` | 返回首页 + 关闭弹窗 | 轻量级清理 |
| `custom` | 自定义清理步骤 | 特殊清理需求 |
| `none` | 不执行清理 | 需要保持状态的连续测试 |

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
- **状态清理信息**（是否执行清理、清理耗时）
- 测试步骤和预期结果展示
- 验证结果的可视化展示
- 失败截图的嵌入式显示
- 执行时间线

JSON 报告包含：

- 完整的测试执行数据
- 清理执行结果（`cleanup_executed`, `cleanup_success`, `cleanup_time`）
- 设备分配信息
- 详细的验证结果

## 文档

详细技术文档请参考：[docs/完整文档.md](docs/完整文档.md)

## 使用示例

### 示例1：基本用法

```bash
# 运行 Excel 测试用例
python src/api_test_runner.py --csv examples/test_cases.xlsx
```

**执行效果：**
```
[TC-001] 执行状态清理
[清理] 执行 1 个清理步骤
[清理 TC-001] 执行 force_restart 策略
[清理 TC-001] 检测到当前应用: cc.senguo.producermanage
[清理] 成功杀掉应用进程: cc.senguo.producermanage
[清理 TC-001] 应用已被强制停止，下次启动将从首页开始
[DEBUG] Agent开始执行: 打开"森果产地通"...
```

### 示例2：多设备并发执行

```bash
# 使用2个设备并发执行，自动分配用例
python src/api_test_runner.py \
  --csv examples/test_cases.xlsx \
  --max-workers 2 \
  --force-allocate
```

**执行效果：**
- TC-001, TC-003, TC-005, TC-007 → 设备1
- TC-002, TC-004, TC-006 → 设备2
- 每个用例执行前自动 force_restart
- 真实并行执行，测试效率提升 2 倍

### 示例3：特定应用的清理策略

在 `config/config.yaml` 中配置：

```yaml
cleanup:
  enabled: true
  strategy: "force_restart"
  failure_mode: "warn"
  app_specific:
    "森果产地通": "force_restart"  # 每次重启
    "淘宝": "none"                # 保持登录状态
    "微信": "auto_home"            # 轻量清理
```

### 示例4：连续测试流程

对于需要保持状态的连续测试：

| 测试用例ID | 测试名称 | 清理策略 | 说明 |
|-----------|---------|---------|------|
| TC-001 | 登录 | `force_restart` | 从干净状态开始 |
| TC-002 | 浏览商品 | `none` | 保持登录状态 |
| TC-003 | 添加购物车 | `none` | 保持登录状态 |
| TC-004 | 结算 | `none` | 保持登录状态 |
| TC-005 | 退出登录 | - | - |
| TC-006 | 重新登录 | `force_restart` | 从干净状态开始 |



## 依赖

- Python 3.9+
- pyyaml
- openpyxl（Excel 支持）
- Open-AutoGLM（需要在项目根目录）

## 注意事项

1. 确保 ADB 设备已连接
2. 确保设备已解锁
3. 确保应用已安装
4. 建议使用真实设备进行测试
5. API 密钥请妥善保管，不要提交到 Git
6. **使用 force_restart 策略时，应用需要重新登录**（如需保持登录状态，使用 `none` 策略）

## 常见问题

### Q: 为什么测试用例执行失败？

A: 常见原因包括：
- 设备未连接或未解锁
- 应用未安装或版本不匹配
- 测试步骤描述不够清晰
- 网络连接问题

### Q: 如何保持登录状态？

A: 在测试用例的 `清理策略` 列中填写 `none`，或设置 `需要干净状态: false`

### Q: force_restart 策略会清空应用数据吗？

A: `force_restart` 只停止应用进程，不会清除应用数据（如登录信息、缓存）。如需完全清除数据，可以修改清理步骤使用 `adb shell pm clear <package_name>`

### Q: 为什么看不到应用被杀掉返回系统桌面的效果？

A: 默认情况下，`force_restart` 执行后应用会立即重新启动，所以"返回系统桌面"的时间很短。如果需要观察应用被杀掉的效果，可以在 `config/config.yaml` 中设置 `force_stop_delay: 2.0`（延迟2秒），这样就能看到应用被杀掉后返回系统桌面的效果。生产环境建议设置为 0 以加快测试速度。

### Q: 如何提高测试执行速度？

A: 可以通过以下方式：
1. 使用多设备并发执行：`--max-workers 2 --force-allocate`
2. 使用 `force_restart` 策略（比 UI 操作更快）
3. 合理设置超时时间，避免过长等待

## 许可证

本项目基于 Open-AutoGLM 项目开发。
