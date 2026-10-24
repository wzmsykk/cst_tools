# 功能—实现—验收映射入口

日期：2026-10-25。这是维护中的核心功能索引，不是全仓符号清单。先按功能ID查实现，再查工具、日志和验收；历史方案不是现行运行保证。

设计入口D03：[Python/VBA生命周期故障矩阵与L1–L5](python-vba-lifecycle-protocol-v2-plan.md)。L1–L4已接入，新会话生成v2；[真实收尾](close-v2-l5-acceptance.md)、[Controller退出](controller-exit-l5-acceptance.md)及[HOM恢复](hom-interruption-l5-acceptance.md)分别记录实际范围。完整L5仍pending，不把部分窗口通过扩大为全矩阵保证。

|ID|功能|源码|函数/类|测试或操作工具|说明文档|
|---|---|---|---|---|---|
|F76|真实小网格HOM中断恢复及无中断对照|[HOM退出探针](../test/support/validate_hom_exit_l5.py)|`run_case`, `adoption`, `evidence`, `submissions`, `verify_reports`|[探针断言测试](../test/hom_exit_l5_test.py)、[采用对账测试](../test/checkpoint_adoption_test.py)|[HOM验收及边界](hom-interruption-l5-acceptance.md)|
|F62|L3任务级ACK与失败退役|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker._wait_task_ack`, `ManagedCSTWorker.retiring`, `ManagedCSTWorker._build_macro`|[L3假对端专项](../test/production_close_v2_test.py)|[L3状态/时序](production-close-v2-l3.md)|
|F63|L3生产宏状态采集与v2实际发布|[生产宏](../data/runtime_managed_worker_v1_main.vb)|`Main`, `CSTPMW_PublishFailure`, `CSTPMW_CloseSession`, `CSTPMW_CheckStop`|[L3源码契约](../test/production_close_v2_test.py)|[L3保护与门禁](production-close-v2-l3.md)|
|F64|v2实际任务/模型事实采集|[session_closure.py](../csttool/session_closure.py)|`collect_close_evidence`, `_validate_last_received_task`|[L3停止边界测试](../test/production_close_v2_test.py)|[L3身份/关闭边界](production-close-v2-l3.md)|
|F59|L2收尾回执v2及静态版本|[close_receipt.py](../csttool/close_receipt.py)|`CloseReceipt`, `encode_close_receipt`, `decode_close_receipt`, `declare_close_protocol`, `read_close_receipt`|[v2矩阵](../test/close_receipt_test.py)|[v2协议API与边界](close-receipt-v2.md)|
|F60|VBA收尾回执v2库|[runtime_close_receipt_v2.vb](../data/runtime_close_receipt_v2.vb)|`CSTC2_ReadCloseReceipt`, `CSTC2_WriteCloseReceipt`|[源码契约测试](../test/close_receipt_test.py)|[v2 VBA接口](close-receipt-v2.md)|
|F61|v2隔离契约宏生成及产物核验|[close_receipt_contract.py](../csttool/close_receipt_contract.py)|`prepare_close_receipt_contract`, `verify_close_receipt_contract`|[契约测试](../test/close_receipt_test.py)|[v2验收范围](close-receipt-v2.md)|
|F58|L1关闭证据内核及Python退出观测|[session_closure.py](../csttool/session_closure.py)|`CloseEvidence`, `ClosureAssessment`, `evaluate_closure`, `read_recorded_exit`|[L1故障矩阵](../test/session_closure_test.py)|[L1实现与兼容](session-closure-l1.md)|
|F56|GUI后台服务管理|[runner_management_dialog.py](../GUI/runner_management_dialog.py)|`RunnerManagementDialog`|[GUI测试](../test/gui_runner_test.py)|[后台管理](gui-runner-management.md)|
|F57|Runner有界标准退出核验|[runner_client.py](../csttool/runner_client.py)|`RunnerClient.shutdown_and_wait`|[独立假Runner测试](../test/runner_test.py)|[后台管理](gui-runner-management.md)|
|F53|项目恢复公共门禁与检查点校验|[project_recovery_state.py](../csttool/project_recovery_state.py)|`persisted_project_status`, `validate_recovery_checkpoint`|[状态回归](../test/project_recovery_state_test.py)|[恢复状态对账与TODO](project-recovery-state-reconciliation.md)|
|F54|恢复专用配置加载|[配置管理器](../csttool/projectconfmanager.py)|`ProjectConfigManager.load_recovery_configuration`|[状态回归](../test/project_recovery_state_test.py)|[恢复状态对账](project-recovery-state-reconciliation.md)|
|F55|Runner与持久项目状态对账|[Runner](../csttool/runner.py)|`Runner._reconcile_project_state`, `LocalExecution.session_safety`|[GUI恢复入口测试](../test/gui_runner_test.py)|[恢复状态对账](project-recovery-state-reconciliation.md)|
|F01|任务批量调度|[cstmanager.py](../csttool/cstmanager.py)|`CSTManager.run_batch`|[manager测试](../test/cstmanager_test.py)|[Manager API](cstmanager-api.md)|
|F02|工程预处理与历史设置|[cst_preprocessor.py](../csttool/cst_preprocessor.py)|`CstProjectPreprocessor.preprocess`|[预处理测试](../test/cst_preprocessor_test.py)|[作用域修正](concave-expression-scope-rebuild-fix.md)|
|F03|Managed任务与停止|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker.run_task`, `ManagedCSTWorker.stop`|[Worker测试](../test/managed_cstworker_test.py)|[生命周期与回滚](failed-rebuild-stop-recovery.md)|
|F04|VBA参数恢复与批退出|[Managed模板](../data/runtime_managed_worker_v1_main.vb)|`CSTPMW_CaptureGoodParameters`, `CSTPMW_RestoreGoodParameters`, `CSTPMW_CloseSession`|[直接停止探针](../test/support/validate_failed_rebuild_stop.py)|[生命周期与回滚](failed-rebuild-stop-recovery.md)|
|F05|会话发现与恢复|[project_session_recovery.py](../csttool/project_session_recovery.py)|`discover_managed_sessions`, `recover_project_sessions`|[Ack测试](../test/ack_shutdown_contract_test.py)|[运行协议](python-vba-runtime-protocol.md)|
|F06|字段读取与支持域校验|[field_artifacts.py](../csttool/field_artifacts.py)|`read_field`, `artifacts_from_result`|[导出生命周期测试](../test/saved_field_export_lifecycle_test.py)|[算子执行方案](postprocess-operator-execution-plan.md)|
|F07|场匹配诊断|[field_diagnostics.py](../csttool/field_diagnostics.py)|`run_field_diagnostic`|[真实诊断探针](../test/support/validate_managed_field_diagnostic.py)|[六阶段验收](mode-field-selection-implementation-status.md)|
|F08|保存场导出|[saved_field_export.py](../csttool/saved_field_export.py)|`export_saved_fields`|[效率探针](../test/support/benchmark_field_efficiency.py)|[算子执行方案](postprocess-operator-execution-plan.md)|
|F09|求解失败分类与恢复|[Managed模板](../data/runtime_managed_worker_v1_main.vb)|`Main`|[求解失败探针](../test/support/validate_solver_failure_recovery.py)|[历史与失败对照](cst-history-persistence-and-solver-failure.md)|
|F10|历史持久性对照|[持久性探针](../test/support/validate_history_persistence.py)|`main`, `validate_states`|[持久性探针](../test/support/validate_history_persistence.py)|[历史与失败对照](cst-history-persistence-and-solver-failure.md)|
|F11|日志与JSONL上下文|[logging_config.py](../csttool/logging_config.py)|`ContextLogger`, `JsonLineFormatter`|[测试指南](testing-guide.md)|[当前状态](current-status.md)|
|F12|应用后端准备与恢复|[application_backend.py](../csttool/application_backend.py)|`CstApplicationBackend.prepare_run`, `CstApplicationBackend.recover_project_sessions`|[后端测试](../test/application_backend_test.py)|[后端API](application-backend.md)|
|F13|日志事件到源码映射|[log_event_index.py](../csttool/log_event_index.py)|`render_event_table`|[事件同步门禁](../test/log_event_index_test.py)|[事件索引](log-event-index.md)|
|F14|GUI运行控制|[run_controller.py](../GUI/run_controller.py)|`GuiRunController`|[GUI流程测试](../test/gui_fake_worker_flow_test.py)|[GUI路线](gui-refactor-todo.md)|
|F15|任意轴运行时复杂后处理|[EigenResult_Complex.vb](../data/postprocess/EigenResult_Complex.vb)|`EigenResult_Complex`|[VBA语义门禁](../test/vba_document_contract_test.py)|[算子执行方案](postprocess-operator-execution-plan.md)|
|F16|恢复失败真实注入与死会话收口|[故障探针](../test/support/validate_recovery_faults.py)|`run_case`, `reconcile_report`|[停止故障门禁](../test/failed_rebuild_stop_test.py)|[停止故障验收](failed-rebuild-stop-recovery.md)|
|F17|缺场及损坏工件分析恢复验收|[场故障探针](../test/support/validate_field_failure_recovery.py)|`main`, `diagnose_saved_faults`|[工件恢复测试](../test/field_failure_recovery_probe_test.py)|[缺场与工件验收](field-failure-recovery-acceptance.md)|
|F18|共同域与体积求积|[physical_domain.py](../csttool/physical_domain.py)|`common_quadrature`, `sampling_convergence`|[物理域测试](../test/physical_domain_test.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F19|原生几何/材料掩码|[geometry_support.py](../csttool/geometry_support.py)|`render_material_support`, `load_material_support`|[Pillbox探针](../test/support/validate_pillbox_full_domain.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F20|独立Pillbox双模基准|[pillbox_reference.py](../csttool/pillbox_reference.py)|`tm110_reference`|[Pillbox探针](../test/support/validate_pillbox_full_domain.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F21|Pillbox全域第二网格与小网格Tracker验收|[跨网格探针](../test/support/validate_pillbox_cross_mesh.py)|`compare_pair`, `verify_mesh_counts`, `validate_tracker`|[追踪测试](../test/vacuum_mode_tracking_test.py)|[全域验收](physical-domain-pillbox-acceptance.md)|
|F22|封闭真空腔固定参考模式追踪|[vacuum_mode_tracking.py](../csttool/vacuum_mode_tracking.py)|`select_vacuum_modes`, `VacuumModeTracker.evaluate`, `track_saved_sequence`|[追踪测试](../test/vacuum_mode_tracking_test.py)|[第一版API与使用](vacuum-mode-tracking-v1.md)|
|F23|工程前提预检与自动掩码登记|[vacuum_domain_registry.py](../csttool/vacuum_domain_registry.py)|`register_vacuum_domain`, `load_registered_support`, `export_registered_vacuum_fields`|[登记测试](../test/vacuum_domain_registry_test.py)|[登记API与边界](vacuum-domain-registration.md)|
|F24|Managed可选退出后登记|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker._finish_domain_registration`|[可选链测试](../test/managed_vacuum_domain_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F25|GUI真空域设置开关|[algorithm_settings_dialog.py](../GUI/algorithm_settings_dialog.py)|`AlgorithmSettingsDialog.setValues`|[GUI配置测试](../test/gui_config_models_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F26|Managed固定参考模式匹配|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker._run_vacuum_matching`|[匹配链测试](../test/managed_vacuum_matching_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F27|GUI登记/匹配假Worker流程|[假Worker验收](../test/gui_vacuum_matching_fake_flow_test.py)|`MatchingFakeWorker`, `MatchingFakeBackend`|[流程测试](../test/gui_vacuum_matching_fake_flow_test.py)|[GUI与生命周期](managed-vacuum-domain-gui.md)|
|F28|随机谱HOM假Worker与异常扫描|[hom_fake_worker.py](../test/support/hom_fake_worker.py)|`ProbabilisticHomWorker`|[随机谱测试](../test/hom_probabilistic_fake_worker_test.py)|[HOM假Worker验收](fake-hom-acceptance.md)|
|F29|预处理阶段监测、修改明细与失败保留|[cst_preprocessor.py](../csttool/cst_preprocessor.py)|`CstProjectPreprocessor._run`, `CstProjectPreprocessor._log_details`, `CstProjectPreprocessor._observer`|[预处理测试](../test/cst_preprocessor_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F30|HOM预处理保留mesh选项与恢复策略|[projectconfmanager.py](../csttool/projectconfmanager.py)|`ProjectConfigManager.prepare_project`|[mesh策略测试](../test/projectconfmanager_mesh_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F31|GUI预处理保留mesh交互|[algorithm_settings_dialog.py](../GUI/algorithm_settings_dialog.py)|`AlgorithmSettingsDialog._set_preserve_mesh`|[GUI配置测试](../test/gui_config_models_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F32|CST任务级归属、共享实例诊断与退出门禁|[acceptance_session.py](../csttool/acceptance_session.py)|`wait_probe`, `task_project_processes`|[进程监测测试](../test/acceptance_session_test.py)|[预处理诊断](preprocess-diagnostics.md)|
|F33|GUI长日志有界批量显示与滚动（无清空API）|[log_view.py](../GUI/log_view.py)|`QPlainTextEditLogger.emit`, `QPlainTextEditLogger.flush_pending`|[日志显示测试](../test/gui_log_view_test.py)|[日志显示性能](gui-log-performance.md)|
|F34|GUI事件模型、组合筛选、详情及原始文件入口|[event_log_view.py](../GUI/event_log_view.py)|`EventTableModel.append_events`, `EventFilter.filterAcceptsRow`, `StructuredLogHandler.show_details`, `StructuredLogHandler.file_path`|[结构化日志测试](../test/gui_event_log_view_test.py)|[结构化事件使用](gui-structured-log.md)|
|F35|可读摘要、完整文本上下文及异常传播引用|[logging_config.py](../csttool/logging_config.py)|`DiagnosticTextFormatter.format`, `normalized_context`, `log_failure`|[日志配置测试](../test/logging_config_test.py)、[Worker顺序测试](../test/managed_cstworker_test.py)|[六链日志设计](readable-logging.md)|
|F36|Worker不取任务锁的协作停止|[managed_cstworker.py](../csttool/managed_cstworker.py)|`ManagedCSTWorker.request_stop`|[停止及续跑测试](../test/cooperative_stop_resume_test.py)|[停止与覆盖续跑](cooperative-stop-and-hom-resume.md)|
|F37|VBA步骤停止检查与中断求解保留|[Managed模板](../data/runtime_managed_worker_v1_main.vb)|`CSTPMW_CheckStop`|[停止及续跑测试](../test/cooperative_stop_resume_test.py)|[停止与覆盖续跑](cooperative-stop-and-hom-resume.md)|
|F38|可读运行日志目录、摘要、旧目录总览|[run_overview.py](../csttool/run_overview.py)|`RunOverview.update`, `RunOverviewHandler.emit`, `rebuild_log_index`|[运行总览测试](../test/run_overview_test.py)|[可读日志目录](readable-log-directories.md)|
|F40|运行级持久停止意图与最小契约|[execution_contract.py](../csttool/execution_contract.py)|`StopIntent.check`, `StopIntent.request`, `ArtifactRef`, `validate_command`|[恢复测试](../test/runner_recovery_test.py)|[本机Runner](local-runner.md)|
|F41|独立Runner及持久本机命令|[runner.py](../csttool/runner.py)|`Runner.command`, `Runner.snapshot`, `LocalExecution.run`, `serve`|[进程验收](../test/runner_test.py)|[本机Runner](local-runner.md)|
|F42|控制器OS所有权与受保护目录|[runner_ownership.py](../csttool/runner_ownership.py)|`RunnerOwnership.acquire`, `protect_directory`|[进程验收](../test/runner_test.py)|[统一计划](execution-platform-implementation-plan.md)|
|F43|本机Runner发现/启动/CLI|[runner_client.py](../csttool/runner_client.py)|`RunnerClient.connect`, `RunnerClient.command`, `main`|[进程验收](../test/runner_test.py)|[本机Runner](local-runner.md)|
|F44|生产GUI客户端与重连|[runner_controller.py](../GUI/runner_controller.py)|`RunnerController.poll`, `RunnerController.detach`|[GUI测试](../test/gui_runner_test.py)|[本机Runner](local-runner.md)|
|F45|有限标准批次和持久采用|[standard_batch.py](../csttool/standard_batch.py)|`StandardBatchAlgorithm.start`|[真实副本验收](../test/runner_cst_integration_test.py)|[本机Runner](local-runner.md)|
|F46|完成未接收的结果核验导入|[result_reconciliation.py](../csttool/result_reconciliation.py)|`recover_completed_result`|[恢复测试](../test/runner_recovery_test.py)|[本机Runner](local-runner.md)|

## 从日志定位

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F73|检查点已确认采用标记补写|[checkpoint_adoption.py](../csttool/checkpoint_adoption.py)|`confirmed_tasks`, `reconcile_checkpoint_adoptions`, `mark_adopted`|[身份/幂等/故障矩阵](../test/checkpoint_adoption_test.py)|[采用对账](checkpoint-adoption-l5.md)|
|F74|RunStore日志/索引幂等采用与共享锁|[run_store.py](../csttool/run_store.py)|`RunStore.ensure_adopted`, `RunStore._adoption_events`|[并发/截断/部分写入](../test/checkpoint_adoption_test.py)|[写入顺序及边界](checkpoint-adoption-l5.md)|
|F75|真实采用标记三个退出窗口复核|[validate_controller_exit_l5.py](../test/support/validate_controller_exit_l5.py)|`marker_state`, `marker_hashes`, `verify_adoption_reports`|[真实串行记录](checkpoint-adoption-l5.md)|[Controller验收](controller-exit-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F70|L5 GUI/Runner进程退出与真实恢复|[validate_controller_exit_l5.py](../test/support/validate_controller_exit_l5.py)|`run_case`, `runner_child`, `gui_child`, `verify_reports`|[退出相关回归](../test/controller_exit_l5_test.py)|[六类真实记录](controller-exit-l5-acceptance.md)|
|F71|已完成归档的接收路径恢复|[result_reconciliation.py](../csttool/result_reconciliation.py)|`reconcile_archive_receipt`, `recover_completed_result`, `find_received_result`|[身份/哈希/歧义回归](../test/controller_exit_l5_test.py)|[归档缺口与边界](controller-exit-l5-acceptance.md)|
|F72|线程收尾与客户端可启动状态|[runner.py](../csttool/runner.py)|`Runner.snapshot`|[活跃快照](../test/controller_exit_l5_test.py)、[GUI等待](../test/gui_runner_test.py)|[API及收尾竞态](controller-exit-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F68|Completion清理后的待采用结果恢复发现|[project_session_recovery.py](../csttool/project_session_recovery.py)|`_pending_result_task`, `ManagedSessionRecord.closure`|[停止/ACK回归](../test/stop_ack_l5_test.py)|[实际缺口与修复](stop-ack-l5-acceptance.md)|
|F69|真实停止/ACK时序与产物复核|[validate_stop_ack_l5.py](../test/support/validate_stop_ack_l5.py)|`run_timing`, `read_current_completion`, `verify_timing_reports`|[探针契约](../test/stop_ack_l5_test.py)|[十二时点验收](stop-ack-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F67|L5串行真实副本与故障核验|[validate_close_v2_l5.py](../test/support/validate_close_v2_l5.py)|`run_case`, `run_codec`, `verify_fault_matrix`|[固定收尾快照测试](../test/close_v2_l5_test.py)|[真实验收与剩余](close-v2-l5-acceptance.md)|

|功能ID|目的|源码|函数|测试|说明|
|---|---|---|---|---|---|
|F65|L4生命周期事实与异常原因链|[lifecycle_diagnostics.py](../csttool/lifecycle_diagnostics.py)|`project_lifecycle`, `lifecycle_facts`, `result_observation`, `error_diagnostic`|[事实测试](../test/lifecycle_diagnostics_test.py)|[Runner/GUI事实](runner-lifecycle-l4.md)|
|F66|L4 GUI诊断与源码展示|[lifecycle_display.py](../GUI/lifecycle_display.py)|`lifecycle_lines`, `runner_error_text`|[GUI测试](../test/gui_runner_test.py)|[使用及边界](runner-lifecycle-l4.md)|

Runner审计修复：F41/F43/F44增加`cancel_start`和命令对账，当前API及门禁见[修复记录](runner-audit-fix-20261015.md)。

|功能ID|功能|源码|函数/类型|测试|说明|
|---|---|---|---|---|---|
|F47|有界JSONL游标与异常记录跳过|[event_replay.py](../csttool/event_replay.py)|`read_events`|[审计回归](../test/runner_audit_regression_test.py)|[Runner API](local-runner.md)|
|F48|纯HOM草稿默认值与mesh校验|[scan_settings.py](../csttool/scan_settings.py)|`default_hom_settings`, `validate_hom_settings`|[审计回归](../test/runner_audit_regression_test.py)|[修复记录](runner-audit-fix-20261015.md)|
|F49|配置草稿与显式进程内执行适配|[application_service.py](../GUI/application_service.py)|`ConfigurationDraft`, `ConfigurationService`, `CstApplicationService`|[服务测试](../test/gui_application_service_test.py)|[Runner API](local-runner.md)|
|F50|自动恢复任务摘要及日志保留|[main_window.py](../GUI/main_window.py)|`MainWindow.renderRunnerSnapshot`|[日志恢复测试](../test/gui_log_restore_test.py)|[日志恢复API与边界](gui-log-restoration.md)|
|F51|默认开启的日志自动滚动开关|[event_log_view.py](../GUI/event_log_view.py)|`StructuredLogHandler.set_auto_scroll`, `StructuredLogHandler.go_latest`|[事件显示测试](../test/gui_event_log_view_test.py)、[原始镜像测试](../test/gui_log_view_test.py)|[结构化日志使用](gui-structured-log.md)|
|F52|原生阶段标准键及原文保留（含用户日志四阶段）|[cst_progress.py](../csttool/cst_progress.py)|`normalize_cst_stage`, `CstProgressEvent`|[原生进度测试](../test/native_progress_test.py)、[GUI显示](../test/gui_main_window_test.py)|[原生阶段记录](cst-native-progress-observation.md)|

停止与退出确认：F39，源码 [MainWindow](../GUI/main_window.py) 的 `closeEvent`、`requestStop`、`_confirm_action` 和 [Controller](../GUI/run_controller.py) 的 `_stop_failed`；测试 [GUI测试](../test/gui_main_window_test.py)，说明 [停止/退出](gui-stop-exit.md)。

- 使用run_id→session_id→task_id，先查RunStore与received记录，再查协议目录和lifecycle.log；不能仅按时间猜任务。
- `WORKER_TASK_COMPLETE`：F03；`REBUILD_FAILED`、`SOLVER_FAILED`：F09；`WORKER_STOP_FAILED`：F03/F04/F05。
- `stage=restore-parameters/recovery-rebuild/save/stop-ack/batch-return`：F04；检查点位于工作副本旁`worker-input.cst.last-good-parameters.tsv`。
- 核对最近证据：`docs/current-status.md`→具体验收文档→artifacts/report.json。大型原始模型/场文件可能未提交。

## 维护

F40–F44审计回应：[收悉工作记录及逐项结论](runner-audit-response-20261015.md)保留修复前历史；四项缺陷/M1现已修复，当前验收及剩余门禁见[修复记录](runner-audit-fix-20261015.md)。

F40–F44历史审查边界：[2026-10-15本机分离审查](../knowledge-base/runner-separation-review-20261015.md)，涉及 Runner.snapshot/events 与 RunnerController.poll/_observe/_command；现行映射包括F47–F49，不将原审查“未修复”作为当前结论。

实施总入口D00：[统一实施计划E0–E9](execution-platform-implementation-plan.md)。本机E0–E5主链已实施，实际验收及未完成门禁以该文为准；D01/D02保留设计细节。

规划入口D02（未实施）：[远程/分布式扩展设计](remote-distributed-execution-design.md)，含任务/尝试身份、所有权代次、数据位置、Warm亲和及阶段验收；当前本地源码约束与复用映射见该文第10节。

设计入口D01：[GUI/Runner分离设计与TODO](gui-runner-process-separation-design.md)。历史拟议方案保留，当前接口见[本机Runner](local-runner.md)，实际实现映射见F40–F46。

遵守根目录[AGENTS.md](../AGENTS.md)。索引测试检查本地链接和Python/VBA符号，不自动证明功能完整或更新 prose 内容；实现者必须同步状态、用途、限制与验收证据。
