# CST接口作用域补充核查

日期：2026-10-28；本机CST2022安装帮助和可见源码只读审查，未启动CST。完整来源、调用链、限制和待办见[详细设计](../docs/mcp-cst-capability-scope-design.md)。

## 官方定义

- Python cst.interface的connect_to_any在多实例时随机连接；应使用明确PID和工程句柄，但PID仍需额外归属证据。
- Project.modeler与Project.schematic是不同接口；execute_vba_code在本版帮助列于Schematic，不能称为通用Modeler方法。
- Modeler.start_solver异步返回，run_solver等待完成；abort/pause/resume存在，但帮助未证明异常断连或timeout后的任务状态，也不替代框架恢复协议。
- cst.results只处理0D/1D。get_3d取工程的3D结果子模块；支持子工程，不保证所有结果树项含相同run id。run0可能有副本。
- allow_interactive只能在保存后读取；未保存变化可能得到陈旧/畸形结果。正在仿真的工程不在支持范围。
- CLI -withmpi文档列举的求解器不含Eigenmode；这不足以断言所有版本都不支持，但本版不能据此承诺HOM MPI。

## 当前源码事实

- Managed使用工程内Model.run批宏，不通过官方Python控制；native_results按声明路径读取严格单行标量，不是cst.results包装。
- 官方studio.py/results.py委托编译扩展，内部行为不可从这些薄包装完整审计。本机接口扩展文件名含cp36–cp39，不推断可用于任意Python ABI。
- 预处理BindHomSolverSettings未检查AddToHistory返回值，日志已明确returned-not-verified；已登记修复待办。本轮不把此发现升级为已复现的工程损坏或历史丢失。

## 实测与未完成

本轮仅29项离线定向测试通过（文档索引、Managed和原生结果），报告`artifacts/mcp-cst-scope-20261028.xml`为可再生成本机产物，不保证随Git迁移。没有新增真实CST证据；历史Start=1但无结果、作用域和收尾证据仍保留原日期，不追认为本轮验收。原生控制后端、实时abort及跨版本/跨节点支持均待独立实施与验收。
