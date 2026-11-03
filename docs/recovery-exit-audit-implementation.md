# A01–A08 恢复/退出审计实施与故障验收

2026-11-02。对应[审计清单](recovery-exit-system-audit-20261102.md)，基于1b4afa4及当前工作区的最大化/退出修正继续实施。本批没有启动真实CST，不改变原工程、HOM扫描策略或已确认结果。旧分析中的“未实现”是此前状态，以下是当前实现。不是新MCP接口或独立任务框架。

## 逐项收敛

|编号|当前实现|主要入口与验证|
|---|---|---|
|A01|区分实际执行/在途操作和待协调停止意图。稳定RECOVERY_REQUIRED可请求完整退出；先幂等登记cancel_start，不伪造旧运行成功。取消被明确拒绝或响应不确定时保留本地意图，最终仍由物理退出核验决定是否可退出|RunnerController.has_execution_work/request_shutdown；Runner._command(cancel_start)；pending_ui_stop/unreconciled_stop GUI测试|
|A02|一次发现只读一次退出证明，单会话复核用_read_session，不再每处理一个会话都全项目扫描。重型shutdown核验移出Runner控制锁，核验后检查owner/control_revision/run_id，不能在控制权或运行已改变时提交；关闭已接受后拒绝新操作|discover_managed_sessions/_read_session；Runner.command/verify_shutdown_safety；扫描次数和阻塞哈希期间status/换控制权测试|
|A03|恢复有独立run_id；扫描全部历史start意图，恢复/采用核验成功后逐一写INTERRUPTED/reconciled终态，result_outcome=not-inferred，reconciled_by指向本次恢复。已有终态不覆盖；坏JSON/错误归属终态进入intent_diagnostics并阻断自动收口|Runner._unfinished_start_intents/_reconcile_start_intents/_execute；双意图重启、坏记录、磁盘失败后续做测试|
|A04|stop在RECOVERING写暂停意图，恢复在会话/协议轮询/对账任务及旧意图收口边界消费。暂停抛RecoveryPaused，保留RECOVERY_REQUIRED与证据，不自动重算；GUI提供“暂停恢复”及对应确认语义|recovery_control、Backend.recover_project_sessions、managed_session_recovery、checkpoint_adoption；ACK后暂停/重入、采用前暂停/幂等、项目锁释放测试|
|A05|连接失败但Runner锁可取得时，不重启服务；先核验项目物理会话和预处理安全，再报告already_offline。锁仍占用或CST未知则不宣告退出。GUI连接未知时可明确请求“核验并退出”，只读窗口仍不能退出他人后台|RunnerClient.shutdown_and_wait；未知运输层/无重启/物理未知拒绝测试|
|A06|明确HTTP拒绝用RunnerRejected保留path及原因；GUI对/commands拒绝保留已连接事实，只有运输/状态不可核验才unknown。操作拒绝不再统称计算失败；被拒的自动停止意图不高频重试|RunnerClient.request、RunnerController.poll、MainWindow.onRunError；业务拒绝不标断线测试|
|A07|导出按钮可取消；关闭窗口会请求取消并延期到当前文件操作返回，导出线程结束后再继续正常退出选择。发现/捕获进度可见，取消清理本轮临时/部分包，既有文件不改|export_failure_bundle(cancel_check,progress)、DiagnosticExportThread、MainWindow.closeEvent；取消/磁盘错误/延期关闭测试|
|A08|按钮“恢复项目”包括会话、检查点、采用记录。lifecycle.physical_pending_count统计所有未确认exited的会话；GUI显示真实计数或待核验，历史snapshot不冒充实时计数。INI任务恢复标记不再伪装成“1个CST”|lifecycle_facts、RunnerController.poll、MainWindow.renderRunState；历史计数/同状态更新测试|

## 恢复暂停的明确语义

暂停不是撤销已发布的协议动作。current.task/completion/ACK、停止请求和已经写入的采用事件都保留；下次恢复按身份与hash重入。纯校验阶段可在下一项开始前暂停；单个模型hash或系统read/stat未返回时不能保证立即暂停。部分采用标记已写时下次幂等补齐，不重复导入或求解。暂停后的新一次recover使用新StopIntent及操作ID，不继承上一轮暂停文件。

