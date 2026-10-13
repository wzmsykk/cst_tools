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

## 从日志定位

- 使用run_id→session_id→task_id，先查RunStore与received记录，再查协议目录和lifecycle.log；不能仅按时间猜任务。
- `WORKER_TASK_COMPLETE`：F03；`REBUILD_FAILED`、`SOLVER_FAILED`：F09；`WORKER_STOP_FAILED`：F03/F04/F05。
- `stage=restore-parameters/recovery-rebuild/save/stop-ack/batch-return`：F04；检查点位于工作副本旁`worker-input.cst.last-good-parameters.tsv`。
- 核对最近证据：`docs/current-status.md`→具体验收文档→artifacts/report.json。大型原始模型/场文件可能未提交。

## 维护

遵守根目录[AGENTS.md](../AGENTS.md)。索引测试检查本地链接和Python/VBA符号，不自动证明功能完整或更新 prose 内容；实现者必须同步状态、用途、限制与验收证据。
