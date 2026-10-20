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
4. 只读核验已有 HOM 检查点结构及所登记快照大小/哈希，或标准任务检查点结构。通过后在同一锁内持久写入 INTERRUPTED；写成功才记录恢复完成，最后释放锁。
5. Runner 恢复到可操作状态后，由用户继续未完成任务；不自动重新提交计算。配置/检查点/会话核验或状态写入失败则保留恢复要求及异常诊断。

配置尚未生成的准备期失败允许会话收尾，但不凭空生成 project.ini。无快照记录的历史检查点仍沿用既有兼容规则。恢复核验不提升覆盖、不改检查点、不采用未确认工程；实际续跑仍需当前配置/工程身份校验。标准检查点的结构检查不替代后续任务签名比对。

## 接口及证据

- 公共门禁与只读检查：[project_recovery_state.py](../csttool/project_recovery_state.py)。
- 配置加载：`ProjectConfigManager.load_recovery_configuration`，不启动CST、不要求先完成普通运行准备。
- 后端：`prepare_run`、`is_recovery_required`、`recover_project_sessions`。
- Runner：`_reconcile_project_state`；`LocalExecution.session_safety` 独立描述会话安全，不用项目标志冒充进程存活。
- 回归：[project_recovery_state_test.py](../test/project_recovery_state_test.py)，包括真实配置管理器、失败写入重试、快照损坏、188模式/覆盖保持、旧FAILED状态重对账、恢复后续跑及预处理阻断，均不启动CST。

## TODO 与部署边界

离线合并专项：85 passed，43.19s，覆盖后端、Runner及HTTP故障、GUI状态、配置和文档索引。轻量报告 `artifacts/recovery-state-20261020.xml` 不保证随Git迁移；本轮临时目录验收后删除，可重新生成。该结果不是全仓测试或真实CST验收。

- 在目标机器更新源码包，并在后台空闲且标准退出后重启 Runner；不要在运行中替换代码或手工把状态改成 READY。
- 用受控副本验收真实CST中断→恢复→续跑以及实际桌面按钮流程；本轮离线测试不证明现场188模式产物完整，也不证明真实CST恢复已经通过。
- 未实现跨文件原子事务；设计采用保守门禁及可重复恢复，持久写失败不能视为成功。Runner与项目配置表示不同层次事实，不要求其枚举值处处相同。
