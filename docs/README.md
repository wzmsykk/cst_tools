# 文档导航

更新：2026-11-03。先读[当前状态](current-status.md)与[功能索引](feature-index.md)，再定位专题实现、测试和证据。

|用途|入口|
|---|---|
|逐篇适用性、旧语义修正及归档边界|[语义复审](documentation-semantic-review.md)|
|当前能力、实际验收和限制|[当前状态](current-status.md)|
|下一步与保留的长期待办|[现行TODO](minimal-python-vba-todo.md)|
|功能→源码/函数/工具/说明|[生成索引](feature-index.md)、[机器映射及维护指南](project-map-guide.md)|
|开发工具、副作用、动态关系与维护步骤|[定位指南](project-map-guide.md#d3工具清单与人工动态关系)、[实施与验收计划](project-documentation-tooling-plan.md)、[源码包故障与校验边界](project-map-guide.md#d4故障矩阵与源码包边界)|
|公共单次API/G03、恢复/错误行为|[公共服务](single-simulation-service.md)|
|2026-11-02真实CST组合验收|[G03/G04记录](single-simulation-g04-acceptance.md)|
|设置定义/执行事实分层|[验证器](cst-settings-verifier-design.md)、[B2投影](settings-history-projection.md)、[B3快照](execution-snapshot-verification.md)、[原生采集](native-execution-capture.md)|
|MCP目标与冻结设计，非全部已实现|[G01–G08](mcp-first-stage-conversational-gate.md)、[首阶段契约](mcp-first-stage-interface-contract.md)、[统一接口](unified-interface-contract.md)、[静态框架](mcp-framework-static-design.md)|
|通用几何与实体选择集，GEO-1/1.1声明编辑与GEO-2离线历史已接、原生待校准|[GEO设计、作用域与历史边界](geometry-selection-interface-design.md)|
|既有生产运行协议与恢复|[Python/VBA协议](minimal-python-vba-protocol.md)、[恢复退出实现](recovery-exit-audit-implementation.md)|
|整理前状态、旧计划、原始验收数字|[归档索引](archive/20261102-progress-consolidation/README.md)|

当前状态是进度入口，API文档描述已实现接口，设计契约描述目标；历史验收只证明其记录的版本/场景。旧文档不以删除来消除矛盾，而是归档并保留来源链接。artifacts原始数据不保证随Git迁移；知识库区分文档定义、实测、推测和未完成项。

真实副本自动时序/控制器故障注入：[串行驱动与边界](public-fault-injection.md)。

公共故障与N01–N25覆盖入口：[故障矩阵](public-fault-matrix.md)。

本轮执行入口：[G01–G08逐项推进、SDK接入与恢复验收](g01-g08-progress.md)。

G02首子集：[空工程创建、不可变文档与官方Python ABI](project-creation-service.md)。

首阶段当前建模/配置/保存与结果来源API：[类型化定义服务](typed-definition-service.md)。

指定Codex桌面正常纵向链：[2026-11-03桌面验收](codex-desktop-acceptance-20261103.md)。

最新纵向结果与范围：[2026-11-03类型化公开链验收](typed-public-acceptance-20261103.md)。

WinWrap现行生成检查/源图/校准与发布门禁：[W23受限A1链](winwrap-w23-implementation.md)；[W01](winwrap-w01-implementation.md)保留原批次证据。

- [GEO-2–4生产实现与验收](geometry-production-implementation.md)：当前原子历史、公开几何保存、受限仿真闭环及独立原生证据；设计旧阶段不作为当前API。

- [2026-11-04桌面GEO对话验收](codex-desktop-geometry-20261104.md)：当前14工具正常链、实际保存/表达式、单次求解与标准收尾，不以SDK代替指定宿主。

- [A1重校准](a1-recalibration-20261104.md)：2026-11-04当前原子历史、真实语法拒绝前缀、可信注入诊断及XYZ无求解保存重开；A1/GEO许可独立。

- [冷启动就绪与诊断](runner-startup-readiness.md)：纯Runner启动实测、Windows锁竞争、阶段/早退诊断、迟就绪重连及尚未确认的原现场原因。
