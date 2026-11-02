# 文档导航

更新：2026-11-02。先读[当前状态](current-status.md)与[功能索引](feature-index.md)，再定位专题实现、测试和证据。

|用途|入口|
|---|---|
|当前能力、实际验收和限制|[当前状态](current-status.md)|
|下一步与保留的长期待办|[现行TODO](minimal-python-vba-todo.md)|
|功能→源码/函数/工具/说明|[功能索引](feature-index.md)|
|公共单次API/G03、恢复/错误行为|[公共服务](single-simulation-service.md)|
|最新真实CST组合验收|[G03/G04记录](single-simulation-g04-acceptance.md)|
|设置定义/执行事实分层|[验证器](cst-settings-verifier-design.md)、[B2投影](settings-history-projection.md)、[B3快照](execution-snapshot-verification.md)、[原生采集](native-execution-capture.md)|
|MCP目标与冻结设计，非全部已实现|[G01–G08](mcp-first-stage-conversational-gate.md)、[首阶段契约](mcp-first-stage-interface-contract.md)、[统一接口](unified-interface-contract.md)、[静态框架](mcp-framework-static-design.md)|
|既有生产运行协议与恢复|[Python/VBA协议](minimal-python-vba-protocol.md)、[恢复退出实现](recovery-exit-audit-implementation.md)|
|整理前状态、旧计划、原始验收数字|[归档索引](archive/20261102-progress-consolidation/README.md)|

当前状态是进度入口，API文档描述已实现接口，设计契约描述目标；历史验收只证明其记录的版本/场景。旧文档不以删除来消除矛盾，而是归档并保留来源链接。artifacts原始数据不保证随Git迁移；知识库区分文档定义、实测、推测和未完成项。

本轮执行入口：[G01–G08逐项推进、SDK接入与恢复验收](g01-g08-progress.md)。

G02首子集：[空工程创建、不可变文档与官方Python ABI](project-creation-service.md)。

首阶段当前建模/配置/保存与结果来源API：[类型化定义服务](typed-definition-service.md)。

最新纵向结果与范围：[2026-11-03类型化公开链验收](typed-public-acceptance-20261103.md)。
