# CST Tools 测试与验收指南

2026-11-03按pyproject.toml、test/conftest.py及当前测试入口核对。旧P0–P9、打包体积、累计通过数和每轮追加说明保存在[复审前原文](archive/20261103-semantic-review/testing-guide.md)，不代表现代码全仓通过。

## 运行层级

默认`python -m pytest -q`由pyproject排除integration，不启动真实CST；仍可能创建Qt offscreen窗口、临时Git、fake Runner/HTTP进程及测试报告，不等于纯静态或完全无副作用。按功能先运行必要集合，不为文档小改动无目的重跑真实求解。

本次文档/工具定向入口：

```powershell
python -m pytest -q test/documentation_index_test.py test/documentation_semantics_test.py
python -m pytest -q test/project_inspect_test.py test/project_map_migration_test.py test/project_registry_test.py test/project_inspect_fault_test.py
```

第一组只做结构与选定语义回归，不证明全部文档陈述正确。源码包边界`test/source_release_boundary_test.py`会实际构建测试ZIP、编译、无CST GUI烟雾和解压后校验；需要Git源码工作树及Qt环境，不保证在缺省源码包中可递归运行。

其他入口按[功能索引](feature-index.md)查询：Manager/Managed、Runner/恢复、GUI控制器、后处理/场分析分别选择对应测试。显式注入的进程内假GUI后端不代表生产GUI绕过Runner。

## 真实CST授权与门禁

真实测试必须显式选择integration并给--run-cst及--cst-exe（或CST_TEST_EXE）；不满足时fixture跳过，故“deselected/skipped”不是通过。选择integration本身不授权从文档直接启动真实求解。

```powershell
python -m pytest -q -o addopts="" -m integration --run-cst --cst-exe "D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe" test/protocol_contract_integration_test.py
```

此为用户授权后的命令示例，本次语义复审不执行。真实验收串行副本、核实进程归属，不改原工程，不强杀替代正常退出。参数表达式和历史持久化分别核验；退出0、Start返回1、ACK及日志任何单一信号不够。

正常Managed求解TASK_TIMEOUT=None，启动/ACK用120秒边界，stop共享600秒预算；测试可注入限时/时钟模拟故障，不把测试限时当生产求解总时限。原生COM/WinWrap探针即使不求解也有副作用，必须先读tools登记和专页。

## GUI与环境

Qt测试可用QT_QPA_PLATFORM=offscreen；它是测试显示插件设置，不是CST headless开关。生产CST子进程须经过cst_process_env清理测试Qt变量。`python gui_app.py --smoke-test`用不恢复用户项目的窗口，处理事件后正常关闭，不提交计算。

源码发布工具为scripts/build_source_release.py。旧PyInstaller spec/pack.bat仍可能存在，但本页不将旧构建数字/旧二进制记录当当前发布验收。依赖本机环境，离线测试通过不代表新机器、真实鼠标流畅度或远程分布式可用。

## 产物与证据

运行前查磁盘；使用本轮明确的basetemp/工作目录，结束并确认归属后清理可再生副本。保留轻量JSON/JUnit/宏/参数和hash；原始场、模型或测试ZIP已删时注明需重建。不能清理其他活跃会话、原工程、跟踪夹具或MCP运行环境后仍声称可用。

报告记录日期、代码/环境身份、实际选择集合、通过/失败/跳过和证据层。旧批次数字不相加为现代码回归；历史失败保留，后一次通过不擦除初次失败或所有现场风险。

[现行工具维护](project-map-guide.md)、[语义复审](documentation-semantic-review.md)、[当前状态](current-status.md)分别描述使用合同、复审结论与证据进度，不再在本页逐轮追加运行日志。
