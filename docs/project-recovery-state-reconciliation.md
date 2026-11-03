# 项目恢复状态对账（2026-10-20）

## 现象与原因

现场日志显示续跑在初始化阶段被 `project.ini` 的 `RECOVERY_REQUIRED` 拒绝，尚未启动扫描；Runner 却保存为 `FAILED / initializing / confirmed-closed`。这是状态传播缺陷，不是该日志证明了求解失败。

旧流程有三个断点：

1. 普通续跑只自动处理 `FAILED`，不能越过项目的显式恢复门禁；但异常又被后端归为普通失败。
2. Runner 只根据残留会话判断是否需要恢复，遗漏持久项目状态。GUI 根据 Runner 状态提供恢复入口，因而入口被关闭。`confirmed-closed` 仅说明会话关闭，不说明项目结果和检查点已经对账。
3. 显式恢复新建后端仅选择目录，没有加载项目配置；旧实现先释放锁并记录完成，再写项目状态，可能此时才报“配置未准备”。日志中的完成并不代表持久更新成功。

用户提供的检查点摘要为188个模式、连续确认前沿1165.8231853449101 MHz、已计算上界1215.17243800861 MHz。两个频率不能互换；有空隙时不能从最高已计算频率直接继续。现场文件位于另一台/目录环境，本轮没有修改它们。

## 当前恢复顺序

1. Runner 启动、空闲状态查询及接收命令时读取项目门禁。持久 `RUNNING`、`STOP_REQUESTED`、`RECOVERY_REQUIRED` 或不可读配置，均要求显式恢复；运行中的合法状态不被查询流程覆盖。
2. 后端准备也检查同一门禁，拒绝建立 Manager，不自动将其改成 READY。普通 FAILED 续跑兼容行为保持不变。
3. 显式恢复先核验本任务预处理进程没有遗留，再在项目运行锁内加载已有配置、对账 Managed Completion/接收记录并正常关闭会话。
4. 只读核验已有HOM检查点及登记快照，或标准任务检查点结构；对已确认任务补齐采用标记，再在同一项目锁内持久写入INTERRUPTED。写成功才记录后端恢复完成，最后释放锁。Runner随后按本次恢复身份对账全部未收口历史start意图；任何写入失败保留需恢复，不把后端完成日志当Runner全部收口。
5. Runner 恢复到可操作状态后，由用户继续未完成任务；不自动重新提交计算。配置/检查点/会话核验或状态写入失败则保留恢复要求及异常诊断。

配置尚未生成的准备期失败允许会话收尾，但不凭空生成 project.ini。无快照记录的历史检查点仍沿用既有兼容规则。恢复核验不提升覆盖、不改检查点、不采用未确认工程；实际续跑仍需当前配置/工程身份校验。标准检查点的结构检查不替代后续任务签名比对。

## 接口及证据

- 公共门禁与只读检查：[project_recovery_state.py](../csttool/project_recovery_state.py)。
- 配置加载：`ProjectConfigManager.load_recovery_configuration`，不启动CST、不要求先完成普通运行准备。
- 后端：`prepare_run`、`is_recovery_required`、`recover_project_sessions`。
- Runner：`_reconcile_project_state`；`LocalExecution.session_safety` 独立描述会话安全，不用项目标志冒充进程存活。
- 回归：[project_recovery_state_test.py](../test/project_recovery_state_test.py)，包括真实配置管理器、失败写入重试、快照损坏、188模式/覆盖保持、旧FAILED状态重对账、恢复后续跑及预处理阻断，均不启动CST。

## 部署与当前边界

恢复可在会话/协议等待和逐任务采用边界暂停，保留证据后重入；停止不撤销已经发布的ACK。没有生成配置的准备期失败不会凭空创建project.ini。完整停止/旧意图收口及离线退出合同见[实施说明](recovery-exit-audit-implementation.md)。

[原批次完整记录](archive/20261103-semantic-review/project-recovery-state-reconciliation.md)保留现场188模式/覆盖摘要与2026-10-20的85项离线证据。真实CST后续验收见HOM/L5专题，不再把原批“尚未实测”当全项目现状。目标机器需正常停后台后升级；不热替换、不手改READY。