CLI继续使用已有stop操作，run_id必须为当前恢复操作的ID，而非历史计算run_id；GUI自动传当前值。恢复完成不会自动开始计算，仍需“继续未完成”。请求停止和暂停都是接收意图，不等于即时终止Solver。

正常求解与通信/收尾分开计时：仅在当前task/context的session和task身份一致、生命周期文件属于项目/同会话、不是旧context之前的trace，且最后完整行明确为本项目Solver.Start调用而未出现return/Completion时，将观察到的求解等待时间从恢复预算剔除。依据是本项目自有宏的精确Trace，不猜测CST原生日志名字、CPU占用或旧阶段。任务/上下文读取有界，trace只读8KiB尾部。通信和退出仍受每会话1200秒预算；停止/暂停仍可使用。阶段缺失、不可解码或身份不符不套用无总超时推断，保持有界核验并保留会话，不能据超时宣告无模式或强杀。

## 意图收口、错误与恢复

cancel_start tombstone仅阻止该请求将来重新执行，并登记对现有运行的停止意图；它不等于原任务成功或已经停止。运行仍active时仍走原停止流程；稳定但未收口的运行保留待恢复，允许登记tombstone。运输响应丢失时本地意图不能擅自删除；用户请求完整退出仍会通过独立安全检查，不能靠该文件把界面永久锁住。

恢复失败或暂停不为旧start写“完成”；坏意图或坏终态也不覆盖。恢复成功后所有未收口旧意图写可追溯的中断收口记录；若中途磁盘错误，已写记录保留，下一次只处理剩余。当前恢复操作另有自己的outcome，计算成功事实仍来自原结果/检查点，不从恢复终态推导。

## 退出与控制通道

运行/停止投递线程仍活跃时不能shutdown。重型核验期间status和heartbeat可服务；其他窗口若接管或本次run改变，原退出请求被拒，需新鲜核验后重试。不存在永久有效的模型hash缓存，也不跳过最终结果快照核验；本轮优化减少重复遍历，不承诺历史模型核验变成常数时间。小型状态持久化仍在控制锁内，文件系统完全不响应仍可能影响服务，不承诺硬实时。

already_offline只表示已核验Runner所有权释放及允许本次退出的物理安全；不伪造CST标准StopAck/退出0。保留任务RECOVERY_REQUIRED及未解决的停止意图，重新打开仍按原证据核验。无法确认的PID/孤儿进程、坏回执或变更快照不放宽；人工复核入口仍是后续设计，不引入“忽略安全”按钮。

导出取消是协作式取消，不销毁运行中QThread，不强杀进程，不能硬中断阻塞在OS内的磁盘/网络调用。界面继续处理事件，显示取消等待原因；关闭选择在导出安全结束后继续。截尾/预算/缺失记录保持原合同。

## 新接口与持久字段

无新HTTP操作，仍为start/stop/recover/cancel_start/shutdown。HTTP错误体不变；RunnerRejected是本地类型分类。新增控制观察字段unfinished_intents/intent_diagnostics及生命周期physical_pending_count；recovery_progress增加pausing/paused/waiting-solver阶段。旧值缺失或历史数据均显式待核验。恢复新增独立run身份及旧outcome的reconciled_by/result_outcome字段；这些是内部控制记录，不替代MCP统一契约。

内部新增RecoveryPaused；recover_project_sessions、discover_managed_sessions、recover_and_stop_session及reconcile_checkpoint_adoptions增加可选pause_check。协议等待增加wait_remaining以扣除有证据的求解时间。诊断导出增加cancel_check/progress及ExportCancelled；同步调用方仍可省略回调。

## 测试与证据边界

实现对照Runner.command/_execute、RunnerClient.shutdown_and_wait、Backend.recover_project_sessions及GUI退出编排；回归见test/recovery_exit_audit_test.py、test/runner_recovery_test.py、test/project_recovery_state_test.py、test/checkpoint_adoption_test.py。CLI shutdown复用同一核验；后台已离线不为退出而重启。

[原批次完整记录](archive/20261103-semantic-review/recovery-exit-audit-implementation.md)保留11月2日全部分组数字、失败修正、目录释放和清理记录。它们有重叠且使用fake执行器，不是本次真实CST或现场DPI验收；远端慢盘、孤儿归属及真实故障矩阵仍独立待验。
