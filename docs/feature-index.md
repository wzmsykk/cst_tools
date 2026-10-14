# 功能—实现—验收映射入口

日期：2026-10-14。这是维护中的核心功能索引，不是全仓符号清单。先按功能ID查实现，再查工具、日志和验收；历史方案不是现行运行保证。

|ID|功能|源码|函数/类|测试或操作工具|说明文档|
|---|---|---|---|---|---|
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

## 从日志定位

- 使用run_id→session_id→task_id，先查RunStore与received记录，再查协议目录和lifecycle.log；不能仅按时间猜任务。
- `WORKER_TASK_COMPLETE`：F03；`REBUILD_FAILED`、`SOLVER_FAILED`：F09；`WORKER_STOP_FAILED`：F03/F04/F05。
- `stage=restore-parameters/recovery-rebuild/save/stop-ack/batch-return`：F04；检查点位于工作副本旁`worker-input.cst.last-good-parameters.tsv`。
- 核对最近证据：`docs/current-status.md`→具体验收文档→artifacts/report.json。大型原始模型/场文件可能未提交。

## 维护

遵守根目录[AGENTS.md](../AGENTS.md)。索引测试检查本地链接和Python/VBA符号，不自动证明功能完整或更新 prose 内容；实现者必须同步状态、用途、限制与验收证据。
