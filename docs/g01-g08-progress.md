# G01–G08现行门禁状态

2026-11-06对照最新证据整理，证据来自各原验收批次，2026-11-03已通过[Codex桌面正常链](codex-desktop-acceptance-20261103.md)，下表仍区分原记录与本轮证据。完整阶段记录见[复审前快照](archive/20261103-semantic-review/g01-g08-progress.md)，旧“未建模/待刷新/活跃PID”不得当当前实时状态。

|门禁|已实现与原证据|剩余边界|
|---|---|---|
|G01|2026-11-02 Codex九工具空工程/检查/幂等/退出记录；源码14工具，官方现代SDK/stdio通过|2026-11-03/04指定桌面14工具正常闭环通过；完整N01–N25未完成|
|G02|公开create/apply/configure构造参数化真空Pillbox，保存表达式/说明；归属门禁、原生几何观察|2026-11-03桌面对话Z模型及11-04 GEO XYZ小网格通过；其它几何/模块另验|
|G03|生产保存重开、原生单位/solver/mesh/频率/实体/六边界核对；PEC背景使用历史/重放证据|完整Rebuild/异常/控制器退出及更多版本材料未全验|
|G04|公开SDK实际一次Start、ACK/DB/采用/标准关闭，采用回执缺口恢复不重算|12时点/两类发布控制器退出/真实拒绝已见新驱动；Start=0/Start自身异常仍待验；生产Runner求解中退出已由11-04隔离副本通过，见[五项实施](execution-hardening-five-steps.md)|
|G05|1147.42692991921MHz、中心Z轴R/Q223.541439593232Ω，积分/能量/公式/宏来源随结果冻结|11-04 GEO XYZ小网格已验，见[GEO实现](geometry-production-implementation.md)；不扩大到任意位置/算子及收敛证明|
|G06|理想TM010频率相对误差约0.000144%，通过5%|不是场型匹配或R/Q采样收敛|
|G07|公开JSON/CSV导出、幂等和路径/大小/hash核对|2026-11-03/04桌面返回JSON/CSV本地路径并核对hash；远程资源下载未实现|
|G08|对应批次求解Worker标准关闭、Runner退出；失败候选按实际退出事实退役|2026-11-03故障驱动22个原生会话标准关闭；未覆盖失败分支不能推广，旧pending=0不是实时盘点|

首阶段受限正常链已收口，完整故障矩阵与扩展能力独立保留，使用范围见[MCP收口](mcp-first-stage-closeout.md)。本批32项SDK/stdio/适配回归不重新认证旧原生测量。

## 接口及独立事实

- [类型化接口](typed-definition-service.md)、[公共单次](single-simulation-service.md)是使用入口；静态设计的候选清单不是已实现API。
- [公开真实链](typed-public-acceptance-20261103.md)及[轻量JSON](../knowledge-base/mcp-typed-public-acceptance-20261103.json)限定模型/设置/后处理/退出和恢复证据。
- [定义会话](../csttool/definition_sessions.py)核对PID+创建时间/精确副本路径，未知不放行，缺退出码不编造0；恢复不授予ready，不重放验证或求解。
- 2026-11-02原生new超时候选后来已按事实退役；wmic缺失是已证实的接管障碍，不能当最初超时的唯一原因，见[现场记录](../knowledge-base/cst-native-bootstrap-startup-20261102.md)。

MCP适配器固定tools-only/严格Schema/有限句柄与并发，通过Runner执行；启动命令及HTTP入口见[本机Runner](local-runner.md)。可选SDK环境或宿主配置属于部署现场，不将旧artifacts目录存在性作为当前保证；刷新共享服务可能使其他会话句柄失效，不能擅自以刷新代替正常退出。

本页不累加154/6/41等原批次数字；完整报告保留于对应验收页及历史快照。本批离线故障与协议分项证据见[公共矩阵](public-fault-matrix.md)，未提升真实故障门禁。下一步只在[TODO](minimal-python-vba-todo.md)维护。
