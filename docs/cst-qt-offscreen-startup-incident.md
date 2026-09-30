# CST 启动崩溃：继承 Python Qt offscreen 环境

日期：2026-09-30。状态：启动触发条件已复现并修复；修复后的完整集成测试已通过。

## 现象与影响

CST 普通启动正常，部分单项真实测试也通过；整组 pytest 收集后，CST 多次在 Worker ready 或 Completion 生成前退出。

- 退出码 `3221225477`，十六进制 `0xC0000005`，表示内存访问违规，不是文件权限错误。
- Windows Application/1000 事件显示 CST 2022.5 的 `QtitanBase1.dll` 崩溃，重复出现偏移 `0x3b1f9`。故障模块仅说明异常位置，不能单凭它认定安装损坏。
- 整组 17 项曾全部失败；其中最小协议的 PowerShell/COM 控制器退出码为 1，不能把该码本身等同于 CST 异常码。
- 失败发生在启动阶段，不能据此判断 HOM 算法、后处理或恢复功能本身不正确。

## 触发链

1. GUI 测试模块在导入时设置 `os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')`，供无可见窗口的 Python GUI 测试使用。
2. pytest 全量收集时导入这些模块；即使随后被 `-m integration` 排除，导入产生的环境修改仍然存在。
3. Python 启动 CST 时默认继承父进程环境。CST 自身也使用 Qt，因而继承 Python 测试所用的 offscreen 平台设置。
4. 本机、本版本的 CST 在此条件下启动崩溃。单项收集没有导入 GUI 模块，因此形成“单项通过、整组失败”的表象。

相关 GUI 测试：`gui_theme_test.py`、`gui_main_window_test.py`、`gui_fake_worker_flow_test.py`、`gui_config_models_test.py`。

此结论是本项目的受控对照结果，不代表所有 Qt 程序或所有 CST 版本使用 offscreen 都必然崩溃。

## 对照证据

| 条件 | 结果 | 结论边界 |
| --- | --- | --- |
| 同一最小宏：正常、最小化、独立进程组、组合选项 | 四组均退出 0，无新增残留 | 本轮未复现启动选项导致崩溃 |
| 完整 Worker 宏，不求解，独立脚本 | 正常与最小化均 Ready、Stop Ack、退出 0 | 完整宏可初始化并标准退出 |
| 相同流程，pytest 单项收集 | 1 passed，35.14 秒 | pytest 本身不是充分触发条件 |
| 相同流程，pytest 全量收集，继承 offscreen | ready 前 `0xC0000005` | 复现环境继承差异 |
| 全量收集，仅临时删除 offscreen | 1 passed，52.62 秒，两种窗口方式均通过 | 支持该变量为本次直接触发因素 |
| 修复子进程环境后，全量收集，父进程仍 offscreen | 1 passed，36.35 秒 | 验证隔离修复且保留 GUI 测试环境 |

仓库根目录的证据报告：

- `integration-worker-startup-context.xml`
- `integration-worker-fullcollection-context.xml`
- `integration-worker-clean-qt-context.xml`
- `integration-qt-env-fix.xml`
- 历史全量失败报告 `integration-all-gates.xml`、`integration-diagnostics-retest.xml`

逐会话诊断与对照 JSON 存在 `.pytest_cache`，不属于长期可靠归档；长期证据以已保存的 XML 和本文为准。新增报告尚需随后续提交纳入版本控制。

## 修复

`csttool/cst_process_env.py` 提供 `cst_process_environment()`，复制父环境，按大小写不敏感键名移除：

- `QT_QPA_PLATFORM`
- `QT_QPA_PLATFORM_PLUGIN_PATH`
- `QT_PLUGIN_PATH`

直接复现验证的是第一个变量；另外两个作为 Python Qt 插件路径隔离，避免向外部 CST 注入不匹配的插件位置，并非已证明也是本次崩溃原因。

生产 `ManagedCSTWorker`、`CstProjectPreprocessor` 和直接启动 CST/COM 控制器的集成入口均显式传入该环境副本。父环境不变，保留 PATH、许可证等无关配置；不修改全局环境、注册表、CST 安装或驱动，不通过自动重试掩盖错误。

对照工具的原始启动实验是诊断用途，不能当作生产启动封装使用。

## 诊断与测试防护

- `test/cst_process_env_test.py` 检查父环境不变、无关变量保留、Qt 键大小写处理。
- `test/worker_startup_context_integration_test.py` 在真实 CST 上验证完整收集场景，覆盖正常窗口和最小化启动、Ready、Stop Ack、退出码及新增残留检查。
- Worker 启动失败记录 `WORKER_START_FAILED` 和独立 `failures/*.json`，包括异常栈、PID/退出码、协议文件状态及有界 CST 日志尾部。
- Windows 事件采集区分成功空列表、权限/命令失败和超时，保留错误详情；候选事件不自动归因到本进程。
- 本问题排查中另外修复测试夹具 `.settings` 缺失与清理 `None.poll()` 遮盖原始异常。这些是独立缺陷，不是 Qt 崩溃的根因。

## 验收边界与后续

普通回归：267 passed，19 deselected。修复后完整真实 CST 集成测试：19 passed，267 deselected，2762.56 秒（46 分 2 秒）。报告为仓库根目录 `integration-qt-fixed-all-gates.xml`。

本轮通过预处理、重复任务、停止续算、故障恢复、HOM 十模式扫描、运行时后处理、模板、原生读取、Warm/Cold 对比及两个启动环境用例。退出与残留由各用例断言检查；不代表清理了早期实验残留会话，也不构成所有 CST 版本或任意工程的保证。后续修改仍须检查 Stop Ack、标准 Save/Quit、进程退出和残留，不能仅凭结果文件或 Manager 状态认定成功。

## 经验

外部 GUI 程序的启动环境应是显式边界，而不是无条件继承 Python 测试进程。测试选择只控制运行哪些用例，不撤销收集阶段的副作用。面对“单项通过、整组失败”，应先比较收集环境和启动条件，再判断业务实现是否存在回归。
